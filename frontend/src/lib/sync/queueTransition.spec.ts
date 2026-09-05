import 'fake-indexeddb/auto'

import { afterEach, describe, expect, it, vi } from 'vitest'
import * as ts from 'typescript'
import syncProtocolRelations from '@design-relations/sync-protocol.json'
import queueTransitionSpecSource from './queueTransition.spec.ts?raw'
import queueTransitionSource from './queueTransition.ts?raw'
import {
  CANON_ACK_STATE_RESULT,
  readCanonAckStateResults,
  type CanonAckStateResult,
} from './canonOracle'
import {
  openDurableQueue,
  type DurableQueue,
  type I6EvacuationReceipt,
  type I6PersistenceReceipt,
} from './durableQueue'
import { EVENT_KIND_SLOT_ID } from './eventFieldRules'
import { EVENT_KIND_RULES } from './eventKinds'
import {
  QUEUE_ACTION_REQUIRED_LABELS,
  QUEUE_STATES,
  type I6Acceptance,
  type QueueStateId,
} from './queueState'
import {
  TARGET_EVENT_REFERENCE_ELEMENTS,
  type TargetEventReference,
} from './syncEvent'
import {
  B3_REASON_KIND,
  evaluateQueueTransition,
  QUEUE_TRANSITION_ROW_IDS,
  QUEUE_TRANSITION_RULES,
  queueTransitionRuleById,
  RG1_STATE,
  type QueueEventKey,
  type QueueSlot,
  type QueueTransitionInjections,
  type QueueTransitionResult,
  type QueueTransitionRowId,
} from './queueTransition'

const UNSENT_STATE = QUEUE_STATES[0].id
const ACTION_REQUIRED_STATE = QUEUE_STATES[1].id
const SYNCED_STATE = QUEUE_STATES[2].id
const EVACUATED_STATE = QUEUE_STATES[3].id
const REVISION_ACTION_LABEL = QUEUE_ACTION_REQUIRED_LABELS[0]
const TOMBSTONE_ACTION_LABEL = QUEUE_ACTION_REQUIRED_LABELS[1]
const CONTENT_ACTION_LABELS = [REVISION_ACTION_LABEL, TOMBSTONE_ACTION_LABEL]
const O4_ACTION_LABEL = QUEUE_ACTION_REQUIRED_LABELS[2]

const EXPECTED_ROW_IDS = [
  'QT-01',
  'QT-02',
  'QT-03',
  'QT-04',
  'QT-05',
  'QT-06',
  'QT-07',
  'QT-08',
  'QT-09',
  'QT-10',
  'QT-11',
  'QT-12',
  'QT-13',
  'QT-14',
] as const satisfies readonly QueueTransitionRowId[]

const CANON_ACK_RESULTS = readCanonAckStateResults()

function canonAckResultById(
  results: readonly CanonAckStateResult[],
  id: string,
): CanonAckStateResult {
  const result = results.find((candidate) => candidate.id === id)
  if (
    !result ||
    results.length !== Object.keys(CANON_ACK_STATE_RESULT).length
  ) {
    throw new Error('R-ACK-STATE の結果集合が不正です')
  }
  return result
}

const ACK_ACCEPTED_RESULT = canonAckResultById(
  CANON_ACK_RESULTS,
  CANON_ACK_STATE_RESULT.ACCEPTED,
)
const ACK_DUPLICATE_RESULT = canonAckResultById(
  CANON_ACK_RESULTS,
  CANON_ACK_STATE_RESULT.DUPLICATE,
)
const ACK_REJECTED_RESULT = canonAckResultById(
  CANON_ACK_RESULTS,
  CANON_ACK_STATE_RESULT.REJECTED,
)
const ACK_EVACUATED_RESULT = canonAckResultById(
  CANON_ACK_RESULTS,
  CANON_ACK_STATE_RESULT.EVACUATED,
)
const ACK_UNPROCESSED_RESULT = canonAckResultById(
  CANON_ACK_RESULTS,
  CANON_ACK_STATE_RESULT.UNPROCESSED,
)

const BASE_KEY_PARTS = {
  d4: {},
  d1: {},
  d5: {},
} as const
let databaseSequence = 0
const openedI6Queues: DurableQueue[] = []
const i6DatabaseNames: string[] = []
const NON_PLAYER_EVENT_KIND = EVENT_KIND_RULES.find(
  (eventKind) => eventKind.name !== '選手のその場登録',
)
if (!NON_PLAYER_EVENT_KIND) {
  throw new Error('選手登録以外のイベント種別がありません')
}
const BASE_CONTENT = {
  fields: { [EVENT_KIND_SLOT_ID]: NON_PLAYER_EVENT_KIND.id },
}

