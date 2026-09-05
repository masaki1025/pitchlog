import { describe, expect, it } from 'vitest'
import * as ts from 'typescript'
import type {
  D1AckEnvelope,
  D1AckEventResult,
  D1AckPlayerIdMapping,
} from './ackEnvelope'
import type { AckBoundaryResult, NoAckBoundaryResult } from './boundaryResults'
import { CLIENT_DISCIPLINE_RULES } from './clientDiscipline'
import {
  DURABLE_QUEUE_PUBLIC_METHOD_RULES,
  DurableQueue,
  DurableQueuePreparation,
  I6EvacuationReceipt,
  I6PersistenceReceipt,
  type DurableI6Slot,
  type DurableQueueAppend,
  type DurableQueueSlot,
} from './durableQueue'
import {
  EVENT_FIELD_PRESENCE,
  EVENT_FIELD_REQUIREDNESS,
  EVENT_FIELD_RULES,
  EVENT_SLOT_IDS,
  resolveEventFieldPresence,
  SYNC_EVENT_PATH,
  type EventSlotId,
} from './eventFieldRules'
import { buildSyncEventKindSet, EVENT_KIND_RULES } from './eventKinds'
import {
  readCanonAckStateResults,
  readCanonEventFieldRules,
} from './canonOracle'
import type {
  LocalQueueFileImportRequest,
  LocalQueueFileImportResult,
} from './localQueueFile'
import type {
  P3AcceptedResultEnvelope,
  P3RejectedResultEnvelope,
  P3ResultEnvelope,
} from './p3Result'
import {
  actionRequiredLabelId,
  I6_HOLDING_CONTRACT,
  queueStateId,
  type I6AcceptedResult,
} from './queueState'
import type {
  B3ContentRejection,
  B3O4Rejection,
  B3Rejection,
} from './rejectionReason'
import {
  B3_REASON_KIND,
  QUEUE_TRANSITION_RULES,
  type B3ReasonClassification,
  type QueueSlot,
  type QueueTransitionRequest,
} from './queueTransition'
import {
  buildSidecarJoinKey,
  SYNC_EVENT_ENVELOPE_KEYS,
  TARGET_EVENT_REFERENCE_ELEMENTS,
  type SyncEvent,
  type TargetEventReference,
} from './syncEvent'
import {
  checkSyncEvent,
  type SourceEventContext,
  type SyncEventValidationContext,
  type SyncEventValidationResult,
  type SyncEventViolation,
} from './validateSyncEvent'

type RawModule = { default: string }
type ProductModule = Record<string, unknown>
type ProductSource = Readonly<{
  fileName: string
  source: string
}>
type ForbiddenCandidate = Readonly<{
  name: string
  matches: (source: string) => boolean
}>
type ExactKeySet<Actual, Expected> = [Actual] extends [Expected]
  ? [Expected] extends [Actual]
    ? true
    : false
  : false

const EXPECTED_PRODUCT_FILE_NAMES = [
  'ackEnvelope.ts',
  'boundaryResults.ts',
  'canonOracle.ts',
  'changeOperationGate.ts',
  'clientDiscipline.ts',
  'durableQueue.ts',
  'eventFieldRules.ts',
  'eventKinds.ts',
  'failureScenarioContract.ts',
  'idempotencyCollision.ts',
  'k5Tombstone.ts',
  'localQueueFile.ts',
  'mappingConfirmationGate.ts',
  'p3Result.ts',
  'playerIdMapping.ts',
  'queueState.ts',
  'queueTransition.ts',
  'rejectionReason.ts',
  'requestBoundary.ts',
  'singleWriter.ts',
  'syncEvent.ts',
  'syncNotices.ts',
  'temporaryIdMapping.ts',
  'validateSyncEvent.ts',
] as const

const EXPECTED_VALUE_EXPORTS = {
  'ackEnvelope.ts': ['parseD1AckEnvelope'],
  'boundaryResults.ts': [
    'ACK_BOUNDARY_RESULTS',
    'NO_ACK_BOUNDARY_RESULTS',
    'parseAckBoundaryResult',
  ],
  'canonOracle.ts': [
    'CANON_ACK_STATE_RESULT',
    'CANON_IDEMPOTENCY_OUT_OF_SCOPE',
    'CANON_TEMPORARY_ID_MAPPING_OUT_OF_SCOPE',
    'parseCanonAckStateResults',
    'parseCanonBoundaryResults',
    'parseCanonEventFieldRules',
    'parseCanonIdempotencyCollisionRules',
    'parseCanonP3BoundaryResults',
    'parseCanonParticipationRules',
    'parseCanonQueueLifeRules',
    'parseCanonTemporaryIdMappingRules',
    'parseCanonTombstoneRule',
    'parseCanonV12BoundaryRules',
    'readCanonAckStateResults',
    'readCanonBoundaryResults',
    'readCanonEventFieldRules',
    'readCanonIdempotencyCollisionRules',
    'readCanonP3BoundaryResults',
    'readCanonParticipationRules',
    'readCanonQueueLifeRules',
    'readCanonTemporaryIdMappingRules',
    'readCanonTombstoneRule',
    'readCanonV12BoundaryRules',
  ],
  'changeOperationGate.ts': [
    'CHANGE_OPERATION_GATE_RESULT',
    'checkChangeOperationGate',
  ],
  'clientDiscipline.ts': [
    'CLIENT_CLEANUP_TRIGGER',
    'CLIENT_DISCIPLINE_RULES',
    'DEFAULT_UNSENT_WARNING_THRESHOLD',
    'appendUnderQueueDiscipline',
    'coordinateAuthenticationSync',
    'planQueueCleanup',
  ],
  'durableQueue.ts': [
    'DurableQueue',
    'DURABLE_QUEUE_PUBLIC_METHOD_RULES',
    'DurableQueueUnavailableError',
    'DurableQueuePreparation',
    'I6EvacuationReceipt',
    'I6PersistenceReceipt',
    'openDurableQueue',
  ],
  'eventFieldRules.ts': [
    'EVENT_FIELD_PRESENCE',
    'EVENT_FIELD_REQUIREDNESS',
    'EVENT_FIELD_RULES',
    'EVENT_IDENTIFIER_SLOT_IDS',
    'EVENT_KIND_SLOT_ID',
    'EVENT_SLOT_IDS',
    'REQUEST_ONLY_IDS',
    'SYNC_EVENT_PATH',
    'SYNC_EVENT_PATHS',
    'isCancellableEventKind',
    'resolveEventFieldPresence',
  ],
  'eventKinds.ts': [
    'EVENT_KIND_GROUP',
    'EVENT_KIND_RULES',
    'EVENT_PARTICIPATION',
    'buildSyncEventKindSet',
  ],
  'failureScenarioContract.ts': [
    'FAILURE_EXPECTED_FIELD_IDS',
    'FAILURE_SCENARIO_IDS',
    'FailureScenarioContractError',
    'parseFailureScenarioContract',
    'validateFailureScenarioContract',
    'validateFailureScenarioResult',
  ],
  'idempotencyCollision.ts': [
    'CONTENT_IDENTITY',
    'IDEMPOTENCY_COLLISION_RULES',
    'IDEMPOTENCY_DECISION',
    'IDEMPOTENCY_SCOPE_RULE',
    'decideIdempotencyCollision',
  ],
  'k5Tombstone.ts': [
    'K5_ACTION_GENERATION_RULES',
    'K5_TOMBSTONE_RULE',
    'TOMBSTONE_ONLINE_STATE',
    'prepareTombstoneReplacement',
  ],
  'localQueueFile.ts': [
    'DEFAULT_LOCAL_QUEUE_FILE_CODEC',
    'LOCAL_QUEUE_IMPORT_STATUS',
    'LOCAL_QUEUE_V12_BOUNDARY_RULES',
    'LocalQueueFileError',
    'exportLocalQueueFile',
    'importLocalQueueFile',
  ],
  'mappingConfirmationGate.ts': [
    'C4_MAPPING_CONFIRMATION_RULE',
    'MAPPING_CONFIRMATION_STATUS',
    'checkMappingConfirmation',
  ],
  'p3Result.ts': ['parseP3ResultEnvelope'],
  'playerIdMapping.ts': ['receivePlayerIdMapping'],
  'requestBoundary.ts': [
    'P3_REQUEST_STATE',
    'REQUEST_BOUNDARY_RESULT',
    'RequestBoundaryError',
    'V12_BINDING_COMPONENTS',
    'V12_BOUNDARY_RULES',
    'checkRequestBoundary',
    'retryRequestBoundary',
    'validateRequestBoundary',
  ],
  'singleWriter.ts': [
    'NON_OWNER_INPUT_REASON',
    'SINGLE_WRITER_PRECONDITION_IDS',
    'SINGLE_WRITER_START_FAILURE',
    'rejectNonOwnerInput',
    'runAsSingleWriter',
    'singleWriterLockName',
  ],
  'queueState.ts': [
    'I6_HOLDING_CONTRACT',
    'QUEUE_ACTION_REQUIRED_LABELS',
    'QUEUE_STATES',
    'actionRequiredLabelId',
    'queueStateId',
  ],
  'queueTransition.ts': [
    'B3_REASON_KIND',
    'QUEUE_TRANSITION_ROW_IDS',
    'QUEUE_TRANSITION_RULES',
    'RG1_STATE',
    'evaluateQueueTransition',
    'queueTransitionRuleById',
  ],
  'rejectionReason.ts': [
    'B3_CONTENT_BRANCH',
    'B3_REJECTION_KIND',
    'O4_CORRECTION_CONFIRMATION',
    'parseB3Rejection',
  ],
  'syncEvent.ts': [
    'SYNC_EVENT_ENVELOPE_KEYS',
    'TARGET_EVENT_REFERENCE_ELEMENTS',
    'buildSidecarJoinKey',
    'isTargetEventReference',
  ],
  'syncNotices.ts': [
    'SYNC_NOTICE_CATALOG',
    'SYNC_NOTICE_IDS',
    'createStoragePersistenceNotice',
    'createSyncNotice',
  ],
  'temporaryIdMapping.ts': [
    'TEMPORARY_ID_MAPPING_RULES',
    'TemporaryIdMapping',
    'assertD5IsNotTemporary',
  ],
  'validateSyncEvent.ts': [
    'SYNC_EVENT_VIOLATION',
    'SyncEventValidationError',
    'checkSyncEvent',
    'validateSyncEvent',
  ],
} as const satisfies Readonly<Record<string, readonly string[]>>

