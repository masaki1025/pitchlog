// この表と順序検査は docs/design/sync-protocol.md 6-2 の処理段階と停止境界の写しである。
// 射程は D1 付き経路と P3 の段階語彙・順序・停止境界結果に限る。
// 実際のトランザクション処理はサーバー適用層の責務であるため射程外とする。

import {
  readCanonBoundaryResults,
  readCanonP3BoundaryResults,
  type CanonProcessingStageRule,
} from './canonOracle'

const D1_AUTHORIZATION_STAGE = '③ 認可(テナント)'
const D1_RESTORE_GATE_STAGE = '③-a 復元調整ゲート'
const D1_IDEMPOTENCY_STAGE = '④ D5 の照合'
const D1_RECORDING_RIGHT_STAGE = '⑤ 記録権(D4・V12)'
const D1_SEQUENCE_STAGE = '⑥ 連番(D1)の連続性'
const D1_CONTENT_STAGE = '⑦ 内容の検証'
const P3_AUTHORIZATION_STAGE = '③ 認可(テナント)'
const P3_RESTORE_GATE_STAGE = '③-a 復元調整ゲート'
const P3_RECOVERY_GENERATION_STAGE = '③-b 復旧世代の照合'
const P3_IDEMPOTENCY_STAGE = '④ D5 の照合'
const P3_RECORDING_RIGHT_STAGE = '⑤ 記録権証明'
const P3_CONTENT_STAGE = '⑥ 内容の検証'
const P3_EXPECTED_VERSION_STAGE = '⑦ V11 の期待版照合'

type ProcessingStageRuleId = 'DI1' | 'DI4' | 'I1' | 'I4'

export type ProcessingStageRule = Readonly<{
  purpose: CanonProcessingStageRule['purpose']
  relationId: CanonProcessingStageRule['relationId']
  id: ProcessingStageRuleId
  rightHandSide: string
}>

export type D1ProcessingStage = Readonly<{
  stage: string
  check: string
  stopBoundaryResult: string
  stopBoundaryResultIds: readonly string[]
}>

export type P3ProcessingStage = Readonly<{
  order: string
  inProgress: string
  afterCompletion: string
  stopBoundaryResult: string
  stopBoundaryResultIds: readonly string[]
}>

export const PROCESSING_STAGE_RULES: readonly ProcessingStageRule[] =
  Object.freeze([
    Object.freeze({
      purpose: 'processing-stage',
      relationId: 'R-BOUNDARY',
      id: 'DI1',
      rightHandSide: '③認可後+V12前',
    }),
    Object.freeze({
      purpose: 'processing-stage',
      relationId: 'R-BOUNDARY',
      id: 'DI4',
      rightHandSide: 'V12・prefix・内容検査対象',
    }),
    Object.freeze({
      purpose: 'processing-stage',
      relationId: 'R-P3-BOUNDARY',
      id: 'I1',
      rightHandSide: '③認可後+RG1後+復旧世代照合後+V12前+V11前',
    }),
    Object.freeze({
      purpose: 'processing-stage',
      relationId: 'R-P3-BOUNDARY',
      id: 'I4',
      rightHandSide: '現復旧世代+V12・V11照合対象',
    }),
  ])

function requireBoundaryResultId(
  results: readonly Readonly<{ id: string; name: string }>[],
  name: string,
): string {
  const result = results.find((candidate) => Object.is(candidate.name, name))
  if (!result) {
    throw new Error(`正本の境界結果がありません: ${name}`)
  }
  return result.id
}

function freezeResultIds(...ids: string[]): readonly string[] {
  return Object.freeze(ids)
}

