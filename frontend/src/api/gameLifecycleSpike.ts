import { apiRequest, type SyncRequestCredentials } from './client'

/** 終了・再開spikeの GET 応答。書込み結果ではない。 */
export type GameLifecycleRead = Readonly<{
  gameId: string
  status: 'in_progress' | 'finished'
  generation: number
  d4: string
  watermark: number
  nextD1: number
  nextD2: number
  truncated: boolean
  stateDigest: string
  currentState: Readonly<{
    stateFields: Readonly<Record<string, unknown>>
    scoreboard: Readonly<Record<string, unknown>>
    battingOrderBySide?: Readonly<Record<string, unknown>>
  }>
  activeFinalization: GameLifecycleFinalization | null
  nextFinalization: Readonly<{
    version: number
    previous: Readonly<{ version: number; d1: number }> | null
  }> | null
  finalizations: readonly GameLifecycleFinalization[]
  events: readonly Readonly<{
    d1: number
    d5: string
    eventKind: string
    action: 'end' | 'reopen' | null
    version: number | null
    targetD1: number | null
  }>[]
}>

export type GameLifecycleFinalization = Readonly<{
  version: number
  d1: number
  d5: string
  state: Readonly<Record<string, unknown>>
  stateDigest: string
  finalizationDigest: string
  invalidatedBy: Readonly<{ d1: number; d5: string }> | null
}>

type LifecycleState = GameLifecycleRead['currentState']

type LifecyclePayload =
  | Readonly<{
      formatVersion: 'game-lifecycle-spike-v1'
      action: 'end'
      finalization: Readonly<{
        version: number
        previous: Readonly<{ version: number; d1: number }> | null
        state: LifecycleState
      }>
    }>
  | Readonly<{
      formatVersion: 'game-lifecycle-spike-v1'
      action: 'reopen'
      finalization: Readonly<{
        version: number
        target: Readonly<{ version: number; d1: number }>
        state: LifecycleState
      }>
    }>

export type GameLifecycleResult =
  | Readonly<{ sent: true; a5Result: string; response: unknown }>
  | Readonly<{ sent: false; reason: string }>

/** 実認証済みtenantで、保存済みイベントから終了確定版を取得する。 */
export function readGameLifecycle(
  gameId: string,
  signal?: AbortSignal,
): Promise<GameLifecycleRead> {
  return apiRequest<GameLifecycleRead>(
    'GET',
    `/spike/games/${encodeURIComponent(gameId)}/lifecycle`,
    { tenantBound: true, signal },
  )
}

/**
 * 終了または再開の spike payload を、既存の正式同期入口へ 1 件送る。
 *
 * クライアントの `checkSyncEvent` は V5 に画面用の種別 ID を要求するが、
 * 正式 wire の `game_end_declaration` は文字列リテラルである。ここでは
 * wire を直接組み、サーバーの閉じた検査を正とする。
 */
export async function postGameLifecycle(
  gameId: string,
  request: Readonly<{
    d4: string
    d1: number
    d2: number
    recordingRightProof: string
    payload: LifecyclePayload
    syncCredentials: SyncRequestCredentials
  }>,
): Promise<GameLifecycleResult> {
  const d5 = crypto.randomUUID()
  let response: unknown
  try {
    response = await apiRequest<unknown>(
      'POST',
      `/games/${gameId}/sync/events`,
      {
        body: {
          recording_right_proof: request.recordingRightProof,
          events: [
            {
              d5,
              d1: request.d1,
              d4: request.d4,
              game_id: gameId,
              event_kind: 'game_end_declaration',
              d2: request.d2,
              payload: request.payload,
            },
          ],
        },
        syncCredentials: request.syncCredentials,
      },
    )
  } catch {
    return { sent: false, reason: 'network-or-http' }
  }
  const records =
    typeof response === 'object' &&
    response !== null &&
    'eventResults' in response &&
    Array.isArray(response.eventResults)
      ? response.eventResults
      : []
  const first =
    records.length === 1 && typeof records[0] === 'object' ? records[0] : null
  const a5 =
    first !== null && 'a5Result' in first && typeof first.a5Result === 'string'
      ? first.a5Result
      : null
  if (a5 === null) {
    return { sent: false, reason: 'ack-shape' }
  }
  return { sent: true, a5Result: a5, response }
}

/** 終了 payload を現在状態と次の版から組み立てる。 */
export function endPayload(
  lifecycle: GameLifecycleRead,
): LifecyclePayload | null {
  if (lifecycle.status !== 'in_progress' || lifecycle.nextFinalization === null)
    return null
  return {
    formatVersion: 'game-lifecycle-spike-v1',
    action: 'end',
    finalization: {
      version: lifecycle.nextFinalization.version,
      previous: lifecycle.nextFinalization.previous,
      state: lifecycle.currentState,
    },
  }
}

/** 再開 payload を有効な終了確定版から組み立てる。 */
export function reopenPayload(
  lifecycle: GameLifecycleRead,
): LifecyclePayload | null {
  const active = lifecycle.activeFinalization
  if (lifecycle.status !== 'finished' || active === null) return null
  return {
    formatVersion: 'game-lifecycle-spike-v1',
    action: 'reopen',
    finalization: {
      version: active.version,
      target: { version: active.version, d1: active.d1 },
      state: lifecycle.currentState,
    },
  }
}