const EXPECTED_TYPE_EXPORTS = {
  'ackEnvelope.ts': [
    'D1AckEnvelope',
    'D1AckEventResult',
    'D1AckPlayerIdMapping',
  ],
  'boundaryResults.ts': ['AckBoundaryResult', 'NoAckBoundaryResult'],
  'canonOracle.ts': [
    'CanonAckStateResult',
    'CanonBoundaryResult',
    'CanonEventFieldRule',
    'CanonEventKindRule',
    'CanonIdempotencyCollisionRule',
    'CanonP3BoundaryResult',
    'CanonQueueLifeRule',
    'CanonTemporaryIdMappingRule',
    'CanonTombstoneRule',
    'CanonV12BoundaryRule',
  ],
  'changeOperationGate.ts': [
    'ChangeOperationGateInjections',
    'ChangeOperationGateRejection',
    'ChangeOperationGateRequest',
    'ChangeOperationGateResult',
  ],
  'clientDiscipline.ts': [
    'AuthenticationContinuityInjections',
    'AuthenticationContinuityResult',
    'ClientCleanupInjections',
    'ClientCleanupPlan',
    'ClientCleanupTrigger',
    'ClientDisciplineRule',
    'QueueAppendDisciplineResult',
    'QueueCleanupCandidate',
    'QueueCleanupSelector',
  ],
  'durableQueue.ts': [
    'D1Allocator',
    'DurableI6Slot',
    'DurableQueueAppend',
    'DurableQueueOptions',
    'DurableQueueRevisionReplacement',
    'DurableQueueScope',
    'DurableQueueSlot',
    'DurableQueueTombstoneOperation',
    'I6AcceptedAtResolution',
    'I6EvacuationInjections',
    'I6PersistenceInjections',
    'StoragePersistenceRequester',
  ],
  'eventFieldRules.ts': [
    'EventFieldConditionContext',
    'EventFieldPresence',
    'EventFieldRequiredness',
    'EventFieldRule',
    'EventFieldShape',
    'EventSlotId',
    'RequestOnlyId',
    'SyncEventPath',
  ],
  'eventKinds.ts': [
    'EventKind',
    'EventKindGroup',
    'EventKindId',
    'EventParticipation',
  ],
  'failureScenarioContract.ts': [
    'FailureExpectedFieldId',
    'FailureScenarioComparisonUnit',
    'FailureScenarioContract',
    'FailureScenarioField',
    'FailureScenarioId',
    'FailureScenarioObservation',
    'FailureScenarioResult',
  ],
  'idempotencyCollision.ts': [
    'ContentIdentity',
    'IdempotencyBoundaryResult',
    'IdempotencyDecisionResult',
    'IdempotencyEventOriginal',
    'IdempotencyKeyPart',
    'IdempotencyOperation',
    'IdempotencyOriginal',
    'IdempotencyOriginalComparator',
    'IdempotencyScopeRule',
    'StoredIdempotencyOperation',
  ],
  'k5Tombstone.ts': [
    'TombstoneBoundaryRequest',
    'TombstoneGenerationInjections',
    'TombstoneGenerationRequest',
    'TombstoneGenerationResult',
    'TombstoneOnlineState',
    'TombstoneQueueSlotReplacement',
    'TombstoneRecordingRightVerifier',
    'TombstoneSourceSlot',
  ],
  'localQueueFile.ts': [
    'LocalQueueB4Event',
    'LocalQueueFileCodec',
    'LocalQueueFileEnvelope',
    'LocalQueueFileExportInjections',
    'LocalQueueFileExportRequest',
    'LocalQueueFileImportInjections',
    'LocalQueueFileImportRequest',
    'LocalQueueFileImportResult',
    'LocalQueueFileProvenance',
  ],
  'mappingConfirmationGate.ts': [
    'MappingConfirmationGateResult',
    'MappingConfirmationInjections',
    'MappingConfirmationRequest',
    'PlayerRegistrationMappingResolver',
  ],
  'p3Result.ts': [
    'P3AcceptedResultEnvelope',
    'P3RejectedResultEnvelope',
    'P3ResultEnvelope',
  ],
  'playerIdMapping.ts': [
    'ConfirmedPlayerIdMapping',
    'PlayerIdMappingReception',
    'PlayerIdMappingReceptionRequest',
    'PlayerIdMappingResponse',
    'PlayerIdMappingTarget',
  ],
  'requestBoundary.ts': [
    'P3RequestState',
    'RecoveryGenerationVerifier',
    'RequestBoundaryCheckResult',
    'RequestBoundaryEnvelope',
    'RequestBoundaryResult',
    'RequestBoundaryVerifiers',
    'V12BindingComponent',
    'V12BindingVerifier',
  ],
  'singleWriter.ts': [
    'ExclusiveLockManager',
    'NonOwnerInputRejection',
    'SingleWriterInjections',
    'SingleWriterPreconditionId',
    'SingleWriterPreconditions',
    'SingleWriterRequest',
    'SingleWriterResult',
    'SingleWriterRevalidationContext',
    'SingleWriterStartFailure',
  ],
  'queueState.ts': [
    'I6Acceptance',
    'I6AcceptedResult',
    'I6HoldingContract',
    'I6HoldingContractElement',
    'QueueActionRequiredLabel',
    'QueueState',
    'QueueStateId',
  ],
  'queueTransition.ts': [
    'B3ReasonClassification',
    'QueueEventKey',
    'QueueSlot',
    'QueueTransitionInjections',
    'QueueTransitionRequest',
    'QueueTransitionResult',
    'QueueTransitionRowId',
    'QueueTransitionRule',
    'Rg1State',
  ],
  'rejectionReason.ts': [
    'B3ContentBranch',
    'B3ContentRejection',
    'B3O4Rejection',
    'B3Rejection',
  ],
  'syncEvent.ts': [
    'SidecarJoinKey',
    'SyncEvent',
    'SyncEventEnvelopeKey',
    'TargetEventReference',
  ],
  'syncNotices.ts': [
    'SyncNoticeDescriptor',
    'SyncNoticeId',
    'SyncNoticeParamsById',
  ],
  'temporaryIdMapping.ts': [
    'TemporaryIdMappingRecord',
    'TemporaryIdProvenance',
  ],
  'validateSyncEvent.ts': [
    'SourceEventContext',
    'SourceEventContextResolver',
    'SyncEventValidationContext',
    'SyncEventValidationResult',
    'SyncEventViolation',
    'SyncEventViolationType',
  ],
} as const satisfies Readonly<Record<string, readonly string[]>>

