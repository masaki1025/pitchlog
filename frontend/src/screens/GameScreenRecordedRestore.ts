import {
  readLineupPrefixGame,
  type LineupPrefixGame,
} from '../api/lineupPrefixGame'
import { ApiError, ApiNetworkError } from '../api/client'
import {
  readRecordedPrefixGame,
  readPlayPrefixGame,
  type PlayPrefixGame,
  type RecordedPrefixGame,
} from '../api/recordedPrefixGame'
import type { OrdinaryHistoryEntry } from '../api/ordinaryPitchWire'
import { ref, watch, type Ref } from 'vue'
import {
  readStartedGame,
  type StartedGameRead,
  type StartedHistoryEntry,
} from '../api/startedGame'
import type { StateSnapshot } from '../../../contracts/state-transition/t2_first_pitch_continuation_v1'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import {
  readLineupOfflineSeed,
  saveLineupOfflineSeed,
} from '../lib/lineupOfflineSeedPersistence'
import { useAuthStore } from '../stores/authStore'
import { lineupContextFromRead } from './GameScreenOrdinaryPitchProvider'

export type RecordingGameRead =
  StartedGameRead | RecordedPrefixGame | PlayPrefixGame | LineupPrefixGame

export type RecordedRestoreStatus =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'offline-ready'
  | 'seed-unavailable'
  | 'not-found'
  | 'unavailable'
  | 'failed'

