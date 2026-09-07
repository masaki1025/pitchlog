import { describe, expect, it } from 'vitest'
import processingStageSnapshot from './processingStages.snapshot.json'
import {
  D1_PROCESSING_STAGES,
  EXTERNAL_RESULT_CONFIRMATION_ORDER,
  P3_PROCESSING_STAGES,
  assertProcessingStageOrder,
  type D1ProcessingStage,
  type P3ProcessingStage,
} from './processingStages'

type ProcessingStageSnapshot = Readonly<{
  d1Stages: readonly Readonly<{
    stage: string
    check: string
    stopBoundaryResult: string
  }>[]
  p3Stages: readonly Readonly<{
    order: string
    inProgress: string
    afterCompletion: string
    stopBoundaryResult: string
  }>[]
}>

function projectProcessingStageSnapshot(): ProcessingStageSnapshot {
  return Object.freeze({
    d1Stages: Object.freeze(
      D1_PROCESSING_STAGES.map((stage) =>
        Object.freeze({
          stage: stage.stage,
          check: stage.check,
          stopBoundaryResult: stage.stopBoundaryResult,
        }),
      ),
    ),
    p3Stages: Object.freeze(
      P3_PROCESSING_STAGES.map((stage) =>
        Object.freeze({
          order: stage.order,
          inProgress: stage.inProgress,
          afterCompletion: stage.afterCompletion,
          stopBoundaryResult: stage.stopBoundaryResult,
        }),
      ),
    ),
  })
}

function expectProcessingStagesToMatchSnapshot(
  snapshot: ProcessingStageSnapshot,
): void {
  expect(projectProcessingStageSnapshot()).toEqual(snapshot)
}

describe('processingStages', () => {
  it('D1 付き9段階と P3 の11段階をスナップショットと逐語照合する', () => {
    expect(D1_PROCESSING_STAGES).toHaveLength(9)
    expect(P3_PROCESSING_STAGES).toHaveLength(11)
    expectProcessingStagesToMatchSnapshot(processingStageSnapshot)
  })

  it('スナップショットの段階を1行変えると逐語照合が失敗する', () => {
    const mutatedSnapshot = structuredClone(processingStageSnapshot)
    const stageId = '④ D5 の照合'
    const targetIndex = mutatedSnapshot.d1Stages.findIndex((stage) =>
      Object.is(stage.stage, stageId),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    mutatedSnapshot.d1Stages[targetIndex]!.check += '変異'
    expect(() =>
      expectProcessingStagesToMatchSnapshot(mutatedSnapshot),
    ).toThrow()
  })

  it('D1 付き経路で認可を D5 照合より後へ動かすと拒否する', () => {
    const mutatedStages: D1ProcessingStage[] = structuredClone([
      ...D1_PROCESSING_STAGES,
    ])
    const authorizationId = '③ 認可(テナント)'
    const idempotencyId = '④ D5 の照合'
    const authorizationIndex = mutatedStages.findIndex((stage) =>
      Object.is(stage.stage, authorizationId),
    )
    const idempotencyIndex = mutatedStages.findIndex((stage) =>
      Object.is(stage.stage, idempotencyId),
    )

    expect(authorizationIndex).toBeGreaterThanOrEqual(0)
    expect(idempotencyIndex).toBeGreaterThanOrEqual(0)
    ;[mutatedStages[authorizationIndex], mutatedStages[idempotencyIndex]] = [
      mutatedStages[idempotencyIndex]!,
      mutatedStages[authorizationIndex]!,
    ]
    expect(() => assertProcessingStageOrder(mutatedStages)).toThrowError(
      /処理段階の順序/,
    )
  })

  it('P3 で認可を復元調整ゲートより後へ動かすと拒否する', () => {
    const mutatedStages: P3ProcessingStage[] = structuredClone([
      ...P3_PROCESSING_STAGES,
    ])
    const authorizationId = '③ 認可(テナント)'
    const restoreGateId = '③-a 復元調整ゲート'
    const authorizationIndex = mutatedStages.findIndex((stage) =>
      Object.is(stage.order, authorizationId),
    )
    const restoreGateIndex = mutatedStages.findIndex((stage) =>
      Object.is(stage.order, restoreGateId),
    )

    expect(authorizationIndex).toBeGreaterThanOrEqual(0)
    expect(restoreGateIndex).toBeGreaterThanOrEqual(0)
    ;[mutatedStages[authorizationIndex], mutatedStages[restoreGateIndex]] = [
      mutatedStages[restoreGateIndex]!,
      mutatedStages[authorizationIndex]!,
    ]
    expect(() =>
      assertProcessingStageOrder(undefined, mutatedStages),
    ).toThrowError(/処理段階の順序/)
  })

  it('停止境界結果を正本 reader 由来の ID 順で保持する', () => {
    expect(
      D1_PROCESSING_STAGES.map((stage) =>
        stage.stopBoundaryResultIds.join('|'),
      ),
    ).toEqual(['B7', 'B5', 'B6', 'B7', 'B3b', 'B4', 'B2|B3b', 'B3a', 'B7|B1'])
    expect(
      P3_PROCESSING_STAGES.map((stage) =>
        stage.stopBoundaryResultIds.join('|'),
      ),
    ).toEqual([
      'B10',
      'B11',
      'B12',
      'B10',
      'B9',
      'B13',
      'B9',
      'B14',
      'B8',
      'B10',
      '変更受理',
    ])
  })

  it('外部結果へ確定する順序を D1 昇順に固定する', () => {
    const d1Stages: readonly D1ProcessingStage[] = D1_PROCESSING_STAGES
    const p3Stages: readonly P3ProcessingStage[] = P3_PROCESSING_STAGES

    expect(d1Stages).toBe(D1_PROCESSING_STAGES)
    expect(p3Stages).toBe(P3_PROCESSING_STAGES)
    expect(EXTERNAL_RESULT_CONFIRMATION_ORDER).toBe('D1 昇順')
  })
})
