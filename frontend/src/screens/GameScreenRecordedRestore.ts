import { ApiError } from '../api/client'
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
import { useAuthStore } from '../stores/authStore'

export type RecordingGameRead =
  StartedGameRead | RecordedPrefixGame | PlayPrefixGame

export type RecordedRestoreStatus =
  'idle' | 'loading' | 'ready' | 'not-found' | 'unavailable' | 'failed'

/** 記録画面の再読込で、サーバーの開始済み/記録済み状態だけを復元する。 */
export function useRecordedRestore(
  gameId: Ref<string | undefined>,
  auto: Ref<boolean | undefined>,
  legacy: Ref<boolean> = ref(false),
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
    const retained =
      confirmedEpoch === epoch &&
      (game.value?.read_kind === 'recorded-prefix' ||
        game.value?.read_kind === 'play-prefix') &&
      game.value.id === id &&
      game.value.prefix_ref.tenantId === auth.teamId
        ? game.value
        : null
    const request = ++sequence
    status.value = 'loading'
    game.value = retained
    message.value = 'サーバーの記録を取得しています'
    try {
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

  watch(
    [
      auto,
      legacy,
      gameId,
      () => auth.authEpoch,
      () => auth.isAuthenticated,
      () => auth.hasHydrated,
      () => auth.teamId,
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
  if (game.read_kind === 'recorded-prefix' || game.read_kind === 'play-prefix')
    return game.prefix_ref.length
  return game.read_kind === 'recorded' ? game.history.length : 0
}

/** 保存済みPlayRowの件数。開始済み（記録前）は0。 */
export function playCount(game: RecordingGameRead): number {
  if (game.read_kind === 'recorded-prefix' || game.read_kind === 'play-prefix')
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
  | null {
  if (game.read_kind === 'recorded-prefix' || game.read_kind === 'play-prefix')
    return game.last_entry
  return game.read_kind === 'recorded' ? (game.history[0] ?? null) : null
}
