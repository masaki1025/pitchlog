import { getActivePinia } from 'pinia'
import {
  computed,
  onScopeDispose,
  readonly,
  shallowRef,
  watch,
  type Ref,
} from 'vue'
import { useRoute } from 'vue-router'
import { canonicalUuid } from '../api/authIntent'
import {
  enrollInitialDevice,
  parseGameStartRequest,
  resolveInitialGameStart,
  startInitialGame,
  type GameStartRequest,
  type InitialDeviceEnrollmentResponse,
} from '../api/gameStart'
import { isPreparingGame } from '../api/games'
import { pinia } from '../appProviders'
import {
  GameStartPersistence,
  type StoredGameStart,
} from '../lib/gameStartPersistence'
import { useAuthStore } from '../stores/authStore'
import {
  currentEntrySupply,
  type EntrySupply,
  type PreparingReadDetail,
} from './GameScreenEntryTypes'

export type GameStartPhase =
  | 'loading'
  | 'ready'
  | 'sending'
  | 'unknown'
  | 'received'
  | 'failed'
  | 'unavailable'
export interface GameStartView {
  phase: GameStartPhase
  deviceReady: boolean
  savedRequest: boolean
  startedAt: string | null
  message: string
}
export type GameStartLineups = Pick<GameStartRequest, 'away' | 'home'>