const EXPECTED_TESTING_SOURCE_FILE_NAMES = [
  'testing/failureScenarioAdapter.ts',
] as const

const EXPECTED_SCANNED_SOURCE_FILE_NAMES = [
  ...EXPECTED_PRODUCT_FILE_NAMES,
  ...EXPECTED_TESTING_SOURCE_FILE_NAMES,
] as const

const rawModules = import.meta.glob<RawModule>(
  ['./**/*.ts', '../../testing/**/*.ts'],
  {
    query: '?raw',
    eager: true,
  },
)
const productModules = import.meta.glob<ProductModule>(
  ['./**/*.ts', '!./**/*.spec.ts'],
  { eager: true },
)

function scannedFileName(path: string): string {
  if (path.startsWith('./')) {
    return path.slice(2)
  }
  const testingPrefix = '../../testing/'
  if (path.startsWith(testingPrefix)) {
    return `testing/${path.slice(testingPrefix.length)}`
  }
  throw new Error(`未知の raw 走査対象パスです: ${path}`)
}

const scannedSources: readonly ProductSource[] = Object.entries(rawModules)
  .map(([path, module]) => ({
    fileName: scannedFileName(path),
    source: module.default,
  }))
  .filter((entry) => !entry.fileName.endsWith('.spec.ts'))

const productSources = scannedSources.filter(
  (entry) => !entry.fileName.startsWith('testing/'),
)

const actualProductFileNames = productSources
  .map((entry) => entry.fileName)
  .sort()
const expectedProductFileNames = [...EXPECTED_PRODUCT_FILE_NAMES].sort()
if (
  actualProductFileNames.length !== expectedProductFileNames.length ||
  actualProductFileNames.some(
    (fileName, index) => fileName !== expectedProductFileNames[index],
  )
) {
  throw new Error(
    `走査対象の製品ファイル集合が一致しません: ${actualProductFileNames.join(',')}`,
  )
}
const actualScannedSourceFileNames = scannedSources
  .map((entry) => entry.fileName)
  .sort()
const expectedScannedSourceFileNames = [
  ...EXPECTED_SCANNED_SOURCE_FILE_NAMES,
].sort()
if (
  actualScannedSourceFileNames.length !==
    expectedScannedSourceFileNames.length ||
  actualScannedSourceFileNames.some(
    (fileName, index) => fileName !== expectedScannedSourceFileNames[index],
  )
) {
  throw new Error(
    `raw 走査対象のファイル集合が一致しません: ${actualScannedSourceFileNames.join(',')}`,
  )
}
const PRODUCT_SOURCES = Object.freeze(productSources)
const SCANNED_SOURCES = Object.freeze(scannedSources)

function byPattern(pattern: RegExp): (source: string) => boolean {
  return (source) => pattern.test(source)
}

const NUMBERING_PATTERN = /採番/
const NUMBERING_CONTEXT_PATTERN = /退避|取り込み/
const IMPORT_PATTERN = /取り込み/
const EVACUATED_PATTERN = /退避/

export function matchesForbiddenImportContext(source: string): boolean {
  return source
    .split(/\r\n?|\n/)
    .some((line) => IMPORT_PATTERN.test(line) && EVACUATED_PATTERN.test(line))
}

export function matchesForbiddenNumberingContext(source: string): boolean {
  return source
    .split(/\r\n?|\n/)
    .some(
      (line) =>
        NUMBERING_PATTERN.test(line) && NUMBERING_CONTEXT_PATTERN.test(line),
    )
}

// U-1〜U-4 は日本語の正本語が現れるかだけを走査し、意味の同一性までは判定しない。
// 型プロパティ名や内部構造による同等物は検出できないため、H-59 の人間逐行確認へ送る。
const OUT_OF_SCOPE_CANDIDATES = {
  U1: [
    { name: '対象連番', matches: byPattern(/対象連番/) },
    { name: '欠落範囲', matches: byPattern(/欠落範囲/) },
  ],
  U2: [
    { name: '退避イベント', matches: byPattern(/退避イベント/) },
    {
      name: '退避取り込み',
      matches: matchesForbiddenImportContext,
    },
    { name: '挿入位置', matches: byPattern(/挿入位置/) },
    { name: '採番', matches: matchesForbiddenNumberingContext },
    { name: '凍結', matches: byPattern(/凍結/) },
  ],
  U3: [{ name: '保持期限', matches: byPattern(/保持期限/) }],
  U4: [{ name: '正史復元', matches: byPattern(/正史復元/) }],
} as const satisfies Readonly<Record<string, readonly ForbiddenCandidate[]>>

const V_IDS = [
  'V1',
  'V2',
  'V3',
  'V4',
  'V5',
  'V6',
  'V7',
  'V8',
  'V9',
  'V10',
  'V11',
  'V12',
] as const

const EVENT_KIND_IDS = [
  '1',
  '2',
  '3',
  '4',
  '5',
  '6',
  '7',
  '8',
  '9',
  '10',
  '11',
  '12',
] as const

const VERIFICATION_ROWS = [
  'V1 べき等キーD5 → eventFieldRules.ts / EVENT_FIELD_RULES・EVENT_IDENTIFIER_SLOT_IDS',
  'V2 イベント連番D1 → eventFieldRules.ts / EVENT_FIELD_RULES（D1 付き経路必須・P3 禁止条件）',
  'V3 記録権世代D4 → eventFieldRules.ts / EVENT_FIELD_RULES（D1 付き経路必須・P3 禁止条件）',
  'V4 試合の識別 → eventFieldRules.ts / EVENT_FIELD_RULES（全イベント無条件）',
  'V5 イベント種別 → eventFieldRules.ts / EVENT_FIELD_RULES（全イベント無条件）',
  'V6 論理位置を定める値D2 → eventFieldRules.ts / EVENT_FIELD_RULES（参加区分条件・P3 禁止条件）',
  'V7 ペイロード → eventFieldRules.ts / EVENT_FIELD_RULES（全イベント無条件）',
  'V8 状態差分 → eventFieldRules.ts / EVENT_FIELD_RULES（取消可能条件・P3 禁止条件）',
  'V9 置換・墓標の状態 → eventFieldRules.ts / EVENT_FIELD_RULES（墓標・改訂条件・P3 禁止条件）',
  'V10 対象イベントの参照 → syncEvent.ts / TargetEventReference（試合・対象の D4・対象の D1）',
  'V11 対象の期待版 → eventFieldRules.ts / EVENT_FIELD_RULES（P3 必須条件）',
  'V12 記録権証明 → requestBoundary.ts / RequestBoundaryEnvelope・V12_BOUNDARY_RULES',
  '#1 毎球入力 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）',
  '#2 undo → eventKinds.ts / EVENT_KIND_RULES（群 A・従属）',
  '#3 選手交代 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）',
  '#4 タイブレーク開始 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）',
  '#5 試合終了宣言 → eventKinds.ts / EVENT_KIND_RULES（群 A・論理位置を持つ）',
  '#6 選手のその場登録 → eventKinds.ts / EVENT_KIND_RULES（群 A・同期順のみ）',
  '#7 状態補正 → eventKinds.ts / EVENT_KIND_RULES・buildSyncEventKindSet（群 A・論理位置を持つ）',
  '#8 墓標 → eventKinds.ts / EVENT_KIND_RULES（群 A・同期順のみ）',
  '#9 改訂版 → eventKinds.ts / EVENT_KIND_RULES（群 A・元イベントの参加区分を継承）',
  '#10 プレイの修正 → eventKinds.ts / EVENT_KIND_RULES（群 B・従属・変更版順あり）',
  '#11 プレイ行の論理削除 → eventKinds.ts / EVENT_KIND_RULES（群 B・従属・変更版順あり）',
  '#12 交代イベントの修正 → eventKinds.ts / EVENT_KIND_RULES（群 B・従属・変更版順あり）',
] as const