const d1BoundaryResults = readCanonBoundaryResults()
const p3BoundaryResults = readCanonP3BoundaryResults()
const d1RequestEnd = requireBoundaryResultId(d1BoundaryResults, '要求終端')
const d1Gap = requireBoundaryResultId(d1BoundaryResults, 'gap')
const d1PermanentRejection = requireBoundaryResultId(
  d1BoundaryResults,
  '恒久的な内容拒否',
)
const d1RecordingRightMismatch = requireBoundaryResultId(
  d1BoundaryResults,
  '記録権不一致',
)
const d1AuthenticationExpired = requireBoundaryResultId(
  d1BoundaryResults,
  '認証失効',
)
const d1TenantMismatch = requireBoundaryResultId(
  d1BoundaryResults,
  '認可・テナント不一致',
)
const d1TemporaryFailure = requireBoundaryResultId(
  d1BoundaryResults,
  '一時障害',
)
const d1UnusedD5Rejection = `${d1PermanentRejection}a`
const d1ExistingD5Collision = `${d1PermanentRejection}b`
const p3Accepted = p3BoundaryResults.find((result) => result.accepted)?.id
if (!p3Accepted) {
  throw new Error('正本の P3 受理結果がありません')
}
const p3ExpectedVersionMismatch = requireBoundaryResultId(
  p3BoundaryResults,
  '期待版不一致',
)
const p3RecordingRightMissing = requireBoundaryResultId(
  p3BoundaryResults,
  '記録権不保持',
)
const p3TemporaryFailure = requireBoundaryResultId(
  p3BoundaryResults,
  '一時障害',
)
const p3AuthenticationExpired = requireBoundaryResultId(
  p3BoundaryResults,
  '認証失効',
)
const p3TenantMismatch = requireBoundaryResultId(
  p3BoundaryResults,
  '認可・テナント不一致',
)
const p3D5Collision = requireBoundaryResultId(p3BoundaryResults, 'D5衝突')
const p3ContentRejection = requireBoundaryResultId(
  p3BoundaryResults,
  '変更内容拒否',
)

export const D1_PROCESSING_STAGES: readonly D1ProcessingStage[] = Object.freeze(
  [
    Object.freeze({
      stage: '① トランスポート・処理系',
      check: '要求が届き、処理が完了したか',
      stopBoundaryResult: 'B7 一時障害',
      stopBoundaryResultIds: freezeResultIds(d1TemporaryFailure),
    }),
    Object.freeze({
      stage: '② 認証',
      check: '呼び出し元が認証されているか',
      stopBoundaryResult: 'B5 認証失効',
      stopBoundaryResultIds: freezeResultIds(d1AuthenticationExpired),
    }),
    Object.freeze({
      stage: D1_AUTHORIZATION_STAGE,
      check: 'その試合が自テナントのものか',
      stopBoundaryResult: 'B6 認可・テナント不一致',
      stopBoundaryResultIds: freezeResultIds(d1TenantMismatch),
    }),
    Object.freeze({
      stage: D1_RESTORE_GATE_STAGE,
      check:
        'RG1: 復元調整中の fail-closed 共通ゲート = ③ 認可後 + D5 照合前 + 全通常書き込み・内部ジョブ停止 + P1・P2・P4・通常/緊急引き継ぎは B7 + P3 は B10 + D5 消費なし + コミット直前再検証 + サービス再開 fail-closed + 解除・新 D4 開始不可分 + 復旧制御面だけ許可',
      stopBoundaryResult:
        'D1 付き経路は B7 で再試行可能に止め、A5・D3 を返さず D5 を記録しない',
      stopBoundaryResultIds: freezeResultIds(d1TemporaryFailure),
    }),
    Object.freeze({
      stage: D1_IDEMPOTENCY_STAGE,
      check:
        '各イベントを内部候補へ分類する。既存 D5・同一内容なら保存済み結果を再掲する候補として再適用せず、既存 D5・異なる内容は B3b 候補とし、未使用 D5 だけ⑤へ進む。この段階では外部結果を確定しない',
      stopBoundaryResult: 'B3b 候補。同一内容は保存済み結果候補',
      stopBoundaryResultIds: freezeResultIds(d1ExistingD5Collision),
    }),
    Object.freeze({
      stage: D1_RECORDING_RIGHT_STAGE,
      check:
        '未使用 D5 の新規操作について、D4 が現世代で、V12 が現保持端末へ結合された証明として有効か',
      stopBoundaryResult: 'B4 記録権不一致',
      stopBoundaryResultIds: freezeResultIds(d1RecordingRightMismatch),
    }),
    Object.freeze({
      stage: D1_SEQUENCE_STAGE,
      check:
        'D3 + 1 から D1 昇順に走査し、欠落がないかを確かめる。欠落がなければ、その位置の④の候補を外部結果へ確定する。最初の B2 または B3 で止め、それ以降は候補の種類を問わず未処理にする',
      stopBoundaryResult: 'B2 gap、またはその位置で確定した B3b',
      stopBoundaryResultIds: freezeResultIds(d1Gap, d1ExistingD5Collision),
    }),
    Object.freeze({
      stage: D1_CONTENT_STAGE,
      check: '⑥を通過した未使用 D5 のイベント内容が受理できるか',
      stopBoundaryResult: 'B3a 恒久的な内容拒否',
      stopBoundaryResultIds: freezeResultIds(d1UnusedD5Rejection),
    }),
    Object.freeze({
      stage: '⑧ コミット直前の RG1 再検証・完了',
      check:
        '書き込みトランザクションがコミット直前にも復元調整中でないことを確認し、最後まで処理し切ったか',
      stopBoundaryResult:
        '復元調整へ移行済みなら B7 として全変更をロールバック。通過時だけ B1 要求終端',
      stopBoundaryResultIds: freezeResultIds(d1TemporaryFailure, d1RequestEnd),
    }),
  ],
)

