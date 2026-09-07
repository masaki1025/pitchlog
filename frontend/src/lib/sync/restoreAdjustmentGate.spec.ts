import { describe, expect, it } from 'vitest'
import syncProtocolRelations from '@design-relations/sync-protocol.json'
import restoreAdjustmentGateSource from './restoreAdjustmentGate.ts?raw'
import {
  readCanonBoundaryResults,
  readCanonP3BoundaryResults,
  readCanonProcessingStageRules,
} from './canonOracle'
import { D1_PROCESSING_STAGES, P3_PROCESSING_STAGES } from './processingStages'
import { RG1_STATE } from './queueTransition'
import {
  RESTORE_ADJUSTMENT_BOUNDARY_RESULTS,
  RESTORE_ADJUSTMENT_GATE_POSITION,
  RESTORE_ADJUSTMENT_GATE_RULE,
  checkRestoreAdjustmentGate,
  type RestoreAdjustmentGateResult,
  type RestoreAdjustmentPhase,
  type RestoreAdjustmentState,
} from './restoreAdjustmentGate'

function requireTemporaryFailureId(
  results: readonly Readonly<{ id: string; name: string }>[],
): string {
  const result = results.find((candidate) =>
    Object.is(candidate.name, '一時障害'),
  )
  expect(result).toBeDefined()
  if (!result) {
    throw new Error('一時障害の境界結果がありません')
  }
  return result.id
}

function expectCanonRg1ToMatchProduct(relations: unknown): void {
  const canonRules = readCanonProcessingStageRules(relations).filter((rule) =>
    Object.is(rule.id, RESTORE_ADJUSTMENT_GATE_RULE.id),
  )

  expect(canonRules).toHaveLength(2)
  expect(new Set(canonRules.map((rule) => rule.rightHandSide)).size).toBe(1)
  expect(new Set(canonRules.map((rule) => rule.relationId))).toEqual(
    new Set(RESTORE_ADJUSTMENT_GATE_RULE.relationIds),
  )
  for (const rule of canonRules) {
    expect(rule.purpose).toBe(RESTORE_ADJUSTMENT_GATE_RULE.purpose)
    expect(rule.rightHandSide).toBe(RESTORE_ADJUSTMENT_GATE_RULE.rightHandSide)
  }
}

function expectStopped(
  result: RestoreAdjustmentGateResult,
  rollbackAll: boolean,
): void {
  expect(result).toMatchObject({
    decision: 'stop',
    normalWritesAllowed: false,
    internalJobsAllowed: false,
    mayConsumeD5: false,
    rollbackAll,
    allowedControlPlane: 'recovery-only',
  })
}