type D1QueueSlot = Extract<QueueSlot, { source: 'd1-event' }>

function targetReference(): TargetEventReference {
  return Object.fromEntries(
    TARGET_EVENT_REFERENCE_ELEMENTS.map((element) => [element, {}]),
  ) as TargetEventReference
}

function i6Acceptance(): I6Acceptance {
  return {
    targetReference: targetReference(),
    expectedVersion: {},
    d5: `i6-d5-${databaseSequence}`,
    confirmedContent: {},
  }
}

async function persistenceReceipt(
  acceptance: I6Acceptance,
): Promise<I6PersistenceReceipt> {
  databaseSequence += 1
  const databaseName = `queue-transition-i6-${databaseSequence}`
  i6DatabaseNames.push(databaseName)
  const queue = await openDurableQueue({
    databaseName,
    requestStoragePersistence: async () => false,
  })
  openedI6Queues.push(queue)
  const preparation = queue.prepareI6Acceptance(acceptance, {
    resolveAcceptedAt: () => ({
      known: true,
      targetReference: acceptance.targetReference,
      acceptedAt: {},
    }),
  })
  const receipt = preparation
    ? await queue.persistI6Acceptance(preparation)
    : undefined
  if (!receipt) {
    throw new Error('I6 永続化 receipt がありません')
  }
  return receipt
}

async function evacuationReceipt(
  acceptance: I6Acceptance,
): Promise<I6EvacuationReceipt> {
  await persistenceReceipt(acceptance)
  const queue = openedI6Queues.at(-1)
  if (!queue) {
    throw new Error('I6 の永続キューがありません')
  }
  const receipt = await queue.prepareI6Evacuation(acceptance.d5, {
    confirmI6EvacuationSaved: () => true,
  })
  if (!receipt) {
    throw new Error('I6 の退避保存 receipt がありません')
  }
  return receipt
}

function deleteDatabase(name: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name)
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('テスト DB を削除できません'))
  })
}

afterEach(async () => {
  for (const queue of openedI6Queues.splice(0)) {
    queue.close()
  }
  for (const name of i6DatabaseNames.splice(0)) {
    await deleteDatabase(name)
  }
})

function eventKey(overrides: Partial<QueueEventKey> = {}): QueueEventKey {
  return { ...BASE_KEY_PARTS, ...overrides }
}

function queueSlot(
  state: QueueStateId,
  overrides: Partial<D1QueueSlot> = {},
): D1QueueSlot {
  return {
    state,
    key: eventKey(),
    content: BASE_CONTENT,
    source: 'd1-event',
    ...overrides,
  }
}

function resolveA5(
  result: (typeof CANON_ACK_RESULTS)[number],
  key: QueueEventKey,
): QueueTransitionInjections {
  return {
    resolveA5: () => ({ key, result }),
  }
}

type ExpectedTransitionRow = Readonly<{
  id: QueueTransitionRowId
  source: string
  target: string
  trigger: string
  condition: Readonly<{
    kind: string
    a5ResultIds?: readonly string[]
  }>
  transitionAllowed: boolean
  changesState: boolean
}>