export const P3_PROCESSING_STAGES: readonly P3ProcessingStage[] = Object.freeze(
  [
    Object.freeze({
      order: '① トランスポート・処理系',
      inProgress: '要求が届き、処理が完了したか',
      afterCompletion: '同左',
      stopBoundaryResult: 'B10 一時障害',
      stopBoundaryResultIds: freezeResultIds(p3TemporaryFailure),
    }),
    Object.freeze({
      order: '② 認証',
      inProgress: '呼び出し元が認証されているか',
      afterCompletion: '同左',
      stopBoundaryResult: 'B11 認証失効',
      stopBoundaryResultIds: freezeResultIds(p3AuthenticationExpired),
    }),
    Object.freeze({
      order: P3_AUTHORIZATION_STAGE,
      inProgress: 'その試合が自テナントのものか',
      afterCompletion: '同左',
      stopBoundaryResult: 'B12 認可・テナント不一致',
      stopBoundaryResultIds: freezeResultIds(p3TenantMismatch),
    }),
    Object.freeze({
      order: P3_RESTORE_GATE_STAGE,
      inProgress:
        'RG1: 復元調整中の fail-closed 共通ゲート = ③ 認可後 + D5 照合前 + 全通常書き込み・内部ジョブ停止 + P1・P2・P4・通常/緊急引き継ぎは B7 + P3 は B10 + D5 消費なし + コミット直前再検証 + サービス再開 fail-closed + 解除・新 D4 開始不可分 + 復旧制御面だけ許可',
      afterCompletion: '同左',
      stopBoundaryResult: 'B10 で再試行可能に止め、D5 を記録しない',
      stopBoundaryResultIds: freezeResultIds(p3TemporaryFailure),
    }),
    Object.freeze({
      order: P3_RECOVERY_GENERATION_STAGE,
      inProgress: '要求作成時の復旧世代が現復旧世代と一致するか',
      afterCompletion: '同左',
      stopBoundaryResult:
        '不一致なら B9。終了後 P3 も適用せず、D5 を照合・消費しない。旧復旧世代であることを利用者へ示し、管理者ログへ残す',
      stopBoundaryResultIds: freezeResultIds(p3RecordingRightMissing),
    }),
    Object.freeze({
      order: P3_IDEMPOTENCY_STAGE,
      inProgress:
        '既存 D5・同一内容なら保存済み結果を再掲して終了し、再適用しない。既存 D5・異なる内容なら B13。未使用 D5 だけ⑤へ進む',
      afterCompletion: '同左',
      stopBoundaryResult: 'B13 D5 衝突。同一内容は保存済み結果',
      stopBoundaryResultIds: freezeResultIds(p3D5Collision),
    }),
    Object.freeze({
      order: P3_RECORDING_RIGHT_STAGE,
      inProgress:
        '未使用 D5 の新規操作について、V12 が現 D4 の保持端末へ結合された証明として有効か',
      afterCompletion: '適用しない。そのまま⑥へ進む',
      stopBoundaryResult: 'B9 記録権不保持(進行中だけ)',
      stopBoundaryResultIds: freezeResultIds(p3RecordingRightMissing),
    }),
    Object.freeze({
      order: P3_CONTENT_STAGE,
      inProgress: '変更内容が受理できるか',
      afterCompletion: '同左',
      stopBoundaryResult: 'B14 変更内容拒否',
      stopBoundaryResultIds: freezeResultIds(p3ContentRejection),
    }),
    Object.freeze({
      order: P3_EXPECTED_VERSION_STAGE,
      inProgress: '対象の現在の確定版と V11 が一致するか',
      afterCompletion: '同左',
      stopBoundaryResult: 'B8 期待版不一致',
      stopBoundaryResultIds: freezeResultIds(p3ExpectedVersionMismatch),
    }),
    Object.freeze({
      order: '⑧ コミット直前の RG1 再検証',
      inProgress:
        '書き込みトランザクションがコミット直前にも復元調整中でないことを確認する',
      afterCompletion: '同左',
      stopBoundaryResult:
        '復元調整へ移行済みなら B10 として T1・T2・T4・T6・T7 をすべてロールバックする',
      stopBoundaryResultIds: freezeResultIds(p3TemporaryFailure),
    }),
    Object.freeze({
      order: '⑨ 完了',
      inProgress: 'T1・T2・T4・T6・T7 をすべて確定したか',
      afterCompletion: '同左',
      stopBoundaryResult: '変更受理',
      stopBoundaryResultIds: freezeResultIds(p3Accepted),
    }),
  ],
)

