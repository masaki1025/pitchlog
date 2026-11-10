/** 閲覧画面の版照会・有限page取得・鮮度状態を一つのcontrollerへ閉じる。 */
import { canonicalUuid } from '../api/authIntent'
import {
  readViewerGame,
  readViewerHead,
  viewerFailure,
  type ViewerGame,
  type ViewerHead,
} from '../api/viewerGame'

export type ViewerFreshness = 'loading' | 'fresh' | 'unupdated' | 'not-found'

/** 認証世代・tenant・gameを一組にし、古い応答の適用を防ぐ。 */
export type ViewerLiveIdentity = Readonly<{
  authenticated: boolean
  tenantId: string | null
  authEpoch: number
  gameId: string
}>

export type ViewerLiveState = Readonly<{
  game: ViewerGame | null
  head: ViewerHead | null
  freshness: ViewerFreshness
  refreshing: boolean
  checkedAt: number | null
  pageCursors: readonly (string | null)[]
}>

export type ViewerLiveControllerOptions = Readonly<{
  onChange: (state: ViewerLiveState) => void
  readHead?: (gameId: string, signal?: AbortSignal) => Promise<ViewerHead>
  readGame?: (
    gameId: string,
    tenantId: string,
    head: ViewerHead,
    cursor?: string | null,
    signal?: AbortSignal,
  ) => Promise<ViewerGame>
  now?: () => number
  pollMs?: number
  staleMs?: number
}>

const initial = (): ViewerLiveState => ({
  game: null,
  head: null,
  freshness: 'loading',
  refreshing: false,
  checkedAt: null,
  pageCursors: [null],
})

/** 同一tenant・認証世代・gameだけを閲覧対象にする。 */
export function viewerIdentityValid(identity: ViewerLiveIdentity): boolean {
  return (
    identity.authenticated &&
    identity.tenantId !== null &&
    canonicalUuid.test(identity.tenantId) &&
    canonicalUuid.test(identity.gameId)
  )
}

function sameIdentity(
  left: ViewerLiveIdentity,
  right: ViewerLiveIdentity,
): boolean {
  return (
    left.authenticated === right.authenticated &&
    left.tenantId === right.tenantId &&
    left.authEpoch === right.authEpoch &&
    left.gameId === right.gameId
  )
}

/** 表示状態を文言へ閉じ、未取得を更新済みへ読み替えない。 */
export function viewerStatusLabel(
  freshness: ViewerFreshness,
  refreshing: boolean,
): string {
  if (freshness === 'loading') return '確認中'
  if (freshness === 'not-found') return '閲覧できません'
  if (freshness === 'unupdated') return '未更新'
  return refreshing ? '更新中' : '更新済み'
}

/** 最終成功から10秒を超えた表示を未更新へ降ろす判定。 */
export function viewerIsStale(
  checkedAt: number | null,
  now: number,
  staleMs: number,
): boolean {
  return checkedAt !== null && now - checkedAt > staleMs
}

/** 保存済み表示の値だけを返し、記録端末の未送信値を混ぜない。 */
export function viewerCurrent(game: ViewerGame | null) {
  return game?.after.stateFields ?? null
}

export function viewerLineup(game: ViewerGame | null) {
  if (game === null) return null
  return game.read_kind === 'lineup-prefix'
    ? game.lineup
    : (game.checkpoint.content.restored.lineup ?? null)
}

export function viewerRunners(game: ViewerGame | null) {
  if (game === null) return []
  return game.read_kind === 'lineup-prefix'
    ? game.runners
    : (game.checkpoint.content.restored.runners ?? [])
}

export function viewerSavedAt(game: ViewerGame | null): string | null {
  return game?.last_saved_at ?? null
}

export function viewerNextCursor(game: ViewerGame | null): string | null {
  return game?.page.next_cursor ?? null
}

