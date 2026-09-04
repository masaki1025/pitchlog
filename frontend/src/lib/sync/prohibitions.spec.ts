import { describe, expect, it } from 'vitest'
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
import { readCanonEventFieldRules } from './canonOracle'
import {
  buildSidecarJoinKey,
  TARGET_EVENT_REFERENCE_ELEMENTS,
  type SyncEvent,
} from './syncEvent'
import { checkSyncEvent } from './validateSyncEvent'

type RawModule = { default: string }
type ProductModule = Record<string, unknown>
type ProductSource = Readonly<{
  fileName: string
  source: string
}>
type ForbiddenCandidate = Readonly<{
  name: string
  pattern: RegExp
}>

const EXPECTED_PRODUCT_FILE_NAMES = [
  'canonOracle.ts',
  'eventFieldRules.ts',
  'eventKinds.ts',
  'idempotencyCollision.ts',
  'requestBoundary.ts',
  'syncEvent.ts',
  'temporaryIdMapping.ts',
  'validateSyncEvent.ts',
] as const

const EXPECTED_VALUE_EXPORTS = {
  'canonOracle.ts': [
    'CANON_IDEMPOTENCY_OUT_OF_SCOPE',
    'CANON_TEMPORARY_ID_MAPPING_OUT_OF_SCOPE',
    'parseCanonEventFieldRules',
    'parseCanonIdempotencyCollisionRules',
    'parseCanonParticipationRules',
    'parseCanonTemporaryIdMappingRules',
    'parseCanonV12BoundaryRules',
    'readCanonEventFieldRules',
    'readCanonIdempotencyCollisionRules',
    'readCanonParticipationRules',
    'readCanonTemporaryIdMappingRules',
    'readCanonV12BoundaryRules',
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
  'idempotencyCollision.ts': [
    'CONTENT_IDENTITY',
    'IDEMPOTENCY_COLLISION_RULES',
    'IDEMPOTENCY_DECISION',
    'IDEMPOTENCY_SCOPE_RULE',
    'decideIdempotencyCollision',
  ],
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
  'syncEvent.ts': [
    'TARGET_EVENT_REFERENCE_ELEMENTS',
    'buildSidecarJoinKey',
    'isTargetEventReference',
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

const rawModules = import.meta.glob<RawModule>('./**/*.ts', {
  query: '?raw',
  eager: true,
})
const productModules = import.meta.glob<ProductModule>(
  ['./**/*.ts', '!./**/*.spec.ts'],
  { eager: true },
)

const productSources: readonly ProductSource[] = Object.entries(rawModules)
  .filter(([path]) => !path.endsWith('.spec.ts'))
  .map(([path, module]) => ({
    fileName: path.slice(2),
    source: module.default,
  }))

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
const PRODUCT_SOURCES = Object.freeze(productSources)

const OUT_OF_SCOPE_CANDIDATES = {
  U1: [
    { name: '対象連番', pattern: /対象連番/ },
    { name: '欠落範囲', pattern: /欠落範囲/ },
  ],
  U2: [
    { name: '退避イベント', pattern: /退避イベント/ },
    { name: '退避取り込み', pattern: /退避.*取り込み|取り込み.*退避/ },
    { name: '挿入位置', pattern: /挿入位置/ },
    { name: '採番', pattern: /採番/ },
    { name: '凍結', pattern: /凍結/ },
  ],
  U3: [{ name: '保持期限', pattern: /保持期限/ }],
  U4: [{ name: '正史復元', pattern: /正史復元/ }],
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
    for (const productSource of PRODUCT_SOURCES) {
      expect(
        productSource.source,
        `${productSource.fileName} に ${candidate.name} が現れています`,
      ).not.toMatch(candidate.pattern)
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

function exactStringLiterals(source: string, valuePattern: string): string[] {
  const pattern = new RegExp(`(['"])(${valuePattern})\\1`, 'g')
  return [...source.matchAll(pattern)]
    .map((match) => match[2])
    .filter((value): value is string => value !== undefined)
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
    type EnvelopeSlotId = keyof SyncEvent['fields']
    const exactSlotType: EnvelopeSlotId extends EventSlotId
      ? EventSlotId extends EnvelopeSlotId
        ? true
        : false
      : false = true

    // 機械検査は追加スロットの不在までとし、不透明値内部の意味は H-59 の人間逐行確認へ送る。
    expect(exactSlotType).toBe(true)
    expectEventSlotsToMatchCanon()
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
    for (const productSource of PRODUCT_SOURCES) {
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
    for (const productSource of PRODUCT_SOURCES) {
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
})