const QUEUE_STATE_VERIFICATION_ROWS = [
  `状態 ${queueStateId('未送信')} → queueState.ts / QUEUE_STATES（確定前・自動破棄しない）`,
  `状態 ${queueStateId('要操作')} → queueState.ts / QUEUE_STATES（自動再送・自動破棄の対象外）`,
  `状態 ${queueStateId('同期済み')} → queueState.ts / QUEUE_STATES（端末永続化済み結果を保持）`,
  `状態 ${queueStateId('退避済み')} → queueState.ts / QUEUE_STATES（閲覧・書き出し対象）`,
  `要操作下位 ${actionRequiredLabelId('改訂待ち')} → queueState.ts / QUEUE_ACTION_REQUIRED_LABELS`,
  `要操作下位 ${actionRequiredLabelId('墓標待ち')} → queueState.ts / QUEUE_ACTION_REQUIRED_LABELS`,
  `要操作下位 ${actionRequiredLabelId('管理者対応待ち')} → queueState.ts / QUEUE_ACTION_REQUIRED_LABELS`,
] as const

const I6_VERIFICATION_ROWS = I6_HOLDING_CONTRACT.elements.map(
  (element) =>
    `${I6_HOLDING_CONTRACT.id} ${I6_HOLDING_CONTRACT.name} / ${element.id} → queueState.ts / I6_HOLDING_CONTRACT`,
)

const TRANSITION_VERIFICATION_ROWS = QUEUE_TRANSITION_RULES.map((rule) => {
  const a5ResultIds =
    'a5ResultIds' in rule.condition
      ? ` / A5=${rule.condition.a5ResultIds.join('+')}`
      : ''
  return `${rule.id} ${rule.source} → ${rule.target} / ${rule.trigger} / ${rule.condition.kind}${a5ResultIds} / 許可=${rule.transitionAllowed} / 状態変更=${rule.changesState}`
})

const CLIENT_RULE_VERIFICATION_ROWS = [
  'Q1 新規スロットの追記と D1 採番を不可分に永続化 → durableQueue.ts',
  'Q2 同一ブラウザの複数タブは単一の書き手だけが記録 → singleWriter.ts',
  `${CLIENT_DISCIPLINE_RULES[0].id} 警告閾値でも記録をブロックしない → clientDiscipline.ts`,
  'Q4 未送信件数を常時表示する記述子 → syncNotices.ts',
  'Q5 キュー空の同期成功時に試合と球数を通知する記述子 → syncNotices.ts',
  'Q6 永続ストレージ要求の拒否を警告する記述子 → syncNotices.ts',
  `${CLIENT_DISCIPLINE_RULES[1].id} 認証失効でもキューを失わず再ログイン後に同期再開 → clientDiscipline.ts`,
  'Q2-a 単一書き手選出の6前提 → singleWriter.ts / SINGLE_WRITER_PRECONDITION_IDS',
  'Q2-b 非所有タブの記録不可と旧タブ終了の導線 → syncNotices.ts / singleWriter.ts',
  'Q2-c ロック保持中の非所有タブ入力を未受理にする → singleWriter.ts',
  'Q2-r1 steal を使わない → singleWriter.ts',
  'Q2-r2 コンテキスト終了時の解放後に待機側が取得 → singleWriter.ts',
  'Q2-r3 同一 storage bucket の永続キューを保持 → durableQueue.ts / singleWriter.ts',
  'Q2-r4 ロック取得後かつ記録開始前に単一書き手を再検証 → singleWriter.ts',
] as const

const LOCAL_QUEUE_VERIFICATION_ROWS = [
  'X1 書き出しで D1・D4・D5 を含むイベントの原形を保持 → localQueueFile.ts',
  'X2 取り込み専用の重複判定を作らず通常キューへ流す → localQueueFile.ts',
  'X3 単一の試合・D4 と要求境界 verifier の成立時だけ取り込み → localQueueFile.ts',
  'X4 同一端末・同一ブラウザだけを保証 → localQueueFile.ts',
] as const

const SPECIAL_RULE_VERIFICATION_ROWS = [
  'K5 オンライン記録権確認後に同じ D1 の墓標版へ不可分置換 → k5Tombstone.ts',
  'C4 写像確定まで当該イベントを同期済みにしない → mappingConfirmationGate.ts',
] as const

const W4_VERIFICATION_ROWS = [
  'W4 オンライン前提 → 進行中 P3 は適用 / 終了後 P3 も適用',
  'W4 記録権保持前提 → 進行中 P3 は要求境界で照合 / 終了後 P3 は適用しない',
  'W4 未同期キュー空前提 → 進行中 P3 は適用 / 終了後 P3 は適用しない',
] as const

const STEP_13_VERIFICATION_ROWS = [
  ...QUEUE_STATE_VERIFICATION_ROWS,
  ...I6_VERIFICATION_ROWS,
  ...TRANSITION_VERIFICATION_ROWS,
  ...CLIENT_RULE_VERIFICATION_ROWS,
  ...LOCAL_QUEUE_VERIFICATION_ROWS,
  ...SPECIAL_RULE_VERIFICATION_ROWS,
  ...W4_VERIFICATION_ROWS,
] as const

function sourceFor(fileName: string): string {
  const productSource = PRODUCT_SOURCES.find(
    (candidate) => candidate.fileName === fileName,
  )
  if (!productSource) {
    throw new Error(`走査対象の製品ファイルがありません: ${fileName}`)
  }
  return productSource.source
}

function moduleFor(fileName: string): ProductModule {
  const productModule = productModules[`./${fileName}`]
  if (!productModule) {
    throw new Error(`検査対象の製品 module がありません: ${fileName}`)
  }
  return productModule
}

function expectCandidatesAbsent(
  candidates: readonly ForbiddenCandidate[],
): void {
  for (const candidate of candidates) {
    for (const productSource of SCANNED_SOURCES) {
      expect(
        candidate.matches(productSource.source),
        `${productSource.fileName} に ${candidate.name} が現れています`,
      ).toBe(false)
    }
  }
}

function expectEventSlotsToMatchCanon(): void {
  const canonRules = readCanonEventFieldRules()
  const implementationIds = EVENT_FIELD_RULES.map((rule) => rule.id)
  const canonIds = canonRules.map((rule) => rule.id)
  const canonEventSlotIds = canonRules
    .filter(
      (rule) => rule.requiredness !== EVENT_FIELD_REQUIREDNESS.REQUEST_LEVEL,
    )
    .map((rule) => rule.id)

  expect(implementationIds).toHaveLength(canonIds.length)
  expect(new Set(implementationIds)).toEqual(new Set(canonIds))
  expect(EVENT_SLOT_IDS).toHaveLength(canonEventSlotIds.length)
  expect(new Set(EVENT_SLOT_IDS)).toEqual(new Set(canonEventSlotIds))
}

function hasExportModifier(node: ts.Node): boolean {
  return (
    ts.canHaveModifiers(node) &&
    (ts
      .getModifiers(node)
      ?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword) ??
      false)
  )
}

function exportedTypeIdentifiers(
  productSource: ProductSource,
): readonly string[] {
  const sourceFile = ts.createSourceFile(
    productSource.fileName,
    productSource.source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  )
  const identifiers: string[] = []

  for (const statement of sourceFile.statements) {
    if (
      (ts.isTypeAliasDeclaration(statement) ||
        ts.isInterfaceDeclaration(statement)) &&
      hasExportModifier(statement)
    ) {
      identifiers.push(statement.name.text)
      continue
    }
    if (!ts.isExportDeclaration(statement)) {
      continue
    }
    if (!statement.exportClause) {
      if (statement.isTypeOnly) {
        identifiers.push('*')
      }
    } else if (ts.isNamespaceExport(statement.exportClause)) {
      if (statement.isTypeOnly) {
        identifiers.push(statement.exportClause.name.text)
      }
    } else {
      identifiers.push(
        ...statement.exportClause.elements
          .filter((element) => statement.isTypeOnly || element.isTypeOnly)
          .map((element) => element.name.text),
      )
    }
  }
  return identifiers
}

function expectExactOwnKeys(
  value: object,
  expectedKeys: readonly PropertyKey[],
): void {
  const actualKeys = Reflect.ownKeys(value)
  expect(actualKeys).toHaveLength(expectedKeys.length)
  expect(new Set(actualKeys)).toEqual(new Set(expectedKeys))
}

function exactStringLiterals(source: string, valuePattern: string): string[] {
  const pattern = new RegExp(`(['"])(${valuePattern})\\1`, 'g')
  return [...source.matchAll(pattern)]
    .map((match) => match[2])
    .filter((value): value is string => value !== undefined)
}

