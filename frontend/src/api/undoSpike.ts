import { apiRequest, type SyncRequestCredentials } from './client'

/** 取消spikeの再読込応答。状態は保存済みイベントの畳み込み結果。 */
export type UndoSpikeState = Readonly<{
  gameId: string
  generation: number
  d4: string
  watermark: number
  nextD1: number
  truncated: boolean
  state: Readonly<{
    stateFields: Readonly<Record<string, unknown>>
    scoreboard: Readonly<Record<string, unknown>>
    battingOrderBySide?: Readonly<Record<string, unknown>>
  }> | null
  history: readonly Readonly<{
    target: Readonly<{ game: string; d4: string; d1: number; d5: string }>
    entry: Readonly<Record<string, unknown>>
  }>[]
  undoTarget: Readonly<{
    game: string
    d4: string
    d1: number
    d5: string
  }> | null
  events: readonly Readonly<{
    d1: number
    d5: string
    eventKind: string
    targetD1: number | null
  }>[]
}>

export type UndoSpikeResult = Readonly<{
  operationResult: 'applied' | 'nothing-to-undo'
  after: Readonly<{
    stateFields: Readonly<Record<string, unknown>>
    scoreboard: Readonly<Record<string, unknown>>
    battingOrderBySide?: Readonly<Record<string, unknown>>
  }>
  historyEffect: Readonly<{ pops: string }>
  historyContext: readonly Readonly<Record<string, unknown>>[]
}>

export type UndoSpikeRequest = Readonly<{
  recording_right_proof: string
  d5: string
  d1: number
  target: Readonly<{ game: string; d4: string; d1: number }>
  payload: Readonly<{
    formatVersion: 'undo-connection-spike-v1'
    target: Readonly<{ game: string; d4: string; d1: number }>
    result: UndoSpikeResult
  }>
}>

/** 実認証済みtenantで、取消spikeの再読込状態を取得する。 */
export function readUndoSpikeState(
  gameId: string,
  signal?: AbortSignal,
): Promise<UndoSpikeState> {
  return apiRequest<UndoSpikeState>('GET', `/spike/games/${gameId}/state`, {
    tenantBound: true,
    signal,
  })
}

/** 実端末提示とV12を同じ要求へ載せ、取消を1件だけ保存する。 */
export function postUndoSpike(
  gameId: string,
  body: UndoSpikeRequest,
  credentials: SyncRequestCredentials,
  signal?: AbortSignal,
): Promise<unknown> {
  return apiRequest<unknown>('POST', `/spike/games/${gameId}/undo`, {
    tenantBound: true,
    body,
    syncCredentials: credentials,
    signal,
  })
}