/** 記録画面の再読込で、サーバーの開始済み/記録済み状態だけを復元する。 */
export function useRecordedRestore(
  gameId: Ref<string | undefined>,
  auto: Ref<boolean | undefined>,
  legacy: Ref<boolean> = ref(false),
  projection: Ref<'play-prefix-v3' | null | 'invalid'> = ref(null),
) {
  const auth = useAuthStore()
  const status = ref<RecordedRestoreStatus>('idle')
  const game = ref<RecordingGameRead | null>(null)
  const message = ref('')
  let sequence = 0
  let confirmedEpoch: number | null = null

  async function savedStartExists(id: string): Promise<boolean> {
    const tenant = auth.teamId
    if (tenant === null) return false
    let store: GameStartPersistence | null = null
    try {
      store = await GameStartPersistence.open()
      return (await store.readStart(tenant, id)) !== null
    } catch {
      return false
    } finally {
      store?.close()
    }
  }

  async function receivedStartExists(id: string): Promise<boolean> {
    const tenant = auth.teamId
    if (tenant === null) return false
    let store: GameStartPersistence | null = null
    try {
      store = await GameStartPersistence.open()
      const start = await store.readStart(tenant, id)
      return start?.status === 'received' && start.grant !== null
    } catch {
      return false
    } finally {
      store?.close()
    }
  }

  function authReady(): boolean {
    return auth.hasHydrated && auth.isAuthenticated && auth.teamId !== null
  }

  async function load(): Promise<void> {
    const id = gameId.value
    const epoch = auth.authEpoch
    if (!id || !authReady()) {
      status.value = 'idle'
      game.value = null
      message.value = ''
      return
    }
    if (projection.value === 'invalid') {
      ++sequence
      game.value = null
      status.value = 'failed'
      message.value = '記録の入口を確認してください'
      return
    }
    const retained =
      confirmedEpoch === epoch &&
      (game.value?.read_kind === 'recorded-prefix' ||
        game.value?.read_kind === 'play-prefix' ||
        game.value?.read_kind === 'lineup-prefix') &&
      game.value.id === id &&
      (projection.value === 'play-prefix-v3'
        ? game.value.read_kind === 'lineup-prefix'
        : game.value.read_kind !== 'lineup-prefix') &&
      game.value.prefix_ref.tenantId === auth.teamId
        ? game.value
        : null
    const request = ++sequence
    status.value = 'loading'
    game.value = retained
    message.value = 'サーバーの記録を取得しています'
    try {
      if (projection.value === 'play-prefix-v3') {
        const read = await readLineupPrefixGame(id)
        if (request !== sequence || auth.authEpoch !== epoch) return
        if (read.kind === 'found') {
          if (read.game.prefix_ref.tenantId !== auth.teamId)
            throw new Error('記録のtenantを確認できません')
          if (read.game.prefix_ref.length === '0') {
            message.value =
              '開始は受理済みです。断中入力用の開始状態を保存しています'
            try {
              await lineupContextFromRead(read.game, auth.teamId!)
              await saveLineupOfflineSeed(read.game, auth.teamId!)
            } catch {
              if (request !== sequence || auth.authEpoch !== epoch) return
              game.value = read.game
              status.value = 'seed-unavailable'
              message.value =
                '開始は受理済みです。断中入力の準備は未完了です。サーバーから再取得してください'
              return
            }
            if (request !== sequence || auth.authEpoch !== epoch) return
          }
          confirmedEpoch = epoch
          game.value = read.game
          status.value = 'ready'
          message.value = `サーバーの記録を取得しました。最終保存: ${read.game.last_saved_at}`
        } else {
          game.value = null
          status.value = read.kind === 'not-found' ? 'not-found' : 'unavailable'
          message.value = 'この記録入口ではサーバーの記録を取得できません'
        }
        return
      }
      // 通常記録の読取を旧初球専用readerの成功に従属させない。
      // 明示unsupportedだけ旧ABIへ戻し、拒否/故障/破損は代替成功にしない。
      const play = legacy.value
        ? { kind: 'unsupported' as const }
        : await readPlayPrefixGame(id)
      if (request !== sequence || auth.authEpoch !== epoch) return
      if (play.kind === 'found') {
        if (play.game.prefix_ref.tenantId !== auth.teamId)
          throw new Error('記録のtenantを確認できません')
        confirmedEpoch = epoch
        game.value = play.game
        status.value = 'ready'
        message.value = `サーバーの記録を取得しました。最終保存: ${play.game.last_saved_at}`
        return
      }
      if (play.kind !== 'unsupported') {
        game.value = null
        status.value = play.kind === 'not-found' ? 'not-found' : 'unavailable'
        message.value = 'サーバーの記録を取得できません'
        return
      }
      const prefix = await readRecordedPrefixGame(id)
      if (request !== sequence || auth.authEpoch !== epoch) return
      if (prefix.kind === 'found') {
        if (prefix.game.prefix_ref.tenantId !== auth.teamId)
          throw new Error('記録のtenantを確認できません')
        confirmedEpoch = epoch
        game.value = prefix.game
        status.value = 'ready'
        message.value = `サーバー確認済みの通常投球prefix ${prefix.game.prefix_ref.length}を取得しました。最終保存: ${prefix.game.last_saved_at}`
        return
      }
      if (prefix.kind !== 'unsupported') {
        game.value = null
        status.value = prefix.kind === 'not-found' ? 'not-found' : 'unavailable'
        message.value =
          prefix.kind === 'not-found'
            ? 'この試合は取得できません'
            : 'サーバーの通常投球prefixを取得できません'
        return
      }
      const result = await readStartedGame(id)
      // 認証世代・要求順が変わった応答は採用しない。
      if (request !== sequence || auth.authEpoch !== epoch) return
      if (result.kind === 'found') {
        game.value = result.game
        confirmedEpoch = epoch
        status.value = 'ready'
        message.value =
          result.game.read_kind === 'recorded'
            ? 'サーバーの記録（初球1件）を取得しました'
            : 'サーバーの開始済み状態を取得しました'
        return
      }
      game.value = null
      if (result.kind === 'not-found') {
        status.value = 'not-found'
        message.value = 'この試合は取得できません'
      } else {
        status.value = 'unavailable'
        message.value = '初球1件として返せない記録です'
      }
    } catch (error) {
      if (request !== sequence || auth.authEpoch !== epoch) return
      if (
        projection.value === 'play-prefix-v3' &&
        auth.teamId !== null &&
        (error instanceof ApiNetworkError ||
          (typeof error === 'object' &&
            error !== null &&
            'name' in error &&
            error.name === 'AbortError'))
      ) {
        try {
          const seed = await readLineupOfflineSeed(auth.teamId, id)
          if (request !== sequence || auth.authEpoch !== epoch || !authReady())
            return
          if (seed !== null) {
            await lineupContextFromRead(seed, auth.teamId)
            if (
              request !== sequence ||
              auth.authEpoch !== epoch ||
              !authReady()
            )
              return
            game.value = seed
            status.value = 'offline-ready'
            message.value =
              '通信断中です。開始時に確認した状態と端末の未同期列から記録を続けます。最新のサーバー状態ではありません'
            return
          }
        } catch {
          if (request !== sequence || auth.authEpoch !== epoch) return
        }
        if (await receivedStartExists(id)) {
          if (request !== sequence || auth.authEpoch !== epoch || !authReady())
            return
          game.value = null
          status.value = 'seed-unavailable'
          message.value =
            '開始は受理済みです。断中入力の準備は未完了です。通信復帰後に開始状態を再取得してください'
          return
        }
      }
      if (
        retained &&
        (error instanceof TypeError ||
          (error instanceof ApiError &&
            (error.status >= 500 || error.status === 429)))
      ) {
        game.value = retained
        status.value = 'failed'
        message.value = `未更新: 最後に確認した保存日時: ${retained.last_saved_at}。サーバー再取得を確認してください`
        return
      }
      game.value = null
      status.value = 'failed'
      message.value = 'サーバーの記録を取得できません'
    }
  }

  // 明示入口を変えた時は、auto=falseでも旧要求/所有者を引き継がない。
  watch(projection, () => {
    ++sequence
    confirmedEpoch = null
    game.value = null
    status.value = 'idle'
    message.value = ''
  })

  watch(
    [
      auto,
      legacy,
      gameId,
      () => auth.authEpoch,
      () => auth.isAuthenticated,
      () => auth.hasHydrated,
      () => auth.teamId,
      () => projection.value,
    ] as const,
    () => {
      // 端末がこの試合を開始した記録（保存開始応答）がある時だけ自動復元する。
      // 見えない試合への /started 呼出しを増やさない。
      const forced = auto.value
      if (forced === false) return
      if (forced === true) {
        void load()
        return
      }
      const id = gameId.value
      if (!id || !authReady()) return
      void savedStartExists(id).then((exists) => {
        if (exists && auto.value !== false) void load()
      })
    },
    { immediate: true },
  )
  return {
    status,
    game,
    message,
    reload: load,
    loadOrdinary: async () => {
      await load()
    },
  }
}