// R-QUEUE-LIFE に 14 行の遷移表はなく、正本 7-2 の本文だけが出所である。
// R-ACK-STATE も結果集合の5語だけを持ち、14行の遷移条件と A5 の語の対応は照合できない。
// 製品定数を参照すると表と evaluator の同時誤りを検出できないため、ここでは H-61 より
// テストの独立性を優先して期待表をリテラルで持ち、逐語一致は人間の逐行確認へ送る。
const EXPECTED_TRANSITION_ROWS = [
  {
    id: 'QT-01',
    source: '（なし）',
    target: '未送信',
    trigger: 'append-persisted',
    condition: { kind: 'persistence-completed' },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: 'QT-02',
    source: '未送信',
    target: '同期済み',
    trigger: 'apply-a5',
    condition: {
      kind: 'a5-result',
      a5ResultIds: ['受理', '重複'],
    },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: 'QT-03',
    source: '未送信',
    target: '要操作',
    trigger: 'apply-a5',
    condition: {
      kind: 'a5-rejection-with-b3-classification',
      a5ResultIds: ['拒否'],
    },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: 'QT-04',
    source: '未送信',
    target: '未送信',
    trigger: 'apply-a5',
    condition: {
      kind: 'a5-result',
      a5ResultIds: ['未処理'],
    },
    transitionAllowed: true,
    changesState: false,
  },
  {
    id: 'QT-05',
    source: '未送信',
    target: '未送信',
    trigger: 'ack-unavailable',
    condition: { kind: 'ack-not-returned' },
    transitionAllowed: true,
    changesState: false,
  },
  {
    id: 'QT-06',
    source: '要操作',
    target: '未送信',
    trigger: 'action-replacement-persisted',
    condition: { kind: 'same-slot-replacement-completed' },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: 'QT-07',
    source: '要操作',
    target: '未送信',
    trigger: 'o4-retry-persisted',
    condition: {
      kind: 'o4-corrected-and-same-slot-replacement-completed',
    },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: 'QT-08',
    source: '未送信',
    target: '退避済み',
    trigger: 'apply-a5',
    condition: {
      kind: 'a5-result',
      a5ResultIds: ['退避'],
    },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: 'QT-09',
    source: 'P3変更受理結果',
    target: '同期済み',
    trigger: 'p3-acceptance-persisted',
    condition: {
      kind: 'accepted-at-resolved-and-device-persistence-completed',
    },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: 'QT-10',
    source: '同期済み',
    target: '退避済み',
    trigger: 'i6-evacuation-saved',
    condition: { kind: 'i6-evacuation-save-completed' },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: 'QT-11',
    source: '未送信',
    target: '破棄',
    trigger: 'discard',
    condition: { kind: 'no-transition' },
    transitionAllowed: false,
    changesState: false,
  },
  {
    id: 'QT-12',
    source: '要操作',
    target: '破棄',
    trigger: 'discard',
    condition: { kind: 'no-transition' },
    transitionAllowed: false,
    changesState: false,
  },
  {
    id: 'QT-13',
    source: '同期済み',
    target: '破棄',
    trigger: 'discard',
    condition: { kind: 'retention-elapsed-and-rg1-inactive-confirmed' },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: 'QT-14',
    source: '退避済み',
    target: '破棄',
    trigger: 'discard',
    condition: { kind: 'no-transition' },
    transitionAllowed: false,
    changesState: false,
  },
] as const satisfies readonly ExpectedTransitionRow[]

type TransitionRunner = () =>
  QueueTransitionResult | Promise<QueueTransitionResult>

const TRANSITION_RUNNERS = {
  'QT-01': () =>
    evaluateQueueTransition({
      kind: 'append-persisted',
      key: eventKey(),
      content: BASE_CONTENT,
    }),
  'QT-02': () => {
    const slot = queueSlot(UNSENT_STATE)
    return evaluateQueueTransition(
      { kind: 'apply-a5', slot },
      resolveA5(ACK_ACCEPTED_RESULT, slot.key),
    )
  },
  'QT-03': () => {
    const slot = queueSlot(UNSENT_STATE)
    return evaluateQueueTransition(
      { kind: 'apply-a5', slot },
      {
        ...resolveA5(ACK_REJECTED_RESULT, slot.key),
        classifyB3: () => ({
          kind: B3_REASON_KIND.CONTENT,
          actionRequiredLabel: REVISION_ACTION_LABEL.id,
        }),
      },
    )
  },
  'QT-04': () => {
    const slot = queueSlot(UNSENT_STATE)
    return evaluateQueueTransition(
      { kind: 'apply-a5', slot },
      resolveA5(ACK_UNPROCESSED_RESULT, slot.key),
    )
  },
  'QT-05': () =>
    evaluateQueueTransition({
      kind: 'ack-unavailable',
      slot: queueSlot(UNSENT_STATE),
    }),
  'QT-06': () => {
    const slot = queueSlot(ACTION_REQUIRED_STATE, {
      actionRequiredLabel: REVISION_ACTION_LABEL.id,
    })
    return evaluateQueueTransition({
      kind: 'action-replacement-persisted',
      slot,
      replacement: {
        key: eventKey({ d5: {} }),
        content: {},
      },
    })
  },
  'QT-07': () => {
    const slot = queueSlot(ACTION_REQUIRED_STATE, {
      actionRequiredLabel: O4_ACTION_LABEL.id,
    })
    return evaluateQueueTransition(
      {
        kind: 'o4-retry-persisted',
        slot,
        replacement: {
          key: eventKey({ d5: {} }),
          content: slot.content,
        },
      },
      { confirmO4Correction: () => true },
    )
  },
  'QT-08': () => {
    const slot = queueSlot(UNSENT_STATE)
    return evaluateQueueTransition(
      { kind: 'apply-a5', slot },
      resolveA5(ACK_EVACUATED_RESULT, slot.key),
    )
  },
  'QT-09': async () => {
    const acceptance = i6Acceptance()
    return evaluateQueueTransition({
      kind: 'p3-acceptance-persisted',
      persistenceReceipt: await persistenceReceipt(acceptance),
    })
  },
  'QT-10': async () => {
    const acceptance = i6Acceptance()
    return evaluateQueueTransition({
      kind: 'i6-evacuation-saved',
      evacuationReceipt: await evacuationReceipt(acceptance),
    })
  },
  'QT-11': () =>
    evaluateQueueTransition({
      kind: 'discard',
      slot: queueSlot(UNSENT_STATE),
      confirmed24HoursElapsed: true,
    }),
  'QT-12': () =>
    evaluateQueueTransition({
      kind: 'discard',
      slot: queueSlot(ACTION_REQUIRED_STATE),
      confirmed24HoursElapsed: true,
    }),
  'QT-13': () =>
    evaluateQueueTransition(
      {
        kind: 'discard',
        slot: queueSlot(SYNCED_STATE),
        confirmed24HoursElapsed: true,
      },
      { resolveRg1State: () => RG1_STATE.INACTIVE_CONFIRMED },
    ),
  'QT-14': () =>
    evaluateQueueTransition({
      kind: 'discard',
      slot: queueSlot(EVACUATED_STATE),
      confirmed24HoursElapsed: true,
    }),
} satisfies Readonly<Record<QueueTransitionRowId, TransitionRunner>>