function durableQueuePublicMethods(
  source: string,
): readonly ts.MethodDeclaration[] {
  const sourceFile = ts.createSourceFile(
    'durableQueue.ts',
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  )
  const durableQueueClass = sourceFile.statements.find(
    (statement): statement is ts.ClassDeclaration =>
      ts.isClassDeclaration(statement) &&
      statement.name?.text === 'DurableQueue',
  )
  if (!durableQueueClass) {
    throw new Error('DurableQueue class がありません')
  }
  return durableQueueClass.members
    .filter((member): member is ts.MethodDeclaration =>
      ts.isMethodDeclaration(member),
    )
    .filter(
      (member) =>
        !ts
          .getModifiers(member)
          ?.some(
            (modifier) =>
              modifier.kind === ts.SyntaxKind.PrivateKeyword ||
              modifier.kind === ts.SyntaxKind.ProtectedKeyword ||
              modifier.kind === ts.SyntaxKind.StaticKeyword,
          ),
    )
}

function methodName(method: ts.MethodDeclaration): string | undefined {
  return ts.isIdentifier(method.name) ? method.name.text : undefined
}

function hasReadwriteTransaction(method: ts.MethodDeclaration): boolean {
  let found = false
  const visit = (node: ts.Node): void => {
    if (
      ts.isCallExpression(node) &&
      ts.isPropertyAccessExpression(node.expression) &&
      node.expression.name.text === 'transaction' &&
      node.arguments[1] !== undefined &&
      ts.isStringLiteral(node.arguments[1]) &&
      node.arguments[1].text === 'readwrite'
    ) {
      found = true
      return
    }
    ts.forEachChild(node, visit)
  }
  if (method.body) {
    visit(method.body)
  }
  return found
}

function sameStringSet(
  first: readonly string[],
  second: readonly string[],
): boolean {
  return (
    first.length === second.length &&
    first.every((value) => second.includes(value))
  )
}