export const EXTERNAL_RESULT_CONFIRMATION_ORDER = 'D1 昇順' as const

function requireStageIndex(
  stages: readonly string[],
  expectedStage: string,
): number {
  const index = stages.findIndex((stage) => Object.is(stage, expectedStage))
  if (index < 0) {
    throw new Error(`処理段階がありません: ${expectedStage}`)
  }
  return index
}

function assertBefore(
  stages: readonly string[],
  before: string,
  after: string,
): void {
  if (requireStageIndex(stages, before) >= requireStageIndex(stages, after)) {
    throw new Error(`処理段階の順序が不正です: ${before} < ${after}`)
  }
}

export function assertProcessingStageOrder(
  d1Stages: readonly D1ProcessingStage[] = D1_PROCESSING_STAGES,
  p3Stages: readonly P3ProcessingStage[] = P3_PROCESSING_STAGES,
): void {
  const d1StageNames = Object.freeze(d1Stages.map((stage) => stage.stage))
  const p3StageNames = Object.freeze(p3Stages.map((stage) => stage.order))

  assertBefore(d1StageNames, D1_AUTHORIZATION_STAGE, D1_RESTORE_GATE_STAGE)
  assertBefore(d1StageNames, D1_RESTORE_GATE_STAGE, D1_IDEMPOTENCY_STAGE)
  for (const laterStage of [
    D1_RECORDING_RIGHT_STAGE,
    D1_SEQUENCE_STAGE,
    D1_CONTENT_STAGE,
  ]) {
    assertBefore(d1StageNames, D1_IDEMPOTENCY_STAGE, laterStage)
  }

  assertBefore(p3StageNames, P3_AUTHORIZATION_STAGE, P3_RESTORE_GATE_STAGE)
  assertBefore(
    p3StageNames,
    P3_RESTORE_GATE_STAGE,
    P3_RECOVERY_GENERATION_STAGE,
  )
  assertBefore(p3StageNames, P3_RECOVERY_GENERATION_STAGE, P3_IDEMPOTENCY_STAGE)
  for (const laterStage of [
    P3_RECORDING_RIGHT_STAGE,
    P3_CONTENT_STAGE,
    P3_EXPECTED_VERSION_STAGE,
  ]) {
    assertBefore(p3StageNames, P3_IDEMPOTENCY_STAGE, laterStage)
  }
}

assertProcessingStageOrder()