type MutableTransitionRule = {
  id: QueueTransitionRowId
  source: string
  target: string
  trigger: string
  condition: {
    kind: string
    a5ResultIds?: string[]
  }
  transitionAllowed: boolean
  changesState: boolean
}

function mutableTransitionRuleById(
  rules: MutableTransitionRule[],
  id: QueueTransitionRowId,
): MutableTransitionRule {
  const rule = rules.find((candidate) => candidate.id === id)
  if (!rule) {
    throw new Error(`変異対象のキュー遷移行がありません: ${id}`)
  }
  return rule
}

function expectTransitionTableMatchesExpected(
  rules: readonly ExpectedTransitionRow[],
): void {
  expect(rules).toEqual(EXPECTED_TRANSITION_ROWS)
}

function extractExpectedTransitionTable(source: string): string {
  const start = source.indexOf('const EXPECTED_TRANSITION_ROWS =')
  const end = source.indexOf('type TransitionRunner =', start)
  if (start < 0 || end < 0) {
    throw new Error('独立期待表のソース範囲を取得できません')
  }
  return source.slice(start, end)
}

function importedProductIdentifiers(source: string): ReadonlySet<string> {
  const sourceFile = ts.createSourceFile(
    'queueTransition.spec.ts',
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  )
  const identifiers = new Set<string>()

  for (const statement of sourceFile.statements) {
    if (
      !ts.isImportDeclaration(statement) ||
      !ts.isStringLiteral(statement.moduleSpecifier) ||
      !statement.moduleSpecifier.text.startsWith('./') ||
      statement.moduleSpecifier.text.includes('.spec.')
    ) {
      continue
    }
    const importClause = statement.importClause
    if (!importClause) {
      continue
    }
    if (importClause.name) {
      identifiers.add(importClause.name.text)
    }
    const bindings = importClause.namedBindings
    if (bindings && ts.isNamespaceImport(bindings)) {
      identifiers.add(bindings.name.text)
    } else if (bindings) {
      for (const element of bindings.elements) {
        identifiers.add(element.name.text)
      }
    }
  }
  return identifiers
}

function identifiersInSource(source: string): ReadonlySet<string> {
  const sourceFile = ts.createSourceFile(
    'expectedTransitionTable.ts',
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  )
  const identifiers = new Set<string>()
  const visit = (node: ts.Node): void => {
    if (ts.isIdentifier(node)) {
      identifiers.add(node.text)
    }
    ts.forEachChild(node, visit)
  }
  visit(sourceFile)
  return identifiers
}

type ComparableTransitionRule = Readonly<{
  source: string
  target: string
  transitionAllowed: boolean
}>

function expectNoTransitionRows(
  rules: readonly ComparableTransitionRule[],
): void {
  const noTransitionRows = rules.filter((rule) => !rule.transitionAllowed)

  expect(noTransitionRows).toHaveLength(3)
  expect(new Set(noTransitionRows.map((rule) => rule.source))).toEqual(
    new Set([UNSENT_STATE, ACTION_REQUIRED_STATE, EVACUATED_STATE]),
  )
  expect(noTransitionRows.every((rule) => rule.target === '破棄')).toBe(true)
}