describe('prohibitions', () => {
  it('raw 走査対象を再帰取得し、製品ファイルの完全集合と一致させる', () => {
    expect(EXPECTED_PRODUCT_FILE_NAMES.length).toBeGreaterThan(0)
    expect(PRODUCT_SOURCES.length).toBeGreaterThan(0)
    expect(PRODUCT_SOURCES.map((entry) => entry.fileName).sort()).toEqual(
      [...EXPECTED_PRODUCT_FILE_NAMES].sort(),
    )
    expect(
      Object.keys(productModules)
        .map((path) => path.slice(2))
        .sort(),
    ).toEqual([...EXPECTED_PRODUCT_FILE_NAMES].sort())
    expect(PRODUCT_SOURCES.every((entry) => entry.source.length > 0)).toBe(true)
    expect(
      PRODUCT_SOURCES.every((entry) => !entry.fileName.endsWith('.spec.ts')),
    ).toBe(true)
    expect(SCANNED_SOURCES.map((entry) => entry.fileName).sort()).toEqual(
      [...EXPECTED_SCANNED_SOURCE_FILE_NAMES].sort(),
    )
    expect(
      SCANNED_SOURCES.some(
        (entry) =>
          entry.fileName === EXPECTED_TESTING_SOURCE_FILE_NAMES[0] &&
          entry.source.length > 0,
      ),
    ).toBe(true)
    expect(
      SCANNED_SOURCES.every((entry) => !entry.fileName.endsWith('.spec.ts')),
    ).toBe(true)
  })

  it('P-02: サイドカー結合キーを試合・D4・D1の3要素だけで作る', () => {
    const game = {}
    const recordingRightsGeneration = {}
    const eventSequence = {}
    const key = buildSidecarJoinKey(
      game,
      recordingRightsGeneration,
      eventSequence,
    )

    expect(TARGET_EVENT_REFERENCE_ELEMENTS).toEqual([
      '試合',
      '対象の D4',
      '対象の D1',
    ])
    expect(key).toHaveLength(3)
    expect(key).toEqual([game, recordingRightsGeneration, eventSequence])
    expect(key[0]).toBe(game)
    expect(key[1]).toBe(recordingRightsGeneration)
    expect(key[2]).toBe(eventSequence)
  })

  it('P-20: 利用者・入力者の追加を許さず、イベント封筒を正本の完全なスロット集合に閉じる', () => {
    const exactEnvelopeType: ExactKeySet<
      keyof SyncEvent,
      (typeof SYNC_EVENT_ENVELOPE_KEYS)[number]
    > = true
    type EnvelopeSlotId = keyof SyncEvent['fields']
    const exactSlotType: ExactKeySet<EnvelopeSlotId, EventSlotId> = true

    // 機械検査は追加スロットの不在までとし、不透明値内部の意味は H-59 の人間逐行確認へ送る。
    expect(SYNC_EVENT_ENVELOPE_KEYS).toEqual(['fields'])
    expect(exactEnvelopeType).toBe(true)
    expect(exactSlotType).toBe(true)
    expectEventSlotsToMatchCanon()
  })

  it('P-24: キュー要素を SyncEvent 単位に閉じ、プレイ行の列を受け取らない', () => {
    const event: SyncEvent = { fields: {} }
    const append: DurableQueueAppend = {
      scope: { game: {}, d4: {} },
      d5: {},
      version: {},
      event,
    }
    const slot: DurableQueueSlot = {
      game: {},
      d4: {},
      d1: 1,
      d5: {},
      version: {},
      event,
      state: queueStateId('未送信'),
    }
    const playRowSequence = [{ id: {} }]
    const invalidEventAppend: DurableQueueAppend = {
      ...append,
      // @ts-expect-error キュー要素にはプレイ行の列を渡せない。
      event: playRowSequence,
    }
    const invalidPlayRowColumn: DurableQueueAppend = {
      ...append,
      // @ts-expect-error キュー入力にプレイ行の列を追加できない。
      playRows: playRowSequence,
    }
    const exactAppendKeys: ExactKeySet<
      keyof DurableQueueAppend,
      'scope' | 'd5' | 'version' | 'event'
    > = true
    const exactSlotKeys: ExactKeySet<
      keyof DurableQueueSlot,
      | 'game'
      | 'd4'
      | 'd1'
      | 'd5'
      | 'version'
      | 'event'
      | 'state'
      | 'actionRequiredLabel'
    > = true
    const exactAppendEvent: ExactKeySet<
      DurableQueueAppend['event'],
      SyncEvent
    > = true
    const exactSlotEvent: ExactKeySet<DurableQueueSlot['event'], SyncEvent> =
      true

    expect([
      exactAppendKeys,
      exactSlotKeys,
      exactAppendEvent,
      exactSlotEvent,
    ]).toEqual([true, true, true, true])
    expect(append.event).toBe(event)
    expect(slot.event).toBe(event)
    expect(invalidEventAppend.event).toBe(playRowSequence)
    expect(Object.hasOwn(invalidPlayRowColumn, 'playRows')).toBe(true)
  })

  it('K5: 汎用置換を公開せず、D6 と D7 の入口を分離する', () => {
    type ReplacementMethod = Extract<
      keyof DurableQueue,
      'replace' | 'replaceRevision' | 'replaceWithTombstone'
    >
    const exactReplacementMethods: ExactKeySet<
      ReplacementMethod,
      'replaceRevision' | 'replaceWithTombstone'
    > = true
    const invalidLowLevelReplace = (queue: DurableQueue) => {
      // @ts-expect-error K5 を迂回する汎用置換 API は公開しない。
      return queue.replace
    }

    expect(exactReplacementMethods).toBe(true)
    expect(Object.hasOwn(DurableQueue.prototype, 'replace')).toBe(false)
    expect(invalidLowLevelReplace).toBeTypeOf('function')
  })

  it('H-78: DurableQueue の公開変更メソッドを不透明 preparation / receipt 境界に閉じる', () => {
    type MutationMethodName = {
      [
        Name in keyof typeof DURABLE_QUEUE_PUBLIC_METHOD_RULES
      ]: (typeof DURABLE_QUEUE_PUBLIC_METHOD_RULES)[Name] extends {
        effect: 'mutation'
      }
        ? Name
        : never
    }[keyof typeof DURABLE_QUEUE_PUBLIC_METHOD_RULES]
    type MutationBoundary = DurableQueuePreparation | I6EvacuationReceipt
    type UnsafeMutationMethod = {
      [Name in MutationMethodName]: Parameters<
        DurableQueue[Name]
      >[0] extends MutationBoundary
        ? never
        : Name
    }[MutationMethodName]
    const noUnsafeMutationMethod: ExactKeySet<UnsafeMutationMethod, never> =
      true
    const publicMethods = durableQueuePublicMethods(
      sourceFor('durableQueue.ts'),
    )
    const publicMethodNames = publicMethods
      .map(methodName)
      .filter((name): name is string => name !== undefined)
    const mutationRuleEntries = Object.entries(
      DURABLE_QUEUE_PUBLIC_METHOD_RULES,
    ).filter((entry) => entry[1].effect === 'mutation')
    const readwriteMethodNames = publicMethods
      .filter(hasReadwriteTransaction)
      .map(methodName)
      .filter((name): name is string => name !== undefined)

    expect(noUnsafeMutationMethod).toBe(true)
    expect(new Set(publicMethodNames)).toEqual(
      new Set(Object.keys(DURABLE_QUEUE_PUBLIC_METHOD_RULES)),
    )
    expect(mutationRuleEntries).toHaveLength(5)
    expect(new Set(readwriteMethodNames)).toEqual(
      new Set(mutationRuleEntries.map(([name]) => name)),
    )
    expect(
      mutationRuleEntries.every(
        ([, rule]) =>
          'boundary' in rule &&
          (rule.boundary === 'preparation' || rule.boundary === 'receipt'),
      ),
    ).toBe(true)
  })

  it('変異: readwrite の新メソッドを read と自己申告しても AST 集合検査で検出する', () => {
    const mutatedSource = sourceFor('durableQueue.ts').replace(
      '  close(): void {',
      `  misclassifiedMutation(): void {
    this.#database.transaction('queue', 'readwrite')
  }

  close(): void {`,
    )
    const readwriteMethodNames = durableQueuePublicMethods(mutatedSource)
      .filter(hasReadwriteTransaction)
      .map(methodName)
      .filter((name): name is string => name !== undefined)
    const mutatedRules = {
      ...DURABLE_QUEUE_PUBLIC_METHOD_RULES,
      misclassifiedMutation: { effect: 'read' },
    } as const
    const declaredMutationNames = Object.entries(mutatedRules)
      .filter((entry) => entry[1].effect === 'mutation')
      .map(([name]) => name)

    expect(readwriteMethodNames).toContain('misclassifiedMutation')
    expect(sameStringSet(readwriteMethodNames, declaredMutationNames)).toBe(
      false,
    )
  })

  it('I6: 保持結果を5要素の別フィールドに閉じ、期限・回収用フィールドを持たない', () => {
    type AcceptedResultKeys = keyof I6AcceptedResult
    const exactAcceptedResultKeys: ExactKeySet<
      AcceptedResultKeys,
      | 'targetReference'
      | 'expectedVersion'
      | 'd5'
      | 'confirmedContent'
      | 'acceptedAt'
    > = true
    type ForbiddenHoldingKeys = Extract<
      AcceptedResultKeys,
      'retentionDeadline' | 'expiresAt' | 'recoveryState'
    >
    const noForbiddenHoldingKeys: ExactKeySet<ForbiddenHoldingKeys, never> =
      true
    const invalidReceipt = (slot: DurableI6Slot) => {
      // @ts-expect-error 永続化を通らない receipt は型から生成できない。
      return new I6PersistenceReceipt(slot, Symbol('forged receipt'))
    }

    expect(exactAcceptedResultKeys).toBe(true)
    expect(noForbiddenHoldingKeys).toBe(true)
    expect(invalidReceipt).toBeTypeOf('function')
    expect(
      Object.keys(moduleFor('durableQueue.ts')).filter((name) =>
        /recover|reapply|restore/i.test(name),
      ),
    ).toEqual([])
  })

  it('P3 独立応答を D1 ACK から分離し、受理だけを既存 I6 全組へ結合する', () => {
    const exactAcceptedEnvelopeKeys: ExactKeySet<
      keyof P3AcceptedResultEnvelope,
      'boundaryResult' | 'acceptedResult'
    > = true
    const exactRejectedEnvelopeKeys: ExactKeySet<
      keyof P3RejectedResultEnvelope,
      'boundaryResult'
    > = true
    const exactAcceptedResult: ExactKeySet<
      P3AcceptedResultEnvelope['acceptedResult'],
      I6AcceptedResult
    > = true
    const exactEnvelopeUnion: ExactKeySet<
      P3ResultEnvelope,
      P3AcceptedResultEnvelope | P3RejectedResultEnvelope
    > = true
    type P3EnvelopeKey =
      keyof P3AcceptedResultEnvelope | keyof P3RejectedResultEnvelope
    type ForbiddenD1AckKey = Extract<
      P3EnvelopeKey,
      'd1' | 'd3' | 'a3' | 'a5' | 'advancedD3' | 'eventResults' | 'a5Result'
    >
    const noD1AckKey: ExactKeySet<ForbiddenD1AckKey, never> = true

    const sourceFile = ts.createSourceFile(
      'p3Result.ts',
      sourceFor('p3Result.ts'),
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS,
    )
    const queueStateImport = sourceFile.statements.find(
      (statement): statement is ts.ImportDeclaration =>
        ts.isImportDeclaration(statement) &&
        ts.isStringLiteral(statement.moduleSpecifier) &&
        statement.moduleSpecifier.text === './queueState',
    )
    const importedI6Types =
      queueStateImport?.importClause?.namedBindings &&
      ts.isNamedImports(queueStateImport.importClause.namedBindings)
        ? queueStateImport.importClause.namedBindings.elements.map(
            (element) => element.name.text,
          )
        : []
    const locallyDeclaredTypeNames = sourceFile.statements
      .filter(
        (
          statement,
        ): statement is ts.TypeAliasDeclaration | ts.InterfaceDeclaration =>
          ts.isTypeAliasDeclaration(statement) ||
          ts.isInterfaceDeclaration(statement),
      )
      .map((statement) => statement.name.text)

    expect([
      exactAcceptedEnvelopeKeys,
      exactRejectedEnvelopeKeys,
      exactAcceptedResult,
      exactEnvelopeUnion,
      noD1AckKey,
    ]).toEqual([true, true, true, true, true])
    expect(new Set(importedI6Types)).toEqual(
      new Set(['I6Acceptance', 'I6AcceptedResult']),
    )
    expect(queueStateImport?.importClause?.isTypeOnly).toBe(true)
    expect(locallyDeclaredTypeNames).not.toContain('I6Acceptance')
    expect(locallyDeclaredTypeNames).not.toContain('I6AcceptedResult')
  })

  it('C4: A5 の公開入口は永続キュー発行の preparation だけを受け取る', () => {
    type ApplyA5Request = Extract<QueueTransitionRequest, { kind: 'apply-a5' }>
    type MappingResolver = NonNullable<
      NonNullable<
        Parameters<DurableQueue['prepareA5Transition']>[2]
      >['resolvePlayerRegistrationMapping']
    >
    const preparation = {} as DurableQueuePreparation<'a5-transition'>
    const queue = {} as DurableQueue
    const slot: QueueSlot = {
      state: queueStateId('未送信'),
      source: 'd1-event',
      key: { d4: {}, d1: {}, d5: {} },
      content: {},
    }
    const request: ApplyA5Request = {
      kind: 'apply-a5',
      queue,
      preparation,
    }
    const resolver: MappingResolver = () => true
    const invalidEventKindArgument = {
      kind: 'apply-a5',
      slot,
      eventKind: EVENT_KIND_RULES[0],
    } as unknown as QueueTransitionRequest
    const exactRequestKeys: ExactKeySet<
      keyof ApplyA5Request,
      'kind' | 'queue' | 'preparation'
    > = true

    expect(exactRequestKeys).toBe(true)
    expect(Object.keys(request)).toEqual(['kind', 'queue', 'preparation'])
    expect(resolver({})).toBe(true)
    expect(Object.hasOwn(invalidEventKindArgument, 'eventKind')).toBe(true)
  })

  it('D1 ACK の公開型を D3・A5・条件付き A4 だけに閉じる', () => {
    const exactEnvelopeKeys: ExactKeySet<
      keyof D1AckEnvelope,
      'advancedD3' | 'eventResults' | 'playerIdMappings'
    > = true
    const exactEventResultKeys: ExactKeySet<
      keyof D1AckEventResult,
      'd4' | 'd1' | 'd5' | 'a5Result'
    > = true
    const exactPlayerIdMappingKeys: ExactKeySet<
      keyof D1AckPlayerIdMapping,
      'temporaryId' | 'officialId'
    > = true
    type ServerGuaranteeField = Extract<
      keyof D1AckEnvelope,
      | 'a1'
      | 'a2'
      | 'atomicCommit'
      | 'appliedAtomically'
      | 'idempotencyGuaranteed'
      | 'preventsDoubleApplication'
    >
    const noServerGuaranteeField: ExactKeySet<ServerGuaranteeField, never> =
      true

    expect([
      exactEnvelopeKeys,
      exactEventResultKeys,
      exactPlayerIdMappingKeys,
      noServerGuaranteeField,
    ]).toEqual([true, true, true, true])
  })

  it('境界結果の ACK あり・ACK なし型を discriminant の exact-set に閉じる', () => {
    const exactAckKeys: ExactKeySet<
      keyof AckBoundaryResult,
      'delivery' | 'boundaryResult'
    > = true
    const exactNoAckKeys: ExactKeySet<
      keyof NoAckBoundaryResult,
      'delivery' | 'boundaryResult'
    > = true
    const exactAckDelivery: ExactKeySet<AckBoundaryResult['delivery'], 'ack'> =
      true
    const exactNoAckDelivery: ExactKeySet<
      NoAckBoundaryResult['delivery'],
      'no-ack'
    > = true

    expect([
      exactAckKeys,
      exactNoAckKeys,
      exactAckDelivery,
      exactNoAckDelivery,
    ]).toEqual([true, true, true, true])
  })

  it('B3 の受け取り型に操作者が選ぶラベルを持たせない', () => {
    type ContentClassification = Extract<
      B3ReasonClassification,
      { kind: typeof B3_REASON_KIND.CONTENT }
    >
    const exactClassificationKeys: ExactKeySet<
      keyof ContentClassification,
      'kind'
    > = true
    const exactContentKeys: ExactKeySet<
      keyof B3ContentRejection,
      'kind' | 'branch' | 'reason'
    > = true
    const exactO4Keys: ExactKeySet<
      keyof B3O4Rejection,
      'kind' | 'reason' | 'correctionConfirmation'
    > = true
    type B3VariantKeys = keyof B3ContentRejection | keyof B3O4Rejection
    type ForbiddenLabelKey = Extract<
      B3VariantKeys,
      | 'actionRequiredLabel'
      | 'revisionPending'
      | 'tombstonePending'
      | 'queueState'
    >
    const noForbiddenLabelKey: ExactKeySet<ForbiddenLabelKey, never> = true
    const exactUnion: ExactKeySet<
      B3Rejection,
      B3ContentRejection | B3O4Rejection
    > = true

    expect([
      exactClassificationKeys,
      exactContentKeys,
      exactO4Keys,
      noForbiddenLabelKey,
      exactUnion,
    ]).toEqual([true, true, true, true, true])
  })

  it('A5 語彙を ackEnvelope.ts に再定義せず canonOracle の型と reader だけから得る', () => {
    const sourceFile = ts.createSourceFile(
      'ackEnvelope.ts',
      sourceFor('ackEnvelope.ts'),
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS,
    )
    const canonImport = sourceFile.statements.find(
      (statement): statement is ts.ImportDeclaration =>
        ts.isImportDeclaration(statement) &&
        ts.isStringLiteral(statement.moduleSpecifier) &&
        statement.moduleSpecifier.text === './canonOracle',
    )
    if (
      !canonImport?.importClause?.namedBindings ||
      !ts.isNamedImports(canonImport.importClause.namedBindings)
    ) {
      throw new Error(
        'ackEnvelope.ts に canonOracle の named import がありません',
      )
    }
    const importedIdentifiers =
      canonImport.importClause.namedBindings.elements.map((element) => ({
        name: element.name.text,
        typeOnly: canonImport.importClause?.isTypeOnly || element.isTypeOnly,
      }))
    const canonResultIds = new Set(
      readCanonAckStateResults().map((result) => result.id),
    )
    const duplicatedResultLiterals: string[] = []
    const localLookupCollections: string[] = []
    let switchStatementCount = 0
    const visit = (node: ts.Node): void => {
      if (ts.isStringLiteralLike(node) && canonResultIds.has(node.text)) {
        duplicatedResultLiterals.push(node.text)
      }
      if (
        ts.isNewExpression(node) &&
        ts.isIdentifier(node.expression) &&
        (node.expression.text === 'Map' || node.expression.text === 'Set')
      ) {
        localLookupCollections.push(node.expression.text)
      }
      if (ts.isSwitchStatement(node)) {
        switchStatementCount += 1
      }
      ts.forEachChild(node, visit)
    }
    visit(sourceFile)

    expect(importedIdentifiers).toEqual([
      { name: 'readCanonAckStateResults', typeOnly: false },
      { name: 'CanonAckStateResult', typeOnly: true },
    ])
    expect(duplicatedResultLiterals).toEqual([])
    expect(localLookupCollections).toEqual([])
    expect(switchStatementCount).toBe(0)
  })

  it('P-28: 状態補正を種別集合の要素とし、製品 module の export を exact-set に閉じる', () => {
    const stateCorrection = EVENT_KIND_RULES.find(
      (eventKind) => eventKind.name === '状態補正',
    )

    expect(stateCorrection).toBeDefined()
    expect(buildSyncEventKindSet({ stateCorrectionAdopted: true })).toContain(
      stateCorrection,
    )
    expect(
      buildSyncEventKindSet({ stateCorrectionAdopted: false }),
    ).not.toContain(stateCorrection)
    expect(Object.keys(EXPECTED_VALUE_EXPORTS).sort()).toEqual(
      [...EXPECTED_PRODUCT_FILE_NAMES].sort(),
    )
    for (const productSource of PRODUCT_SOURCES) {
      const expectedExports =
        EXPECTED_VALUE_EXPORTS[
          productSource.fileName as keyof typeof EXPECTED_VALUE_EXPORTS
        ]
      const actualExports = Object.keys(moduleFor(productSource.fileName))

      expect(expectedExports).toBeDefined()
      expect(actualExports).toHaveLength(expectedExports.length)
      expect(new Set(actualExports)).toEqual(new Set(expectedExports))
    }
  })

  it('公開 type-only export を正の exact-set に閉じる', () => {
    expect(Object.keys(EXPECTED_TYPE_EXPORTS).sort()).toEqual(
      [...EXPECTED_PRODUCT_FILE_NAMES].sort(),
    )
    for (const productSource of PRODUCT_SOURCES) {
      const expectedExports =
        EXPECTED_TYPE_EXPORTS[
          productSource.fileName as keyof typeof EXPECTED_TYPE_EXPORTS
        ]
      const actualExports = exportedTypeIdentifiers(productSource)

      expect(expectedExports).toBeDefined()
      expect(actualExports).toHaveLength(expectedExports.length)
      expect(new Set(actualExports)).toEqual(new Set(expectedExports))
    }
  })

  it('公開封筒・検査コンテキスト・戻り値のキーを正の exact-set に閉じる', () => {
    type ValidationSuccess = Extract<SyncEventValidationResult, { ok: true }>
    type ValidationFailure = Extract<SyncEventValidationResult, { ok: false }>
    const exactTargetReference: ExactKeySet<
      keyof TargetEventReference,
      (typeof TARGET_EVENT_REFERENCE_ELEMENTS)[number]
    > = true
    const exactSourceContext: ExactKeySet<
      keyof SourceEventContext,
      'participation' | 'cancellable'
    > = true
    const exactValidationContext: ExactKeySet<
      keyof SyncEventValidationContext,
      'path' | 'eventKinds' | 'sourceEventContextResolver'
    > = true
    const exactViolation: ExactKeySet<
      keyof SyncEventViolation,
      'violation' | 'target'
    > = true
    const exactSuccess: ExactKeySet<keyof ValidationSuccess, 'ok'> = true
    const exactFailure: ExactKeySet<keyof ValidationFailure, 'ok' | 'reason'> =
      true
    const exactReturnType: ExactKeySet<
      ReturnType<typeof checkSyncEvent>,
      SyncEventValidationResult
    > = true
    const exactLocalQueueImportRequest: ExactKeySet<
      keyof LocalQueueFileImportRequest,
      'text' | 'currentScope' | 'boundaryRequest'
    > = true
    const exactLocalQueueScope: ExactKeySet<
      keyof LocalQueueFileImportRequest['currentScope'],
      'game' | 'd4'
    > = true
    const exactLocalQueueImportResult: ExactKeySet<
      keyof LocalQueueFileImportResult,
      'status' | 'scope' | 'importedEvents' | 'b4Events' | 'notImportedEvents'
    > = true
    const exactLocalQueueResultScope: ExactKeySet<
      LocalQueueFileImportResult['scope'],
      LocalQueueFileImportRequest['currentScope']
    > = true
    const event: SyncEvent = {
      fields: { V1: {}, V2: {}, V3: {}, V4: {}, V5: '6', V7: {} },
    }
    const context: SyncEventValidationContext = {
      path: SYNC_EVENT_PATH.P1,
      eventKinds: buildSyncEventKindSet({ stateCorrectionAdopted: true }),
    }
    const success = checkSyncEvent(event, context)
    const failureEvent: SyncEvent = { fields: { ...event.fields } }
    delete failureEvent.fields.V1
    const failure = checkSyncEvent(failureEvent, context)

    expect([
      exactTargetReference,
      exactSourceContext,
      exactValidationContext,
      exactViolation,
      exactSuccess,
      exactFailure,
      exactReturnType,
      exactLocalQueueImportRequest,
      exactLocalQueueScope,
      exactLocalQueueImportResult,
      exactLocalQueueResultScope,
    ]).toEqual([
      true,
      true,
      true,
      true,
      true,
      true,
      true,
      true,
      true,
      true,
      true,
    ])
    expectExactOwnKeys(success, ['ok'])
    if (failure.ok) {
      throw new Error('検査失敗の戻り値がありません')
    }
    expectExactOwnKeys(failure, ['ok', 'reason'])
    expectExactOwnKeys(failure.reason, ['violation', 'target'])
  })

  it('P-32: 投球項目の追加を許さず、V7 の不透明値内部を検査しない', () => {
    const opaquePayload = new Proxy(
      {},
      {
        get() {
          throw new Error('V7 の内部を読みました')
        },
        getOwnPropertyDescriptor() {
          throw new Error('V7 の内部構造を読みました')
        },
        ownKeys() {
          throw new Error('V7 の内部キーを読みました')
        },
      },
    )
    const event: SyncEvent = {
      fields: {
        V1: {},
        V2: {},
        V3: {},
        V4: {},
        V5: '6',
        V7: opaquePayload,
      },
    }

    // 機械検査はスロット集合と非参照動作までとし、ペイロードの意味は H-59 の人間逐行確認へ送る。
    expectEventSlotsToMatchCanon()
    expect(
      exactStringLiterals(sourceFor('validateSyncEvent.ts'), 'V7'),
    ).toEqual([])
    expect(
      checkSyncEvent(event, {
        path: SYNC_EVENT_PATH.P1,
        eventKinds: buildSyncEventKindSet({ stateCorrectionAdopted: true }),
      }),
    ).toEqual({ ok: true })
  })

  it('P-57: V8 を取消可能な操作に限る必須規則として持つ', () => {
    const rule = EVENT_FIELD_RULES.find((candidate) => candidate.id === 'V8')
    const eventKind = EVENT_KIND_RULES.find(
      (candidate) => candidate.name === '状態補正',
    )

    expect(rule).toBeDefined()
    expect(eventKind).toBeDefined()
    if (!rule || !eventKind) {
      throw new Error('V8 または状態補正の規則がありません')
    }
    expect(rule.requiredness).toBe(
      EVENT_FIELD_REQUIREDNESS.EVENT_KIND_CONDITIONAL,
    )
    expect(rule.conditions).toContain('取消可能な操作に限る')
    expect(
      resolveEventFieldPresence(rule, {
        path: SYNC_EVENT_PATH.P1,
        eventKind,
        participation: eventKind.participation,
        cancellable: true,
      }),
    ).toBe(EVENT_FIELD_PRESENCE.REQUIRED)
  })

  it('V-ID リテラルを eventFieldRules.ts の単一 locus に閉じる', () => {
    const valuePattern = 'V(?:[1-9]|1[0-2])'

    expect(V_IDS.length).toBeGreaterThan(0)
    expect(
      new Set(
        exactStringLiterals(sourceFor('eventFieldRules.ts'), valuePattern),
      ),
    ).toEqual(new Set(V_IDS))
    for (const productSource of SCANNED_SOURCES) {
      if (productSource.fileName !== 'eventFieldRules.ts') {
        expect(exactStringLiterals(productSource.source, valuePattern)).toEqual(
          [],
        )
      }
    }
  })

  it('P-58: 種別 ID リテラルを eventKinds.ts の単一 locus に閉じる', () => {
    const valuePattern = '(?:[1-9]|1[0-2])'
    const eventKindLiterals = exactStringLiterals(
      sourceFor('eventKinds.ts'),
      valuePattern,
    )

    expect(EVENT_KIND_IDS.length).toBeGreaterThan(0)
    expect(eventKindLiterals).toEqual([...EVENT_KIND_IDS, '7'])
    for (const productSource of SCANNED_SOURCES) {
      if (productSource.fileName !== 'eventKinds.ts') {
        expect(exactStringLiterals(productSource.source, valuePattern)).toEqual(
          [],
        )
      }
    }
  })

  it.each(Object.entries(OUT_OF_SCOPE_CANDIDATES))(
    '%s の射程外語・構造を持たない',
    (_id, candidates) => {
      expect(candidates.length).toBeGreaterThan(0)
      expectCandidatesAbsent(candidates)
    },
  )

  it.each([
    '(試合, D4) ごとに D1 を採番する',
    '書き出しの時点で採番し直さない',
    '墓標は新しい D1 を採番しない',
  ])('U-2: 通常の採番文脈を許可する: %s', (source) => {
    expect(matchesForbiddenNumberingContext(source)).toBe(false)
  })

  it.each([
    '退避済み資料を現行世代へ取り込み、採番する',
    '退避イベントを取り込むときに採番する',
    '通常の説明\n退避済み資料を採番する\n別の説明',
  ])('U-2: 退避イベントの取り込み文脈を禁止する: %s', (source) => {
    expect(matchesForbiddenNumberingContext(source)).toBe(true)
  })

  it('U-2: 行をまたぐ語の出現を取り込み文脈と判定しない', () => {
    expect(
      matchesForbiddenNumberingContext('退避済み資料\n通常の説明\n採番する'),
    ).toBe(false)
  })

  it('U-2: ローカルキューファイル実装が禁止された採番文脈を持たない', () => {
    expect(
      matchesForbiddenNumberingContext(sourceFor('localQueueFile.ts')),
    ).toBe(false)
    expect(matchesForbiddenImportContext(sourceFor('localQueueFile.ts'))).toBe(
      false,
    )
  })

  it('X2: ローカルキューファイル実装に D5 のローカル判定を持たない', () => {
    expect(sourceFor('localQueueFile.ts')).not.toMatch(/\.d5\b/)
    expect(sourceFor('localQueueFile.ts')).not.toMatch(/duplicateEvents/)
  })

  it('H-59 の逐語照合入力を24行出力する', async () => {
    expect(VERIFICATION_ROWS).toHaveLength(24)
    expect(VERIFICATION_ROWS.filter((row) => row.startsWith('V'))).toHaveLength(
      12,
    )
    expect(VERIFICATION_ROWS.filter((row) => row.startsWith('#'))).toHaveLength(
      12,
    )
    expect(VERIFICATION_ROWS.every((row) => !row.includes('\n'))).toBe(true)

    console.log(VERIFICATION_ROWS.join('\n'))
    await Promise.resolve()
  })

  it('H-59 の実装逐語照合入力を55行出力する', async () => {
    expect(QUEUE_STATE_VERIFICATION_ROWS).toHaveLength(7)
    expect(I6_VERIFICATION_ROWS).toHaveLength(11)
    expect(TRANSITION_VERIFICATION_ROWS).toHaveLength(14)
    expect(CLIENT_RULE_VERIFICATION_ROWS).toHaveLength(14)
    expect(LOCAL_QUEUE_VERIFICATION_ROWS).toHaveLength(4)
    expect(SPECIAL_RULE_VERIFICATION_ROWS).toHaveLength(2)
    expect(W4_VERIFICATION_ROWS).toHaveLength(3)
    expect(STEP_13_VERIFICATION_ROWS).toHaveLength(55)
    expect(STEP_13_VERIFICATION_ROWS.every((row) => !row.includes('\n'))).toBe(
      true,
    )

    console.log(STEP_13_VERIFICATION_ROWS.join('\n'))
    await Promise.resolve()
  })
})
