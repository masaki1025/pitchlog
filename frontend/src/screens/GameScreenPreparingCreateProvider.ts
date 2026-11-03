import { getActivePinia } from 'pinia'
import { nextTick, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { canonicalUuid } from '../api/authIntent'
import { ApiError } from '../api/client'
import {
  createPreparingGame,
  readPreparationOptions,
  readPreparingGame,
  type PreparingGame,
  type PreparingGameCreate,
  type PreparingOptions,
} from '../api/games'
import {
  listTeamRecords,
  readSelfTeamRecord,
  type TeamRecordRead,
} from '../api/roster'
import { pinia } from '../appProviders'
import { queryClient } from '../lib/queryClient'
import { useAuthStore } from '../stores/authStore'

export interface PreparingCreateChoices {
  options: PreparingOptions
  self: TeamRecordRead
  opponents: { items: TeamRecordRead[]; next_cursor: string | null }
}
export type CreateStatus =
  | 'loading'
  | 'ready'
  | 'failed'
  | 'sending'
  | 'created'
  | 'confirming'
  | 'unknown'

function opponents(
  value: unknown,
): value is PreparingCreateChoices['opponents'] {
  if (typeof value !== 'object' || value === null) return false
  const page = value as Partial<PreparingCreateChoices['opponents']>
  return (
    Array.isArray(page.items) &&
    page.items.length <= 20 &&
    page.items.every(
      (team) =>
        typeof team === 'object' &&
        team !== null &&
        typeof team.id === 'string' &&
        canonicalUuid.test(team.id) &&
        team.kind === 'opponent' &&
        team.hidden_at === null &&
        typeof team.name === 'string',
    ) &&
    new Set(page.items.map((team) => team.id)).size === page.items.length &&
    (page.next_cursor === null ||
      (typeof page.next_cursor === 'string' && page.next_cursor.length > 0))
  )
}
/** 同じ正規Pinia/QueryClientを使い、GET再試行は明示操作・POSTは一度だけにする。 */
export function usePreparingCreateProvider() {
  const auth = useAuthStore(pinia)
  const route = useRoute()
  const router = useRouter()
  const status = ref<CreateStatus>('loading')
  const choices = shallowRef<PreparingCreateChoices | null>(null)
  const created = shallowRef<PreparingGame | null>(null)
  const message = ref('')
  const online = ref(navigator.onLine === true)
  const owner = crypto.randomUUID()
  let generation = 0
  let disposed = false
  let activeQuery: readonly unknown[] | null = null
  let mutation: AbortController | null = null
  let optionsCursor: string | null = null
  let teamsCursor: string | null = null
  let optionHistory: (string | null)[] = [null]
  let teamHistory: (string | null)[] = [null]
  const canPreviousOptions = ref(false)
  const canPreviousTeams = ref(false)
  function connected() {
    online.value = navigator.onLine === true
  }
  window.addEventListener('online', connected)
  window.addEventListener('offline', connected)
  function currentContext() {
    const epoch = auth.authEpoch,
      tenant = auth.teamId,
      path = route.path,
      sequence = generation
    return () =>
      !disposed &&
      generation === sequence &&
      getActivePinia() === pinia &&
      auth.hasHydrated &&
      auth.isAuthenticated &&
      tenant !== null &&
      canonicalUuid.test(tenant) &&
      auth.teamId === tenant &&
      auth.authEpoch === epoch &&
      route.path === path &&
      path === '/games'
  }
  function cancel() {
    generation += 1
    mutation?.abort()
    mutation = null
    if (activeQuery) {
      void queryClient.cancelQueries({ queryKey: activeQuery, exact: true })
      queryClient.removeQueries({ queryKey: activeQuery, exact: true })
      activeQuery = null
    }
  }
  async function load() {
    if (['sending', 'created', 'confirming', 'unknown'].includes(status.value))
      return
    cancel()
    const current = currentContext()
    choices.value = null
    if (!current()) return
    status.value = 'loading'
    const key = [
      'preparing-create',
      owner,
      auth.teamId,
      auth.authEpoch,
      generation,
      optionsCursor,
      teamsCursor,
    ] as const
    activeQuery = key
    try {
      const result = await queryClient.fetchQuery({
        queryKey: key,
        retry: false,
        gcTime: 0,
        staleTime: 0,
        queryFn: async ({ signal }) => {
          const [options, self, teams] = await Promise.all([
            readPreparationOptions(optionsCursor, signal),
            readSelfTeamRecord({ signal }),
            listTeamRecords({ limit: 20, cursor: teamsCursor }, { signal }),
          ])
          if (!opponents(teams) || !current() || signal.aborted)
            throw new Error('選択肢を確認できません')
          return { options, self, opponents: teams }
        },
      })
      if (!current()) return
      choices.value = result
      status.value = 'ready'
      message.value = ''
    } catch {
      if (!current()) return
      choices.value = null
      status.value = 'failed'
      message.value = '選択肢を確認できません。明示的に再取得してください'
    } finally {
      queryClient.removeQueries({ queryKey: key, exact: true })
      if (activeQuery === key) activeQuery = null
    }
  }
  function page(kind: 'options' | 'teams', direction: 'next' | 'previous') {
    if (status.value !== 'ready' || !choices.value) return
    const history = kind === 'options' ? optionHistory : teamHistory
    const next =
      direction === 'previous'
        ? history.at(-2)
        : kind === 'options'
          ? choices.value.options.tournaments.next_cursor
          : choices.value.opponents.next_cursor
    if (next === undefined || (direction === 'next' && next === null)) return
    if (direction === 'previous') history.pop()
    else history.push(next)
    if (kind === 'options') optionsCursor = next
    else teamsCursor = next
    canPreviousOptions.value = optionHistory.length > 1
    canPreviousTeams.value = teamHistory.length > 1
    void load()
  }
  async function submit(body: PreparingGameCreate) {
    if (status.value !== 'ready' || !choices.value || !online.value) return
    const current = currentContext()
    if (!current()) return
    status.value = 'sending' // awaitより先に二重submitを遮断する。
    message.value = ''
    const controller = new AbortController()
    mutation = controller
    try {
      const result = await createPreparingGame(
        structuredClone(body),
        controller.signal,
      )
      if (!current() || controller.signal.aborted) return
      created.value = result
      status.value = 'created'
      message.value =
        '作成応答を受け取りました。保存された試合を確認してください'
    } catch (error) {
      if (!current()) return
      created.value = null
      if (error instanceof ApiError && [404, 409, 422].includes(error.status)) {
        status.value = 'ready'
        message.value =
          '作成を受理できませんでした。入力と大会の選択を確認してください'
      } else {
        status.value = 'unknown'
        message.value =
          '作成結果は未確認です。自動再送せず、一覧で保存結果を確認してください'
      }
    } finally {
      if (mutation === controller) mutation = null
    }
  }
  async function confirmCreated() {
    if (status.value !== 'created' || !created.value || !online.value) return
    const current = currentContext(),
      id = created.value.id
    if (!current()) return
    status.value = 'confirming'
    const controller = new AbortController()
    mutation = controller
    try {
      const result = await readPreparingGame(id, controller.signal)
      if (!current() || controller.signal.aborted || result.id !== id) return
      await router.push(`/games/${id}/record`)
    } catch {
      if (!current()) return
      status.value = 'created'
      message.value =
        '保存値を取得できませんでした。同じ試合IDを明示的に再確認できます'
    } finally {
      if (mutation === controller) mutation = null
    }
  }
  watch(
    () => [
      auth.authEpoch,
      auth.teamId,
      auth.isAuthenticated,
      auth.hasHydrated,
      route.path,
    ],
    () => {
      cancel()
      choices.value = null
      created.value = null
      message.value = ''
      status.value = 'loading'
      optionsCursor = teamsCursor = null
      optionHistory = [null]
      teamHistory = [null]
      canPreviousOptions.value = canPreviousTeams.value = false
      const request = generation
      void nextTick(() => {
        if (!disposed && generation === request) void load()
      })
    },
    { immediate: true, flush: 'sync' },
  )
  onScopeDispose(() => {
    disposed = true
    cancel()
    choices.value = null
    created.value = null
    window.removeEventListener('online', connected)
    window.removeEventListener('offline', connected)
  })
  return {
    status,
    choices,
    created,
    message,
    online,
    canPreviousOptions,
    canPreviousTeams,
    load,
    page,
    submit,
    confirmCreated,
  }
}
