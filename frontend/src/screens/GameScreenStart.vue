<script setup lang="ts">
import { computed, onScopeDispose, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import { canonicalUuid } from '../api/authIntent'
import { isPreparingGame } from '../api/games'
import { listPlayers } from '../api/roster'
import type { StartLineupInput } from '../api/gameStart'
import { useAuthStore } from '../stores/authStore'
import {
  currentEntrySupply,
  type EntrySupply,
  type PreparingReadDetail,
} from './GameScreenEntryTypes'
import type { useGameStartProvider } from './GameScreenStartProvider'

const props = defineProps<{
  preparing: EntrySupply<PreparingReadDetail> | null
  connection: ReturnType<typeof useGameStartProvider>
}>()
const route = useRoute()
const auth = useAuthStore()
type Side = 'away' | 'home'
interface Choice {
  id: string
  name: string
  number: string | null
}
interface DraftRow {
  player: Choice | null
  position: string
}
interface PlayerPage {
  items: Choice[]
  cursor: string | null
  next: string | null
  history: (string | null)[]
  index: number
  loaded: boolean
  loading: boolean
  failed: boolean
}
const sides = ['away', 'home'] as const
const labels = { away: '先攻', home: '後攻' } as const
// DOMの選択文字列を、正式な開始入力の有限整数へ写像する。
const positionValues = {
  '1': 1,
  '2': 2,
  '3': 3,
  '4': 4,
  '5': 5,
  '6': 6,
  '7': 7,
  '8': 8,
  '9': 9,
} as const
const positions = [
  ['1', '投手'],
  ['2', '捕手'],
  ['3', '一塁手'],
  ['4', '二塁手'],
  ['5', '三塁手'],
  ['6', '遊撃手'],
  ['7', '左翼手'],
  ['8', '中堅手'],
  ['9', '右翼手'],
] as const
const drafts = reactive<Record<Side, DraftRow[]>>({ away: [], home: [] })
function page(): PlayerPage {
  return {
    items: [],
    cursor: null,
    next: null,
    history: [null],
    index: 0,
    loaded: false,
    loading: false,
    failed: false,
  }
}
const pages = reactive<Record<Side, PlayerPage>>({ away: page(), home: page() })
const requests: Partial<Record<Side, AbortController>> = {}
let generation = 0
let disposed = false
const detail = computed(() => {
  const id = route.params.gameId
  if (typeof id !== 'string' || !canonicalUuid.test(id)) return null
  const supplied = currentEntrySupply(props.preparing, auth, route, id)
  const value = supplied?.data
  return supplied?.status === 'ready' &&
    value !== undefined &&
    value.gameId === id &&
    value.tenantId === auth.teamId &&
    isPreparingGame(value.saved) &&
    value.saved.id === id &&
    typeof value.saved.applied_rules.dh === 'boolean'
    ? value.saved
    : null
})
const scopeKey = computed(() =>
  JSON.stringify([
    auth.authEpoch,
    auth.teamId,
    route.path,
    route.params.gameId,
    detail.value?.away_team_record_id,
    detail.value?.home_team_record_id,
    detail.value?.applied_rules.dh,
  ]),
)
function abort() {
  for (const side of sides) {
    requests[side]?.abort()
    delete requests[side]
  }
}
function candidate(value: unknown, team: string): Choice | null {
  if (typeof value !== 'object' || value === null) return null
  const item = value as Record<string, unknown>
  if (
    typeof item.id !== 'string' ||
    !canonicalUuid.test(item.id) ||
    item.team_record_id !== team ||
    item.hidden_at !== null ||
    item.roster_status_key !== 'active' ||
    typeof item.name !== 'string' ||
    !(item.uniform_number === null || typeof item.uniform_number === 'string')
  )
    return null
  return { id: item.id, name: item.name, number: item.uniform_number }
}
async function load(
  side: Side,
  cursor: string | null,
  direction: 'next' | 'previous' | 'retry',
) {
  const saved = detail.value
  if (saved === null || !props.connection.canStart.value || pages[side].loading)
    return
  const team =
    side === 'away' ? saved.away_team_record_id : saved.home_team_record_id
  const key = scopeKey.value
  const sequence = generation
  const controller = new AbortController()
  requests[side]?.abort()
  requests[side] = controller
  pages[side].loading = true
  pages[side].failed = false
  const current = () =>
    !disposed &&
    !controller.signal.aborted &&
    sequence === generation &&
    scopeKey.value === key &&
    requests[side] === controller &&
    props.connection.canStart.value
  try {
    const result = await listPlayers(
      {
        team_record_id: team,
        roster_status_key: 'active',
        include_hidden: false,
        limit: 20,
        cursor,
      },
      { signal: controller.signal },
    )
    if (!current()) return
    if (
      typeof result !== 'object' ||
      result === null ||
      !Array.isArray(result.items) ||
      result.items.length > 20 ||
      !(
        result.next_cursor === null ||
        (typeof result.next_cursor === 'string' &&
          result.next_cursor.length > 0)
      )
    )
      throw new Error('選手応答不正')
    const items = result.items.map((value) => candidate(value, team))
    if (items.some((value) => value === null)) throw new Error('選手応答不正')
    const choices = items as Choice[]
    if (new Set(choices.map((value) => value.id)).size !== choices.length)
      throw new Error('選手応答不正')
    const state = pages[side]
    if (direction === 'next') {
      state.history = [...state.history.slice(0, state.index + 1), cursor]
      state.index += 1
    } else if (direction === 'previous') state.index -= 1
    state.items = choices
    state.cursor = cursor
    state.next = result.next_cursor
    state.loaded = true
  } catch {
    if (current()) {
      pages[side].items = []
      pages[side].failed = true
    }
  } finally {
    if (requests[side] === controller) {
      pages[side].loading = false
      delete requests[side]
    }
  }
}
watch(
  scopeKey,
  () => {
    generation += 1
    abort()
    const count =
      detail.value === null ? 0 : detail.value.applied_rules.dh ? 10 : 9
    for (const side of sides) {
      drafts[side] = Array.from({ length: count }, () => ({
        player: null,
        position: '',
      }))
      pages[side] = page()
    }
  },
  { immediate: true, flush: 'sync' },
)
watch(
  () => [scopeKey.value, props.connection.canStart.value],
  () => {
    if (!props.connection.canStart.value) {
      abort()
      for (const side of sides) pages[side].loading = false
      return
    }
    for (const side of sides)
      if (!pages[side].loaded && !pages[side].loading)
        void load(side, null, 'retry')
  },
  { immediate: true, flush: 'sync' },
)
function choose(side: Side, index: number, event: Event) {
  const row = drafts[side][index]
  if (!row) return
  const id = (event.target as HTMLSelectElement).value
  row.player =
    pages[side].items.find((item) => item.id === id) ??
    (row.player?.id === id ? row.player : null)
}
function name(player: Choice) {
  return (
    player.name +
    (player.number === null || player.number === ''
      ? ''
      : `（${player.number}）`)
  )
}
const complete = computed(
  () =>
    detail.value !== null &&
    sides.every(
      (side) =>
        drafts[side].length === (detail.value!.applied_rules.dh ? 10 : 9) &&
        drafts[side].every(
          (row, index) =>
            row.player !== null &&
            (index === 9
              ? row.position === '1'
              : positions.some(([key]) => key === row.position) ||
                (detail.value!.applied_rules.dh === true &&
                  row.position === 'DH')),
        ),
    ),
)
function start() {
  if (!props.connection.canStart.value || !complete.value) return
  const side = (key: Side): StartLineupInput[] =>
    drafts[key].map<StartLineupInput>((row, index) => {
      const entry: StartLineupInput = {
        player_id: row.player!.id,
        batting_order: index < 9 ? index + 1 : null,
        fielding_position: { kind: 'designated-hitter' },
      }
      if (row.position === 'DH') return entry
      return {
        ...entry,
        fielding_position: {
          kind: 'fielding',
          position: positionValues[row.position as keyof typeof positionValues],
        },
      }
    })
  void props.connection.start({ away: side('away'), home: side('home') })
}
onScopeDispose(() => {
  disposed = true
  generation += 1
  abort()
})
</script>

<template>
  <section
    aria-label="スタメンと試合開始"
    class="mx-auto max-w-5xl space-y-4 p-4"
  >
    <h2 class="text-xl font-bold">スタメンと試合開始</h2>
    <p role="status">{{ connection.state.value.message }}</p>
    <p v-if="connection.state.value.startedAt">
      開始日時：{{
        new Date(connection.state.value.startedAt).toLocaleString('ja-JP', {
          timeZone: 'Asia/Tokyo',
        })
      }}
    </p>
    <button
      type="button"
      class="min-h-11 rounded-lg border px-3 py-2"
      :disabled="!connection.canEnroll.value"
      @click="connection.enroll()"
    >
      この端末を登録
    </button>
    <button
      v-if="
        connection.state.value.savedRequest &&
        connection.state.value.phase !== 'received'
      "
      type="button"
      class="min-h-11 rounded-lg border px-3 py-2"
      :disabled="!connection.canResolve.value"
      @click="connection.resolve()"
    >
      保存した開始要求の結果を確認
    </button>
    <form
      v-if="connection.canStart.value && detail"
      class="space-y-4"
      @submit.prevent="start"
    >
      <p>
        {{
          detail.applied_rules.dh
            ? 'DH制のスタメンを選択してください。10人目は投手専用です。'
            : 'DHなしのスタメンを選択してください。'
        }}
      </p>
      <div class="grid gap-5 lg:grid-cols-2">
        <fieldset
          v-for="side in sides"
          :key="side"
          class="min-w-0 space-y-3 rounded-xl border p-3"
        >
          <legend class="font-bold">{{ labels[side] }}</legend>
          <p v-if="pages[side].loading" role="status">選手を取得しています</p>
          <p v-if="pages[side].failed" role="status">選手を取得できません</p>
          <div
            v-for="(row, index) in drafts[side]"
            :key="index"
            class="grid min-w-0 gap-2"
          >
            <label :for="`start-${side}-${index}-player`"
              >{{ index < 9 ? `${index + 1}番` : '投手専用' }}の選手</label
            >
            <select
              :id="`start-${side}-${index}-player`"
              :value="row.player?.id ?? ''"
              class="min-h-11 min-w-0 rounded-lg border p-2"
              @change="choose(side, index, $event)"
            >
              <option value="">選択してください</option>
              <option
                v-if="
                  row.player &&
                  !pages[side].items.some((item) => item.id === row.player?.id)
                "
                :value="row.player.id"
              >
                {{ name(row.player) }}
              </option>
              <option
                v-for="player in pages[side].items"
                :key="player.id"
                :value="player.id"
              >
                {{ name(player) }}
              </option>
            </select>
            <label :for="`start-${side}-${index}-position`"
              >{{ index < 9 ? `${index + 1}番` : '投手専用' }}の守備位置</label
            >
            <select
              :id="`start-${side}-${index}-position`"
              v-model="row.position"
              class="min-h-11 min-w-0 rounded-lg border p-2"
            >
              <option value="">選択してください</option>
              <template v-for="[value, label] in positions" :key="value"
                ><option v-if="index < 9 || value === '1'" :value="value">
                  {{ label }}
                </option></template
              >
              <option
                v-if="index < 9 && detail.applied_rules.dh === true"
                value="DH"
              >
                指名打者
              </option>
            </select>
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              v-if="pages[side].failed"
              type="button"
              class="min-h-11 rounded-lg border px-3 py-2"
              :disabled="pages[side].loading"
              @click="load(side, pages[side].cursor, 'retry')"
            >
              {{ labels[side] }}の選手を再取得
            </button>
            <button
              type="button"
              class="min-h-11 rounded-lg border px-3 py-2"
              :disabled="pages[side].loading || pages[side].index === 0"
              @click="
                load(
                  side,
                  pages[side].history[pages[side].index - 1] ?? null,
                  'previous',
                )
              "
            >
              {{ labels[side] }}の前のページ
            </button>
            <button
              type="button"
              class="min-h-11 rounded-lg border px-3 py-2"
              :disabled="pages[side].loading || pages[side].next === null"
              @click="load(side, pages[side].next, 'next')"
            >
              {{ labels[side] }}の次のページ
            </button>
          </div>
        </fieldset>
      </div>
      <button
        type="submit"
        class="min-h-11 rounded-lg border px-4 py-2 font-bold"
        :disabled="!complete || !connection.canStart.value"
      >
        試合を開始
      </button>
    </form>
    <p>
      登録と開始はオンラインで行います。記録入力は、記録の準備が完了してから利用できます。
    </p>
  </section>
</template>
