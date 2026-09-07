// このゲートは docs/design/sync-protocol.md 6-2・6-3 の RG1 の写しである。
// 射程は復元調整中の通常処理停止・停止境界・再検証契約に限る。
// 復元処理と新 D4 の生成自体は復旧制御面の責務であるため射程外とする。

import {
  readCanonBoundaryResults,
  readCanonP3BoundaryResults,
  type CanonProcessingStageRule,
} from './canonOracle'
import {
  D1_PROCESSING_STAGES,
  P3_PROCESSING_STAGES,
  type D1ProcessingStage,
  type P3ProcessingStage,
} from './processingStages'
import { RG1_STATE, type Rg1State } from './queueTransition'

export type RestoreAdjustmentGateRule = Readonly<{
  purpose: CanonProcessingStageRule['purpose']
  relationIds: readonly CanonProcessingStageRule['relationId'][]
  id: 'RG1'
  name: string
  clauses: readonly string[]
  rightHandSide: string
  failClosed: Readonly<{
    indeterminateState: 'stop'
    preCommitTransition: 'rollback-all'
    serviceRestartIndeterminate: 'keep-writes-closed'
    releaseAndNewGenerationStart: 'atomic'
    intermediateNormalWritesAllowed: false
    allowedControlPlane: 'recovery-only'
  }>
}>

export type RestoreAdjustmentGatePosition = Readonly<{
  d1: Readonly<{
    authorization: D1ProcessingStage
    restoreGate: D1ProcessingStage
    d5Verification: D1ProcessingStage
  }>
  p3: Readonly<{
    authorization: P3ProcessingStage
    restoreGate: P3ProcessingStage
    recoveryGeneration: P3ProcessingStage
    d5Verification: P3ProcessingStage
  }>
}>

export type RestoreAdjustmentState = Rg1State | undefined
export type RestoreAdjustmentPhase = 'request' | 'pre-commit' | 'service-start'
export type RestoreAdjustmentPath = 'd1' | 'p3' | 'handover'

export type RestoreAdjustmentGateRequest = Readonly<{
  state: RestoreAdjustmentState
  phase: RestoreAdjustmentPhase
  path: RestoreAdjustmentPath
}>

export type RestoreAdjustmentGateResult =
  | Readonly<{
      decision: 'allow'
      normalWritesAllowed: true
      internalJobsAllowed: true
      mayConsumeD5: true
    }>
  | Readonly<{
      decision: 'stop'
      boundaryResultId: string
      normalWritesAllowed: false
      internalJobsAllowed: false
      mayConsumeD5: false
      rollbackAll: boolean
      allowedControlPlane: 'recovery-only'
    }>

function requireBoundaryResultId(
  results: readonly Readonly<{ id: string; name: string }>[],
  name: string,
): string {
  const matches = Object.freeze(
    results.filter((candidate) => Object.is(candidate.name, name)),
  )
  if (matches.length !== 1) {
    throw new Error(`正本の境界結果を一意に解決できません: ${name}`)
  }
  return matches[0]!.id
}

const d1TemporaryFailure = requireBoundaryResultId(
  readCanonBoundaryResults(),
  '一時障害',
)
const p3TemporaryFailure = requireBoundaryResultId(
  readCanonP3BoundaryResults(),
  '一時障害',
)

export const RESTORE_ADJUSTMENT_BOUNDARY_RESULTS = Object.freeze({
  d1: d1TemporaryFailure,
  p3: p3TemporaryFailure,
  handover: d1TemporaryFailure,
})

const restoreAdjustmentGateClauses = Object.freeze([
  '③認可後',
  'D5照合前',
  '全通常書き込み・内部ジョブ停止',
  `P1・P2・P4・通常/緊急引き継ぎは${RESTORE_ADJUSTMENT_BOUNDARY_RESULTS.d1}`,
  `P3は${RESTORE_ADJUSTMENT_BOUNDARY_RESULTS.p3}`,
  'D5消費なし',
  'コミット直前再検証',
  'サービス再開fail-closed',
  '解除・新D4開始不可分',
  '復旧制御面だけ許可',
])

export const RESTORE_ADJUSTMENT_GATE_RULE: RestoreAdjustmentGateRule =
  Object.freeze({
    purpose: 'processing-stage',
    relationIds: Object.freeze([
      'R-BOUNDARY' as const,
      'R-P3-BOUNDARY' as const,
    ]),
    id: 'RG1',
    name: '復元調整中のfail-closed共通ゲート',
    clauses: restoreAdjustmentGateClauses,
    rightHandSide: restoreAdjustmentGateClauses.join('+'),
    failClosed: Object.freeze({
      indeterminateState: 'stop',
      preCommitTransition: 'rollback-all',
      serviceRestartIndeterminate: 'keep-writes-closed',
      releaseAndNewGenerationStart: 'atomic',
      intermediateNormalWritesAllowed: false,
      allowedControlPlane: 'recovery-only',
    }),
  })

function requireStage<Stage>(
  stages: readonly Stage[],
  index: number,
  path: string,
): Stage {
  const stage = stages[index]
  if (!stage) {
    throw new Error(`${path} の RG1 処理段階がありません`)
  }
  return stage
}

export const RESTORE_ADJUSTMENT_GATE_POSITION: RestoreAdjustmentGatePosition =
  Object.freeze({
    d1: Object.freeze({
      authorization: requireStage(D1_PROCESSING_STAGES, 2, 'D1 付き経路'),
      restoreGate: requireStage(D1_PROCESSING_STAGES, 3, 'D1 付き経路'),
      d5Verification: requireStage(D1_PROCESSING_STAGES, 4, 'D1 付き経路'),
    }),
    p3: Object.freeze({
      authorization: requireStage(P3_PROCESSING_STAGES, 2, 'P3'),
      restoreGate: requireStage(P3_PROCESSING_STAGES, 3, 'P3'),
      recoveryGeneration: requireStage(P3_PROCESSING_STAGES, 4, 'P3'),
      d5Verification: requireStage(P3_PROCESSING_STAGES, 5, 'P3'),
    }),
  })

function boundaryResultForPath(path: RestoreAdjustmentPath): string {
  if (Object.is(path, 'p3')) {
    return RESTORE_ADJUSTMENT_BOUNDARY_RESULTS.p3
  }
  if (Object.is(path, 'handover')) {
    return RESTORE_ADJUSTMENT_BOUNDARY_RESULTS.handover
  }
  return RESTORE_ADJUSTMENT_BOUNDARY_RESULTS.d1
}

/**
 * 復元調整状態を fail-closed で判定する。
 *
 * Args:
 *   request: 復元調整状態、検査段階、要求経路。
 *
 * Returns:
 *   非調整中と確認できた場合だけ通常処理を許可する判定結果。
 */
export function checkRestoreAdjustmentGate(
  request: RestoreAdjustmentGateRequest,
): RestoreAdjustmentGateResult {
  if (Object.is(request.state, RG1_STATE.INACTIVE_CONFIRMED)) {
    return Object.freeze({
      decision: 'allow',
      normalWritesAllowed: true,
      internalJobsAllowed: true,
      mayConsumeD5: true,
    })
  }

  return Object.freeze({
    decision: 'stop',
    boundaryResultId: boundaryResultForPath(request.path),
    normalWritesAllowed: false,
    internalJobsAllowed: false,
    mayConsumeD5: false,
    rollbackAll: Object.is(request.phase, 'pre-commit'),
    allowedControlPlane: 'recovery-only',
  })
}