/** 現行v3/非playの双方とも、最新pageから旧pageへ進む。 */
export function viewerPageLabels(game: ViewerGame | null): {
  next: string
  previous: string
} {
  return game?.read_kind === 'lineup-prefix'
    ? { next: '古い25球へ', previous: '新しい25球へ' }
    : { next: '古い25球へ', previous: '新しい25球へ' }
}

export function viewerHistory(game: ViewerGame | null) {
  if (game === null) return []
  return game.read_kind === 'lineup-prefix'
    ? game.page.items.map((item) => ({
        key: item.play_row.id,
        number: String(item.play_row.play_number),
        result: item.play_row.batting_result_key,
      }))
    : game.page.items.map((item) => ({
        key: item.play.playId,
        number: item.play.physicalPlayNumber,
        result: '確定済みの投球',
      }))
}

/** 終了済みは保存T2の完了半回を優先し、次の半回を開始扱いしない。 */
export function viewerPeriodLabel(game: ViewerGame | null): string | null {
  if (game === null) return null
  const state = game.after.stateFields
  const half = (value: 'top' | 'bottom') => (value === 'top' ? '表' : '裏')
  const t2 =
    game.read_kind === 'lineup-prefix'
      ? game.t2
      : game.checkpoint.content.restored.lastPlayEvaluation
  if (game.status === 'finished') {
    if (t2?.facts.halfCompleted)
      return `試合終了（${t2.facts.beforeInning}回${half(t2.facts.beforeHalf)}終了）`
    return `試合終了（最終保存時 ${state['state.inning']}回${half(state['state.half'])}）`
  }
  return `${state['state.inning']}回${half(state['state.half'])}`
}

export class GameScreenViewerLiveController {
  #readIdentity: () => ViewerLiveIdentity
  #options: Required<
    Pick<
      ViewerLiveControllerOptions,
      'onChange' | 'readHead' | 'readGame' | 'now' | 'pollMs' | 'staleMs'
    >
  >
  #state: ViewerLiveState = initial()
  #identity: ViewerLiveIdentity | null = null
  #mounted = false
  #runId = 0
  #request: AbortController | null = null
  #pollTimer: ReturnType<typeof setTimeout> | null = null
  #staleTimer: ReturnType<typeof setInterval> | null = null