describe('restoreAdjustmentGate', () => {
  it('RG1 の右辺10節を逐語かつ所定順で固定する', () => {
    expect(RESTORE_ADJUSTMENT_GATE_RULE.clauses).toEqual([
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
    expect(RESTORE_ADJUSTMENT_GATE_RULE.rightHandSide).toBe(
      RESTORE_ADJUSTMENT_GATE_RULE.clauses.join('+'),
    )
    expect(RESTORE_ADJUSTMENT_GATE_RULE.failClosed).toEqual({
      indeterminateState: 'stop',
      preCommitTransition: 'rollback-all',
      serviceRestartIndeterminate: 'keep-writes-closed',
      releaseAndNewGenerationStart: 'atomic',
      intermediateNormalWritesAllowed: false,
      allowedControlPlane: 'recovery-only',
    })
  })

  it('両関係の RG1 が同一の右辺で製品表と逐語一致する', () => {
    expectCanonRg1ToMatchProduct(syncProtocolRelations)
  })

  it('片方の関係だけに生じた RG1 の右辺変更を検出する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-P3-BOUNDARY'].source_elements
    const targetId = 'RG1'
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith(`${targetId}:`),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements[targetIndex] = sourceElements[targetIndex]!.replace(
      'D5照合前',
      'D5照合後',
    )
    expect(() => expectCanonRg1ToMatchProduct(mutatedRelations)).toThrow()
  })

  it('一時障害の境界結果を両 canon reader から名前で解決する', () => {
    const d1TemporaryFailure = requireTemporaryFailureId(
      readCanonBoundaryResults(),
    )
    const p3TemporaryFailure = requireTemporaryFailureId(
      readCanonP3BoundaryResults(),
    )

    expect(RESTORE_ADJUSTMENT_BOUNDARY_RESULTS).toEqual({
      d1: d1TemporaryFailure,
      p3: p3TemporaryFailure,
      handover: d1TemporaryFailure,
    })
    expect(restoreAdjustmentGateSource).not.toMatch(/(['"])B(?:7|10)\1/)
  })

  it('RG1 の位置を処理段階表の認可後かつ D5 照合前へ結びつける', () => {
    const d1AuthorizationIndex = D1_PROCESSING_STAGES.findIndex((stage) =>
      Object.is(stage, RESTORE_ADJUSTMENT_GATE_POSITION.d1.authorization),
    )
    const d1RestoreGateIndex = D1_PROCESSING_STAGES.findIndex((stage) =>
      Object.is(stage, RESTORE_ADJUSTMENT_GATE_POSITION.d1.restoreGate),
    )
    const d1D5Index = D1_PROCESSING_STAGES.findIndex((stage) =>
      Object.is(stage, RESTORE_ADJUSTMENT_GATE_POSITION.d1.d5Verification),
    )
    const p3AuthorizationIndex = P3_PROCESSING_STAGES.findIndex((stage) =>
      Object.is(stage, RESTORE_ADJUSTMENT_GATE_POSITION.p3.authorization),
    )
    const p3RestoreGateIndex = P3_PROCESSING_STAGES.findIndex((stage) =>
      Object.is(stage, RESTORE_ADJUSTMENT_GATE_POSITION.p3.restoreGate),
    )
    const p3RecoveryGenerationIndex = P3_PROCESSING_STAGES.findIndex((stage) =>
      Object.is(stage, RESTORE_ADJUSTMENT_GATE_POSITION.p3.recoveryGeneration),
    )
    const p3D5Index = P3_PROCESSING_STAGES.findIndex((stage) =>
      Object.is(stage, RESTORE_ADJUSTMENT_GATE_POSITION.p3.d5Verification),
    )

    for (const index of [
      d1AuthorizationIndex,
      d1RestoreGateIndex,
      d1D5Index,
      p3AuthorizationIndex,
      p3RestoreGateIndex,
      p3RecoveryGenerationIndex,
      p3D5Index,
    ]) {
      expect(index).toBeGreaterThanOrEqual(0)
    }
    expect(d1AuthorizationIndex).toBeLessThan(d1RestoreGateIndex)
    expect(d1RestoreGateIndex).toBeLessThan(d1D5Index)
    expect(p3AuthorizationIndex).toBeLessThan(p3RestoreGateIndex)
    expect(p3RestoreGateIndex).toBeLessThan(p3RecoveryGenerationIndex)
    expect(p3RecoveryGenerationIndex).toBeLessThan(p3D5Index)
  })

  it.each([
    [RG1_STATE.ACTIVE, 'request', false],
    [RG1_STATE.ACTIVE, 'pre-commit', true],
    [RG1_STATE.ACTIVE, 'service-start', false],
    [RG1_STATE.UNKNOWN, 'request', false],
    [RG1_STATE.UNKNOWN, 'pre-commit', true],
    [RG1_STATE.UNKNOWN, 'service-start', false],
    [undefined, 'request', false],
    [undefined, 'pre-commit', true],
    [undefined, 'service-start', false],
  ] satisfies readonly [
    RestoreAdjustmentState,
    RestoreAdjustmentPhase,
    boolean,
  ][])('%s の %s は停止側へ倒す', (state, phase, rollbackAll) => {
    const result = checkRestoreAdjustmentGate({ state, phase, path: 'd1' })

    expectStopped(result, rollbackAll)
  })

  it('各経路を対応する一時障害境界で停止する', () => {
    for (const [path, boundaryResultId] of Object.entries(
      RESTORE_ADJUSTMENT_BOUNDARY_RESULTS,
    )) {
      expect(
        checkRestoreAdjustmentGate({
          state: RG1_STATE.ACTIVE,
          phase: 'request',
          path: path as 'd1' | 'p3' | 'handover',
        }),
      ).toMatchObject({ decision: 'stop', boundaryResultId })
    }
  })

  it('非調整中と確認できた場合だけ通常処理を許可する', () => {
    expect(
      checkRestoreAdjustmentGate({
        state: RG1_STATE.INACTIVE_CONFIRMED,
        phase: 'service-start',
        path: 'p3',
      }),
    ).toEqual({
      decision: 'allow',
      normalWritesAllowed: true,
      internalJobsAllowed: true,
      mayConsumeD5: true,
    })
  })
})