/** 現在状態。記録済みはafter、開始済みはstate（before）を使う。 */
export function currentState(
  game: RecordingGameRead,
): StateSnapshot | PlayPrefixGame['after'] {
  return game.read_kind === 'initial' ? game.state : game.after
}

/** 開始前の状態。記録済みでも初期状態へ戻さないため別に表示する。 */
export function beforeState(
  game: RecordingGameRead,
): StateSnapshot | PlayPrefixGame['after'] {
  return game.state
}

/** 保存済み履歴の件数。開始済み（記録前）は0。 */
export function historyCount(game: RecordingGameRead): number | string {
  if (
    game.read_kind === 'recorded-prefix' ||
    game.read_kind === 'play-prefix' ||
    game.read_kind === 'lineup-prefix'
  )
    return game.prefix_ref.length
  return game.read_kind === 'recorded' ? game.history.length : 0
}

/** 保存済みPlayRowの件数。開始済み（記録前）は0。 */
export function playCount(game: RecordingGameRead): number {
  if (
    game.read_kind === 'recorded-prefix' ||
    game.read_kind === 'play-prefix' ||
    game.read_kind === 'lineup-prefix'
  )
    return game.page.items.length
  return game.read_kind === 'recorded' ? game.play_rows.length : 0
}

/** 履歴の先頭1件を、表示用の閉じた値として返す。 */
export function firstHistory(
  game: RecordingGameRead,
):
  | StartedHistoryEntry
  | OrdinaryHistoryEntry
  | PlayPrefixGame['last_entry']
  | LineupPrefixGame['last_entry']
  | null {
  if (
    game.read_kind === 'recorded-prefix' ||
    game.read_kind === 'play-prefix' ||
    game.read_kind === 'lineup-prefix'
  )
    return game.last_entry
  return game.read_kind === 'recorded' ? (game.history[0] ?? null) : null
}