  constructor(
    readIdentity: () => ViewerLiveIdentity,
    options: ViewerLiveControllerOptions,
  ) {
    this.#readIdentity = readIdentity
    this.#options = {
      onChange: options.onChange,
      readHead: options.readHead ?? readViewerHead,
      readGame: options.readGame ?? readViewerGame,
      now: options.now ?? Date.now,
      pollMs: options.pollMs ?? 5000,
      staleMs: options.staleMs ?? 10000,
    }
  }

  get state(): ViewerLiveState {
    return this.#state
  }

  #emit(): void {
    this.#options.onChange(this.#state)
  }

  #clearTimers(): void {
    if (this.#pollTimer !== null) clearTimeout(this.#pollTimer)
    this.#pollTimer = null
  }

  #cancel(): void {
    this.#runId += 1
    this.#request?.abort()
    this.#request = null
    this.#clearTimers()
  }

  #reset(freshness: ViewerFreshness): void {
    this.#state = {
      game: null,
      head: null,
      freshness,
      refreshing: false,
      checkedAt: null,
      pageCursors: [null],
    }
    this.#emit()
  }

  /** 認証世代またはgameが変わった時だけ旧表示を破棄して再取得する。 */
  resetAndLoad(): void {
    const identity = this.#readIdentity()
    if (this.#identity !== null && sameIdentity(this.#identity, identity))
      return
    this.#cancel()
    this.#identity = identity
    if (this.#mounted && !viewerIdentityValid(identity)) {
      this.#reset('not-found')
      return
    }
    this.#reset('loading')
    if (this.#mounted) void this.#load(true)
  }

  start(): void {
    if (this.#mounted) return
    this.#mounted = true
    this.#staleTimer = setInterval(() => {
      if (
        this.#state.freshness === 'fresh' &&
        viewerIsStale(
          this.#state.checkedAt,
          this.#options.now(),
          this.#options.staleMs,
        )
      ) {
        this.#cancel()
        this.#reset('unupdated')
        this.#schedule()
      }
    }, 1000)
    this.resetAndLoad()
  }

  stop(): void {
    this.#mounted = false
    this.#cancel()
    if (this.#staleTimer !== null) clearInterval(this.#staleTimer)
    this.#staleTimer = null
    this.#identity = null
  }

  /** 自動pollまたは明示再試行。forceは同一版でも本体を取り直す。 */
  reload(force = false): void {
    if (!this.#mounted || !viewerIdentityValid(this.#readIdentity())) return
    void this.#load(force)
  }

  #schedule(): void {
    this.#clearTimers()
    if (this.#mounted && viewerIdentityValid(this.#readIdentity()))
      this.#pollTimer = setTimeout(() => this.reload(), this.#options.pollMs)
  }

  async #load(force: boolean): Promise<void> {
    const identity = this.#readIdentity()
    if (!this.#mounted || !viewerIdentityValid(identity)) return
    const currentRun = ++this.#runId
    this.#request?.abort()
    const controller = new AbortController()
    this.#request = controller
    this.#state = { ...this.#state, refreshing: true }
    this.#emit()
    try {
      const nextHead = await this.#options.readHead(
        identity.gameId,
        controller.signal,
      )
      if (currentRun !== this.#runId || !this.#stillCurrent(identity)) return
      const changed =
        this.#state.head === null ||
        this.#state.head.status !== nextHead.status ||
        this.#state.head.version !== nextHead.version ||
        this.#state.head.watermark !== nextHead.watermark
      if (changed) {
        this.#state = {
          ...this.#state,
          game: null,
          head: null,
          freshness: this.#state.checkedAt === null ? 'loading' : 'unupdated',
          checkedAt: null,
          pageCursors: [null],
        }
        this.#emit()
      }
      if (changed || force || this.#state.game === null) {
        const nextGame = await this.#options.readGame(
          identity.gameId,
          identity.tenantId!,
          nextHead,
          this.#state.pageCursors.at(-1) ?? null,
          controller.signal,
        )
        if (currentRun !== this.#runId || !this.#stillCurrent(identity)) return
        this.#state = { ...this.#state, game: nextGame }
      }
      this.#state = {
        ...this.#state,
        head: nextHead,
        freshness: 'fresh',
        refreshing: false,
        checkedAt: this.#options.now(),
      }
      this.#emit()
    } catch (error) {
      if (currentRun !== this.#runId || !this.#stillCurrent(identity)) return
      this.#state = {
        game: null,
        head: null,
        freshness: viewerFailure(error),
        refreshing: false,
        checkedAt: null,
        pageCursors: [null],
      }
      this.#emit()
    } finally {
      if (currentRun === this.#runId) {
        this.#request = null
        this.#schedule()
      }
    }
  }

  #stillCurrent(identity: ViewerLiveIdentity): boolean {
    return this.#mounted && sameIdentity(this.#readIdentity(), identity)
  }

  nextPage(): void {
    const cursor = this.#state.game?.page.next_cursor ?? null
    if (
      cursor === null ||
      this.#state.refreshing ||
      this.#state.freshness !== 'fresh' ||
      this.#state.pageCursors.includes(cursor)
    )
      return
    this.#state = {
      ...this.#state,
      pageCursors: [...this.#state.pageCursors, cursor],
    }
    this.reload(true)
  }

  previousPage(): void {
    if (
      this.#state.pageCursors.length <= 1 ||
      this.#state.refreshing ||
      this.#state.freshness !== 'fresh'
    )
      return
    this.#state = {
      ...this.#state,
      pageCursors: this.#state.pageCursors.slice(0, -1),
    }
    this.reload(true)
  }
}