describe('queueTransition', () => {
  it('正本 7-2 から書き起こした独立期待表と製品表を完全一致させる', () => {
    const tableA5ResultIds = QUEUE_TRANSITION_RULES.flatMap((rule) =>
      'a5ResultIds' in rule.condition ? rule.condition.a5ResultIds : [],
    )

    expectTransitionTableMatchesExpected(QUEUE_TRANSITION_RULES)
    expect(QUEUE_TRANSITION_RULES).toHaveLength(14)
    expect(QUEUE_TRANSITION_ROW_IDS).toHaveLength(14)
    expect(new Set(QUEUE_TRANSITION_ROW_IDS).size).toBe(14)
    expect(new Set(QUEUE_TRANSITION_ROW_IDS)).toEqual(new Set(EXPECTED_ROW_IDS))
    expect(QUEUE_TRANSITION_ROW_IDS).toEqual(
      QUEUE_TRANSITION_RULES.map((rule) => rule.id),
    )
    expect(Object.keys(TRANSITION_RUNNERS)).toEqual(EXPECTED_ROW_IDS)
    expect(tableA5ResultIds).toHaveLength(CANON_ACK_RESULTS.length)
    expect(new Set(tableA5ResultIds)).toEqual(
      new Set(CANON_ACK_RESULTS.map((result) => result.id)),
    )
  })

  it('独立期待表が製品 module の識別子を参照しない', () => {
    const expectedTableSource = extractExpectedTransitionTable(
      queueTransitionSpecSource,
    )
    const productIdentifiers = importedProductIdentifiers(
      queueTransitionSpecSource,
    )
    const referencedProductIdentifiers = [
      ...identifiersInSource(expectedTableSource),
    ].filter((identifier) => productIdentifiers.has(identifier))

    expect(productIdentifiers.size).toBeGreaterThan(0)
    expect(referencedProductIdentifiers).toEqual([])
  })

  it('R-ACK-STATE の要素順を入れ替えても A5 の語と遷移先を変えない', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    mutatedRelations['R-ACK-STATE'].source_elements.reverse()
    const reorderedResults = readCanonAckStateResults(mutatedRelations)
    const expectedTargets = [
      [CANON_ACK_STATE_RESULT.ACCEPTED, SYNCED_STATE],
      [CANON_ACK_STATE_RESULT.DUPLICATE, SYNCED_STATE],
      [CANON_ACK_STATE_RESULT.REJECTED, ACTION_REQUIRED_STATE],
      [CANON_ACK_STATE_RESULT.EVACUATED, EVACUATED_STATE],
      [CANON_ACK_STATE_RESULT.UNPROCESSED, UNSENT_STATE],
    ] as const

    for (const [ackId, expectedTarget] of expectedTargets) {
      const slot = queueSlot(UNSENT_STATE)
      const result = evaluateQueueTransition(
        { kind: 'apply-a5', slot },
        {
          ...resolveA5(canonAckResultById(reorderedResults, ackId), slot.key),
          classifyB3: () => ({
            kind: B3_REASON_KIND.CONTENT,
            actionRequiredLabel: REVISION_ACTION_LABEL.id,
          }),
        },
      )

      expect(result.applied).toBe(true)
      if (result.applied) {
        expect(result.target).toBe(expectedTarget)
      }
    }
    expect(queueTransitionSource).not.toContain('canonAckResultAt')
    expect(queueTransitionSource).not.toMatch(/CANON_ACK_RESULTS\s*\[/)
  })

  it('未知の行 ID を fail-closed で拒否する', () => {
    expect(() =>
      queueTransitionRuleById('QT-UNKNOWN' as QueueTransitionRowId),
    ).toThrow('キュー遷移表の行 ID を解決できません')
  })

  it.each(EXPECTED_TRANSITION_ROWS)(
    '$id の要求を独立期待値どおり判定する',
    async (expectedRow) => {
      const result = await TRANSITION_RUNNERS[expectedRow.id]()

      expect(result.rowId).toBe(expectedRow.id)
      expect(result.applied).toBe(expectedRow.transitionAllowed)
      if (result.applied) {
        expect(result.target).toBe(expectedRow.target)
        if (result.slot) {
          expect(result.slot.state).toBe(
            expectedRow.changesState ? expectedRow.target : expectedRow.source,
          )
        }
      }
    },
  )

  const transitionTableMutations = [
    {
      name: '遷移先変更',
      mutate: (rules: MutableTransitionRule[]) => {
        mutableTransitionRuleById(rules, 'QT-02').target = '要操作'
      },
    },
    {
      name: '遷移なし行を遷移させる条件緩和',
      mutate: (rules: MutableTransitionRule[]) => {
        const rule = mutableTransitionRuleById(rules, 'QT-11')
        rule.transitionAllowed = true
        rule.changesState = true
      },
    },
    {
      name: '遷移行を遷移させない条件厳格化',
      mutate: (rules: MutableTransitionRule[]) => {
        const rule = mutableTransitionRuleById(rules, 'QT-09')
        rule.transitionAllowed = false
        rule.changesState = false
      },
    },
    {
      name: 'A5 の受理と拒否の入れ替え',
      mutate: (rules: MutableTransitionRule[]) => {
        mutableTransitionRuleById(rules, 'QT-02').condition.a5ResultIds = [
          CANON_ACK_STATE_RESULT.REJECTED,
          CANON_ACK_STATE_RESULT.DUPLICATE,
        ]
        mutableTransitionRuleById(rules, 'QT-03').condition.a5ResultIds = [
          CANON_ACK_STATE_RESULT.ACCEPTED,
        ]
      },
    },
  ] as const

  it.each(transitionTableMutations)(
    '変異: $nameを独立期待表で検出する',
    ({ mutate }) => {
      const mutatedRules = structuredClone(
        QUEUE_TRANSITION_RULES,
      ) as unknown as MutableTransitionRule[]
      mutate(mutatedRules)

      expect(() => expectTransitionTableMatchesExpected(mutatedRules)).toThrow()
    },
  )

  it('遷移なし3行の破棄要求を拒否する', () => {
    expectNoTransitionRows(QUEUE_TRANSITION_RULES)
  })

  it('変異: 遷移なし3行で破棄を許す変更を検出する', () => {
    const mutatedRules = QUEUE_TRANSITION_RULES.map((rule) =>
      rule.transitionAllowed ? rule : { ...rule, transitionAllowed: true },
    )

    expect(() => expectNoTransitionRows(mutatedRules)).toThrow()
  })

  it.each([ACK_ACCEPTED_RESULT, ACK_DUPLICATE_RESULT])(
    'A5 の $id は完全一致したイベントキーだけを同期済みにする',
    (ackResult) => {
      const slot = queueSlot(UNSENT_STATE)
      const result = evaluateQueueTransition(
        { kind: 'apply-a5', slot },
        resolveA5(ackResult, slot.key),
      )

      expect(result.applied).toBe(true)
      if (result.applied) {
        expect(result.slot?.state).toBe(SYNCED_STATE)
      }
    },
  )

  it('同じ D4・D1 でも D5 が異なる A5 結果では遷移しない', () => {
    const slot = queueSlot(UNSENT_STATE)
    const mismatchedKey = eventKey({ d5: {} })
    const result = evaluateQueueTransition(
      { kind: 'apply-a5', slot },
      resolveA5(ACK_ACCEPTED_RESULT, mismatchedKey),
    )

    expect(result.applied).toBe(false)
  })

  it('変異: D1 の prefix 情報だけで同期済みにする経路を持たない', () => {
    const prefixOnlyRequest = {
      kind: 'apply-a5',
      slot: queueSlot(UNSENT_STATE),
      d3: {},
    } as const

    expect(evaluateQueueTransition(prefixOnlyRequest)).toEqual({
      applied: false,
    })
    expect(queueTransitionSource).not.toContain('D3')
  })

  it.each(CONTENT_ACTION_LABELS)(
    '内容起因の B3 を $id に分類する',
    (actionRequiredLabel) => {
      const slot = queueSlot(UNSENT_STATE)
      const result = evaluateQueueTransition(
        { kind: 'apply-a5', slot },
        {
          ...resolveA5(ACK_REJECTED_RESULT, slot.key),
          classifyB3: () => ({
            kind: B3_REASON_KIND.CONTENT,
            actionRequiredLabel: actionRequiredLabel.id,
          }),
        },
      )

      expect(result.applied).toBe(true)
      if (result.applied) {
        expect(result.slot?.state).toBe(ACTION_REQUIRED_STATE)
        expect(result.slot?.source).toBe('d1-event')
        if (result.slot?.source === 'd1-event') {
          expect(result.slot.actionRequiredLabel).toBe(actionRequiredLabel.id)
        }
      }
    },
  )

  it('O4 の B3 を管理者対応用ラベルに分類する', () => {
    const slot = queueSlot(UNSENT_STATE)
    const result = evaluateQueueTransition(
      { kind: 'apply-a5', slot },
      {
        ...resolveA5(ACK_REJECTED_RESULT, slot.key),
        classifyB3: () => ({ kind: B3_REASON_KIND.O4 }),
      },
    )

    expect(result.applied).toBe(true)
    if (result.applied) {
      expect(result.slot?.source).toBe('d1-event')
      if (result.slot?.source === 'd1-event') {
        expect(result.slot.actionRequiredLabel).toBe(O4_ACTION_LABEL.id)
      }
    }
  })

  const blockedTombstoneInjections = [
    ['未注入', {}],
    ['undefined', { confirmTombstoneGeneration: () => undefined }],
    ['false', { confirmTombstoneGeneration: () => false }],
    [
      '例外',
      {
        confirmTombstoneGeneration: () => {
          throw new Error('確認失敗')
        },
      },
    ],
  ] as const satisfies readonly (readonly [string, QueueTransitionInjections])[]

  it.each(blockedTombstoneInjections)(
    '墓標待ちは墓標生成確認が%sなら要操作のまま保持する',
    (_name, injections) => {
      const slot = queueSlot(ACTION_REQUIRED_STATE, {
        actionRequiredLabel: TOMBSTONE_ACTION_LABEL.id,
      })
      const result = evaluateQueueTransition(
        {
          kind: 'action-replacement-persisted',
          slot,
          replacement: { key: eventKey({ d5: {} }), content: {} },
        },
        injections,
      )

      expect(result.applied).toBe(false)
      expect(result.rowId).toBe('QT-06')
    },
  )

  it('墓標待ちは墓標生成確認が true の場合だけ未送信へ戻す', () => {
    const slot = queueSlot(ACTION_REQUIRED_STATE, {
      actionRequiredLabel: TOMBSTONE_ACTION_LABEL.id,
    })
    const replacement = { key: eventKey({ d5: {} }), content: {} }
    const confirmTombstoneGeneration = vi.fn(() => true)
    const result = evaluateQueueTransition(
      {
        kind: 'action-replacement-persisted',
        slot,
        replacement,
      },
      { confirmTombstoneGeneration },
    )

    expect(result.applied).toBe(true)
    expect(result.rowId).toBe('QT-06')
    expect(confirmTombstoneGeneration).toHaveBeenCalledWith({
      slot,
      replacement,
    })
  })

  it('墓標待ちは置換内容が空でなければ確認結果が true でも保持する', () => {
    const slot = queueSlot(ACTION_REQUIRED_STATE, {
      actionRequiredLabel: TOMBSTONE_ACTION_LABEL.id,
    })
    const confirmTombstoneGeneration = vi.fn(() => true)
    const result = evaluateQueueTransition(
      {
        kind: 'action-replacement-persisted',
        slot,
        replacement: {
          key: eventKey({ d5: {} }),
          content: { unexpected: true },
        },
      },
      { confirmTombstoneGeneration },
    )

    expect(result.applied).toBe(false)
    expect(result.rowId).toBe('QT-06')
    expect(confirmTombstoneGeneration).not.toHaveBeenCalled()
  })

  it('改訂待ちは墓標生成確認を注入せず未送信へ戻す', () => {
    const slot = queueSlot(ACTION_REQUIRED_STATE, {
      actionRequiredLabel: REVISION_ACTION_LABEL.id,
    })
    const result = evaluateQueueTransition({
      kind: 'action-replacement-persisted',
      slot,
      replacement: { key: eventKey({ d5: {} }), content: {} },
    })

    expect(result.applied).toBe(true)
    expect(result.rowId).toBe('QT-06')
  })

  it('O4 是正後も内容と D1 を保ち、新しい D5 で未送信へ戻す', () => {
    const slot = queueSlot(ACTION_REQUIRED_STATE, {
      actionRequiredLabel: O4_ACTION_LABEL.id,
    })
    const newD5 = {}
    const result = evaluateQueueTransition(
      {
        kind: 'o4-retry-persisted',
        slot,
        replacement: {
          key: eventKey({ d5: newD5 }),
          content: slot.content,
        },
      },
      { confirmO4Correction: () => true },
    )

    expect(result.applied).toBe(true)
    if (result.applied) {
      expect(result.slot?.state).toBe(UNSENT_STATE)
      expect(result.slot?.source).toBe('d1-event')
      if (result.slot?.source === 'd1-event') {
        expect(result.slot.content).toBe(slot.content)
        expect(result.slot.key.d1).toBe(slot.key.d1)
        expect(result.slot.key.d5).toBe(newD5)
      }
    }
  })

  it('O4 是正後の内容変更を拒否する', () => {
    const slot = queueSlot(ACTION_REQUIRED_STATE, {
      actionRequiredLabel: O4_ACTION_LABEL.id,
    })

    expect(
      evaluateQueueTransition(
        {
          kind: 'o4-retry-persisted',
          slot,
          replacement: { key: eventKey({ d5: {} }), content: {} },
        },
        { confirmO4Correction: () => true },
      ).applied,
    ).toBe(false)
  })

  it('P3 受理結果の端末永続化失敗では同期済みにしない', () => {
    const result = evaluateQueueTransition({
      kind: 'p3-acceptance-persisted',
    })

    expect(result.applied).toBe(false)
  })

  const blockedRg1Cases = [
    ['RG1 中', { resolveRg1State: () => RG1_STATE.ACTIVE }],
    ['確認不能', { resolveRg1State: () => RG1_STATE.UNKNOWN }],
    ['未注入', {}],
  ] as const satisfies readonly (readonly [string, QueueTransitionInjections])[]

  it.each(blockedRg1Cases)(
    '%s では同期済みを破棄しない',
    (_name, injections) => {
      const result = evaluateQueueTransition(
        {
          kind: 'discard',
          slot: queueSlot(SYNCED_STATE),
          confirmed24HoursElapsed: true,
        },
        injections,
      )

      expect(result.applied).toBe(false)
    },
  )

  it('24 時間未経過では RG1 中でないと確認済みでも破棄しない', () => {
    const result = evaluateQueueTransition(
      {
        kind: 'discard',
        slot: queueSlot(SYNCED_STATE),
        confirmed24HoursElapsed: false,
      },
      { resolveRg1State: () => RG1_STATE.INACTIVE_CONFIRMED },
    )

    expect(result.applied).toBe(false)
  })

  const missingInjectionCases = [
    {
      name: 'A5 結果',
      run: () =>
        evaluateQueueTransition({
          kind: 'apply-a5',
          slot: queueSlot(UNSENT_STATE),
        }),
    },
    {
      name: 'B3 理由分類',
      run: () => {
        const slot = queueSlot(UNSENT_STATE)
        return evaluateQueueTransition(
          { kind: 'apply-a5', slot },
          resolveA5(ACK_REJECTED_RESULT, slot.key),
        )
      },
    },
    {
      name: 'O4 是正済み確認',
      run: () => {
        const slot = queueSlot(ACTION_REQUIRED_STATE, {
          actionRequiredLabel: O4_ACTION_LABEL.id,
        })
        return evaluateQueueTransition({
          kind: 'o4-retry-persisted',
          slot,
          replacement: {
            key: eventKey({ d5: {} }),
            content: slot.content,
          },
        })
      },
    },
    {
      name: '墓標生成の成立確認',
      run: () => {
        const slot = queueSlot(ACTION_REQUIRED_STATE, {
          actionRequiredLabel: TOMBSTONE_ACTION_LABEL.id,
        })
        return evaluateQueueTransition({
          kind: 'action-replacement-persisted',
          slot,
          replacement: { key: eventKey({ d5: {} }), content: {} },
        })
      },
    },
    {
      name: 'I6 退避保存完了',
      run: () =>
        evaluateQueueTransition({
          kind: 'i6-evacuation-saved',
        }),
    },
    {
      name: 'RG1 状態',
      run: () =>
        evaluateQueueTransition({
          kind: 'discard',
          slot: queueSlot(SYNCED_STATE),
          confirmed24HoursElapsed: true,
        }),
    },
    {
      name: 'I6 永続化 receipt',
      run: () => {
        return evaluateQueueTransition({
          kind: 'p3-acceptance-persisted',
        })
      },
    },
  ] as const

  it('注入境界を7点とも fail-closed の負例で固定する', () => {
    expect(missingInjectionCases).toHaveLength(7)
  })

  it.each(missingInjectionCases)(
    '変異: $name の注入を無視せず fail-closed にする',
    (testCase) => {
      expect(testCase.run().applied).toBe(false)
    },
  )

  it('明示的に不明な B3 分類を fail-closed にする', () => {
    const slot = queueSlot(UNSENT_STATE)
    const unknownB3 = evaluateQueueTransition(
      { kind: 'apply-a5', slot },
      {
        ...resolveA5(ACK_REJECTED_RESULT, slot.key),
        classifyB3: () => ({ kind: B3_REASON_KIND.UNKNOWN }),
      },
    )
    expect(unknownB3.applied).toBe(false)
  })
})
