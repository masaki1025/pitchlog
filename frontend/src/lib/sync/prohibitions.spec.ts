import { describe, expect, it } from 'vitest'
import {
  EVENT_FIELD_PRESENCE,
  EVENT_FIELD_REQUIREDNESS,
  EVENT_FIELD_RULES,
  resolveEventFieldPresence,
  SYNC_EVENT_PATH,
} from './eventFieldRules'
import { buildSyncEventKindSet, EVENT_KIND_RULES } from './eventKinds'
import {
  buildSidecarJoinKey,
  TARGET_EVENT_REFERENCE_ELEMENTS,
} from './syncEvent'

type RawModule = { default: string }
type ProductSource = Readonly<{
  fileName: string
  source: string
}>
type ForbiddenCandidate = Readonly<{
  name: string
  pattern: RegExp
}>

const rawModules = import.meta.glob<RawModule>('./*.ts', {
  query: '?raw',
  eager: true,
})

const PRODUCT_SOURCES: readonly ProductSource[] = Object.entries(rawModules)
  .filter(([path]) => !path.endsWith('.spec.ts'))
  .map(([path, module]) => ({
    fileName: path.slice(2),
    source: module.default,
  }))

const USER_IDENTITY_CANDIDATES: readonly ForbiddenCandidate[] = [
  { name: 'userId', pattern: /\buserId\b/i },
  { name: 'user_id', pattern: /\buser_id\b/i },
  { name: 'operator', pattern: /\boperator\b/i },
  { name: 'operatorId', pattern: /\boperatorId\b/i },
  { name: 'operator_id', pattern: /\boperator_id\b/i },
  { name: 'inputBy', pattern: /\binputBy\b/i },
  { name: 'input_by', pattern: /\binput_by\b/i },
  { name: 'inputterId', pattern: /\binputterId\b/i },
  { name: 'inputter_id', pattern: /\binputter_id\b/i },
  { name: '利用者', pattern: /利用者/ },
  { name: '入力者', pattern: /入力者/ },
]

const PITCH_DETAIL_CANDIDATES: readonly ForbiddenCandidate[] = [
  { name: 'velocity', pattern: /\bvelocity\b/i },
  { name: 'pitchVelocity', pattern: /\bpitchVelocity\b/i },
  { name: 'pitch_velocity', pattern: /\bpitch_velocity\b/i },
  { name: '球速', pattern: /球速/ },
  { name: 'course', pattern: /\bcourse\b/i },
  { name: 'pitchCourse', pattern: /\bpitchCourse\b/i },
  { name: 'pitch_course', pattern: /\bpitch_course\b/i },
  { name: 'コース', pattern: /コース/ },
  { name: 'pitchType', pattern: /\bpitchType\b/i },
  { name: 'pitch_type', pattern: /\bpitch_type\b/i },
  { name: '球種', pattern: /球種/ },
]

const DIRECT_STATE_OVERWRITE_EXPORT_CANDIDATES: readonly RegExp[] = [
  /^(?:overwrite|replace|set|update|mutate|apply).*State/i,
  /^(?:overwrite|replace|set|update|mutate|apply)_state/i,
]

