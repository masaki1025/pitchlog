import { ref, watch, type Ref } from 'vue'
import {
  readStartedGame,
  type StartedGameRead,
  type StartedHistoryEntry,
} from '../api/startedGame'
import type { StateSnapshot } from '../../../contracts/state-transition/t2_first_pitch_continuation_v1'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { useAuthStore } from '../stores/authStore'

export type RecordedRestoreStatus =
  'idle' | 'loading' | 'ready' | 'not-found' | 'unavailable' | 'failed'

/** 記録画面の再読込で、サーバーの開始済み/記録済み状態だけを復元する。 */
export function useRecordedRestore(
  gameId: Ref<string | undefined>,
  auto: Ref<boolean | undefined>,
) {
  const auth = useAuthStore()
  const status = ref<RecordedRestoreStatus>('idle')
  const game = ref<StartedGameRead | null>(null)
  const message = ref('')
  let sequence = 0

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
    const request = ++sequence
    status.value = 'loading'
    game.value = null
    message.value = 'サーバーの記録を取得しています'
    try {
      const result = await readStartedGame(id)
      // 認証世代・要求順が変わった応答は採用しない（旧表示を最新にしない）。
      if (request !== sequence || auth.authEpoch !== epoch) return
      if (result.kind === 'found') {
        game.value = result.game
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
    } catch {
      if (request !== sequence || auth.authEpoch !== epoch) return
      game.value = null
      status.value = 'failed'
      message.value = 'サーバーの記録を取得できません'
    }
  }

  watch(
    [
      auto,
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
  return { status, game, message, reload: load }
}

/** 現在状態。記録済みはafter、開始済みはstate（before）を使う。 */
export function currentState(game: StartedGameRead): StateSnapshot {
  return game.read_kind === 'recorded' ? game.after : game.state
}

/** 開始前の状態。記録済みでも初期状態へ戻さないため別に表示する。 */
export function beforeState(game: StartedGameRead): StateSnapshot {
  return game.state
}

/** 保存済み履歴の件数。開始済み（記録前）は0。 */
export function historyCount(game: StartedGameRead): number {
  return game.read_kind === 'recorded' ? game.history.length : 0
}

/** 保存済みPlayRowの件数。開始済み（記録前）は0。 */
export function playCount(game: StartedGameRead): number {
  return game.read_kind === 'recorded' ? game.play_rows.length : 0
}

/** 履歴の先頭1件を、表示用の閉じた値として返す。 */
export function firstHistory(
  game: StartedGameRead,
): StartedHistoryEntry | null {
  return game.read_kind === 'recorded' ? (game.history[0] ?? null) : null
}