/** 開始要求の耐久保存・輸送・応答保存を順序付ける。現在の記録権を認定しない。 */
export function useGameStartProvider(
  preparing: Readonly<Ref<EntrySupply<PreparingReadDetail> | null>>,
) {
  const auth = useAuthStore(pinia)
  const route = useRoute()
  const state = shallowRef<GameStartView>({
    phase: 'loading',
    deviceReady: false,
    savedRequest: false,
    startedAt: null,
    message: '開始データを確認しています',
  })
  const online = shallowRef(navigator.onLine === true)
  let generation = 0
  let disposed = false
  let database: GameStartPersistence | null = null
  let device: InitialDeviceEnrollmentResponse | null = null
  let saved: StoredGameStart | null = null
  let active: AbortController | null = null

  function scope() {
    const id = route.params.gameId
    if (
      disposed ||
      getActivePinia() !== pinia ||
      !auth.hasHydrated ||
      !auth.isAuthenticated ||
      auth.teamId === null ||
      !canonicalUuid.test(auth.teamId) ||
      typeof id !== 'string' ||
      !canonicalUuid.test(id) ||
      route.path !== `/games/${id}/record`
    )
      return null
    return {
      tenant: auth.teamId,
      game: id,
      epoch: auth.authEpoch,
      path: route.path,
      generation,
    }
  }
  type Scope = NonNullable<ReturnType<typeof scope>>
  function current(expected: Scope) {
    const now = scope()
    return (
      now !== null &&
      now.tenant === expected.tenant &&
      now.game === expected.game &&
      now.epoch === expected.epoch &&
      now.path === expected.path &&
      now.generation === expected.generation
    )
  }
  function publish(phase: GameStartPhase, message: string) {
    state.value = {
      phase,
      message,
      deviceReady: device !== null,
      savedRequest: saved !== null,
      startedAt: saved?.grant?.started_at ?? null,
    }
  }
  function showSaved() {
    if (saved?.status === 'received') {
      publish('received', '前回受領した開始応答です。現在の記録権は未確認です')
    } else if (saved !== null) {
      publish(
        'unknown',
        '保存した開始要求の結果は未確認です。同じ要求の結果を確認してください',
      )
    } else {
      publish(
        'ready',
        device === null ? 'この端末の登録が必要です' : '開始入力を確認できます',
      )
    }
  }
  const preparingReady = computed(() => {
    const expected = scope()
    if (expected === null) return false
    const supplied = currentEntrySupply(
      preparing.value,
      auth,
      route,
      expected.game,
    )
    const detail = supplied?.data
    return (
      supplied?.status === 'ready' &&
      detail !== undefined &&
      detail.tenantId === expected.tenant &&
      detail.gameId === expected.game &&
      isPreparingGame(detail.saved) &&
      detail.saved.id === expected.game
    )
  })
  const canEnroll = computed(
    () =>
      scope() !== null &&
      online.value &&
      state.value.phase === 'ready' &&
      !state.value.deviceReady &&
      !state.value.savedRequest,
  )
  const canStart = computed(
    () =>
      scope() !== null &&
      online.value &&
      preparingReady.value &&
      state.value.phase === 'ready' &&
      state.value.deviceReady &&
      !state.value.savedRequest,
  )
  const canResolve = computed(
    () =>
      scope() !== null &&
      online.value &&
      state.value.phase === 'unknown' &&
      state.value.savedRequest,
  )

  async function initialize() {
    generation += 1
    active?.abort()
    active = null
    database?.close()
    database = null
    device = null
    saved = null
    const expected = scope()
    if (expected === null) {
      publish('unavailable', 'ログイン状態と試合を確認してください')
      return
    }
    publish('loading', '開始データを確認しています')
    let opened: GameStartPersistence | null = null
    try {
      opened = await GameStartPersistence.open()
      if (!current(expected)) return
      const [pair, request] = await Promise.all([
        opened.readDevice(expected.tenant),
        opened.readStart(expected.tenant, expected.game),
      ])
      if (!current(expected)) return
      database = opened
      opened = null
      device = pair
      saved = request
      showSaved()
    } catch {
      if (current(expected))
        publish('failed', '開始データを保存・復元できません。送信していません')
    } finally {
      opened?.close()
    }
  }

  async function enroll() {
    const expected = scope()
    const storage = database
    if (!canEnroll.value || expected === null || storage === null) return
    publish('sending', 'この端末を登録しています')
    const controller = new AbortController()
    active = controller
    try {
      const previous = await storage.readDevice(expected.tenant)
      if (!current(expected)) return
      if (previous !== null) {
        device = previous
        showSaved()
        return
      }
      const result = await enrollInitialDevice(
        expected.tenant,
        controller.signal,
      )
      if (!current(expected)) return
      await storage.rememberDevice(result, expected.tenant)
      if (!current(expected)) return
      device = result
      showSaved()
    } catch {
      if (current(expected))
        publish(
          'failed',
          '端末登録・保存の結果を確認できません。自動再登録は行いません',
        )
    } finally {
      if (active === controller) active = null
    }
  }

  async function exchange(
    expected: Scope,
    storage: GameStartPersistence,
    request: StoredGameStart,
    resolve: boolean,
  ) {
    const controller = new AbortController()
    active = controller
    try {
      if (!current(expected)) return
      if (!online.value) {
        showSaved()
        return
      }
      const send = resolve ? resolveInitialGameStart : startInitialGame
      const result = await send(
        request.owner,
        request.request,
        controller.signal,
      )
      if (!current(expected)) return
      const received = await storage.rememberGrant(request.owner, result)
      if (!current(expected)) return
      saved = received
      publish('received', '開始応答を保存しました。記録の準備はまだ未確認です')
    } catch {
      // 送信断/認証切替/保存失敗をrollbackとせず、元要求は必ず残す。
      if (!current(expected)) return
      try {
        const unknown = await storage.markUnknown(request.owner)
        if (!current(expected)) return
        saved = unknown
        showSaved()
      } catch {
        if (current(expected))
          publish(
            'failed',
            '開始結果を保存できません。元要求を保持し、新しい開始要求は送信しません',
          )
      }
    } finally {
      if (active === controller) active = null
    }
  }

  async function start(lineups: GameStartLineups) {
    const expected = scope()
    const storage = database
    const pair = device
    if (
      !canStart.value ||
      expected === null ||
      storage === null ||
      pair === null
    )
      return
    publish('sending', '開始要求を保存しています')
    try {
      const previous = await storage.readStart(expected.tenant, expected.game)
      if (!current(expected)) return
      if (previous !== null) {
        saved = previous
        showSaved()
        return
      }
      const request = parseGameStartRequest({
        start_request_id: crypto.randomUUID(),
        device_id: pair.device_id,
        device_credential: pair.device_credential,
        away: lineups.away,
        home: lineups.home,
      })
      if (!current(expected)) return
      if (!online.value || !preparingReady.value) {
        showSaved()
        return
      }
      const prepared = await storage.prepareStart(
        expected.tenant,
        expected.game,
        request,
      )
      if (!current(expected)) return
      saved = prepared
      if (prepared.status === 'received') {
        showSaved()
        return
      }
      // prepareStartのtransaction完了後だけ、保存された原要求そのものを送る。
      await exchange(expected, storage, prepared, false)
    } catch {
      if (current(expected))
        publish(
          'failed',
          '開始要求を保存できません。新しい要求は送信していません',
        )
    }
  }

  async function resolve() {
    const expected = scope()
    const storage = database
    const request = saved
    if (
      !canResolve.value ||
      expected === null ||
      storage === null ||
      request === null
    )
      return
    publish('sending', '保存した開始要求の結果を確認しています')
    await exchange(expected, storage, request, true)
  }

  function connectivity() {
    online.value = navigator.onLine === true
    if (!online.value) active?.abort()
  }
  window.addEventListener('online', connectivity)
  window.addEventListener('offline', connectivity)
  watch(
    () => [
      auth.authEpoch,
      auth.teamId,
      auth.isAuthenticated,
      auth.hasHydrated,
      route.path,
      route.params.gameId,
    ],
    () => {
      void initialize()
    },
    { immediate: true, flush: 'sync' },
  )
  onScopeDispose(() => {
    disposed = true
    generation += 1
    active?.abort()
    database?.close()
    device = null
    saved = null
    window.removeEventListener('online', connectivity)
    window.removeEventListener('offline', connectivity)
  })
  return {
    state: readonly(state),
    canEnroll,
    canStart,
    canResolve,
    enroll,
    start,
    resolve,
  }
}