const OUT_OF_SCOPE_CANDIDATES = {
  U1: [
    { name: '対象連番', pattern: /対象連番/ },
    { name: '欠落範囲', pattern: /欠落範囲/ },
    { name: 'targetSequence', pattern: /\btargetSequence\b/i },
    { name: 'targetEventSequence', pattern: /\btargetEventSequence\b/i },
    { name: 'missingRange', pattern: /\bmissingRange\b/i },
    { name: 'missingSequenceRange', pattern: /\bmissingSequenceRange\b/i },
    { name: 'gapRange', pattern: /\bgapRange\b/i },
  ],
  U2: [
    { name: '退避イベント', pattern: /退避イベント/ },
    { name: '退避取り込み', pattern: /退避.*取り込み|取り込み.*退避/ },
    { name: '挿入位置', pattern: /挿入位置/ },
    { name: '採番', pattern: /採番/ },
    { name: '凍結', pattern: /凍結/ },
    { name: 'quarantineImport', pattern: /\bquarantineImport\b/i },
    { name: 'insertionPosition', pattern: /\binsertionPosition\b/i },
    { name: 'frozenSequence', pattern: /\bfrozenSequence\b/i },
  ],
  U3: [
    { name: '保持期限', pattern: /保持期限/ },
    { name: 'retentionDeadline', pattern: /\bretentionDeadline\b/i },
    { name: 'retentionPeriod', pattern: /\bretentionPeriod\b/i },
    { name: 'retentionDays', pattern: /\bretentionDays\b/i },
    { name: 'retentionExpiresAt', pattern: /\bretentionExpiresAt\b/i },
    { name: 'expiresAt', pattern: /\bexpiresAt\b/i },
    { name: 'expires_at', pattern: /\bexpires_at\b/i },
  ],
  U4: [
    { name: '正史復元', pattern: /正史復元/ },
    { name: 'canonicalRestore', pattern: /\bcanonicalRestore\b/i },
    { name: 'restoreCanonical', pattern: /\brestoreCanonical\w*\b/i },
    {
      name: 'restoreCanonicalHistory',
      pattern: /\brestoreCanonicalHistory\b/i,
    },
  ],
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

function exportedValueIdentifiers(source: string): readonly string[] {
  return [...source.matchAll(/\bexport\s+(?:const|function|class)\s+([\w$]+)/g)]
    .map((match) => match[1])
    .filter((identifier): identifier is string => identifier !== undefined)
}

function exactStringLiterals(source: string, valuePattern: string): string[] {
  const pattern = new RegExp(`(['"])(${valuePattern})\\1`, 'g')
  return [...source.matchAll(pattern)]
    .map((match) => match[2])
    .filter((value): value is string => value !== undefined)
}

describe('prohibitions', () => {
  it('raw 走査対象が空でなく、spec を含まない', () => {
    expect(PRODUCT_SOURCES.length).toBeGreaterThan(0)
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

  it('P-20: 利用者・入力者を識別する候補語を持たない', () => {
    expect(USER_IDENTITY_CANDIDATES.length).toBeGreaterThan(0)
    expectCandidatesAbsent(USER_IDENTITY_CANDIDATES)
  })

  it('P-28: 状態補正を種別集合の要素とし、状態を直接上書きする export を持たない', () => {
    const stateCorrection = EVENT_KIND_RULES.find(
      (eventKind) => eventKind.name === '状態補正',
    )
    const exportedIdentifiers = PRODUCT_SOURCES.flatMap((entry) =>
      exportedValueIdentifiers(entry.source),
    )

    expect(stateCorrection).toBeDefined()
    expect(buildSyncEventKindSet({ stateCorrectionAdopted: true })).toContain(
      stateCorrection,
    )
    expect(
      buildSyncEventKindSet({ stateCorrectionAdopted: false }),
    ).not.toContain(stateCorrection)
    expect(DIRECT_STATE_OVERWRITE_EXPORT_CANDIDATES.length).toBeGreaterThan(0)
    expect(exportedIdentifiers.length).toBeGreaterThan(0)
    for (const identifier of exportedIdentifiers) {
      for (const candidate of DIRECT_STATE_OVERWRITE_EXPORT_CANDIDATES) {
        expect(identifier).not.toMatch(candidate)
      }
    }
  })

  it('P-32: 投球項目を表す候補語を持たない', () => {
    expect(PITCH_DETAIL_CANDIDATES.length).toBeGreaterThan(0)
    expectCandidatesAbsent(PITCH_DETAIL_CANDIDATES)
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

  it('P-58: 種別 ID を比較・switchする分岐を持たない', () => {
    const eventKindDiscriminant =
      /\b(?:eventKind(?:\.id)?|event\.kind|kindId|eventKindId)\b/
    const eventKindComparison =
      /\b(?:eventKind(?:\.id)?|event\.kind|kindId|eventKindId)\b\s*(?:===|!==)|(?:===|!==)\s*\b(?:eventKind(?:\.id)?|event\.kind|kindId|eventKindId)\b/

    for (const productSource of PRODUCT_SOURCES) {
      const sourceWithoutAllowedMembership =
        productSource.fileName === 'eventKinds.ts'
          ? productSource.source.replace(/eventKind\.id\s*!==\s*'7'/g, '')
          : productSource.source
      expect(sourceWithoutAllowedMembership).not.toMatch(eventKindComparison)

      for (const match of sourceWithoutAllowedMembership.matchAll(
        /\bswitch\s*\(([^)]*)\)/g,
      )) {
        expect(match[1] ?? '').not.toMatch(eventKindDiscriminant)
      }
    }

    expect(
      sourceFor('eventKinds.ts').match(/eventKind\.id\s*!==\s*'7'/g),
    ).toHaveLength(1)
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

  it('種別 ID リテラルを eventKinds.ts の定義と許可済み membership 規則に閉じる', () => {
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
