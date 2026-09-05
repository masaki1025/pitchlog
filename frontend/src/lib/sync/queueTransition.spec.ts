import { describe, expect, it } from 'vitest'
import queueTransitionSource from './queueTransition.ts?raw'
import { readCanonAckStateResults } from './canonOracle'
import { EVENT_KIND_RULES } from './eventKinds'
import {
  QUEUE_ACTION_REQUIRED_LABELS,
  QUEUE_STATES,
  type QueueStateId,
} from './queueState'
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
  type QueueTransitionRule,
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

function canonAckResultAt(index: number) {
  const result = CANON_ACK_RESULTS[index]
  if (!result || CANON_ACK_RESULTS.length !== 5) {
    throw new Error('R-ACK-STATE の結果集合が不正です')
  }
  return result
}

const ACK_ACCEPTED_RESULT = canonAckResultAt(0)
const ACK_DUPLICATE_RESULT = canonAckResultAt(1)
const ACK_REJECTED_RESULT = canonAckResultAt(2)
const ACK_EVACUATED_RESULT = canonAckResultAt(3)
const ACK_UNPROCESSED_RESULT = canonAckResultAt(4)

const BASE_KEY_PARTS = {
  d4: {},
  d1: {},
  d5: {},
} as const
const BASE_CONTENT = {}
const NON_PLAYER_EVENT_KIND = EVENT_KIND_RULES.find(
  (eventKind) => eventKind.name !== '選手のその場登録',
)
if (!NON_PLAYER_EVENT_KIND) {
  throw new Error('選手登録以外のイベント種別がありません')
}

type D1QueueSlot = Extract<QueueSlot, { source: 'd1-event' }>
type P3QueueSlot = Extract<QueueSlot, { source: 'p3-acceptance' }>

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

function p3QueueSlot(state: QueueStateId): P3QueueSlot {
  return {
    state,
    source: 'p3-acceptance',
    acceptance: {},
    acceptedAt: {},
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

type TransitionCase = Readonly<{
  rule: QueueTransitionRule
  run: () => QueueTransitionResult
}>

const TRANSITION_CASES: readonly TransitionCase[] = [
  {
    rule: queueTransitionRuleById('QT-01'),
    run: () =>
      evaluateQueueTransition({
        kind: 'append-persisted',
        key: eventKey(),
        content: BASE_CONTENT,
      }),
  },
  {
    rule: queueTransitionRuleById('QT-02'),
    run: () => {
      const slot = queueSlot(UNSENT_STATE)
      return evaluateQueueTransition(
        { kind: 'apply-a5', slot, eventKind: NON_PLAYER_EVENT_KIND },
        resolveA5(ACK_ACCEPTED_RESULT, slot.key),
      )
    },
  },
  {
    rule: queueTransitionRuleById('QT-03'),
    run: () => {
      const slot = queueSlot(UNSENT_STATE)
      return evaluateQueueTransition(
        { kind: 'apply-a5', slot, eventKind: NON_PLAYER_EVENT_KIND },
        {
          ...resolveA5(ACK_REJECTED_RESULT, slot.key),
          classifyB3: () => ({
            kind: B3_REASON_KIND.CONTENT,
            actionRequiredLabel: REVISION_ACTION_LABEL.id,
          }),
        },
      )
    },
  },
  {
    rule: queueTransitionRuleById('QT-04'),
    run: () => {
      const slot = queueSlot(UNSENT_STATE)
      return evaluateQueueTransition(
        { kind: 'apply-a5', slot, eventKind: NON_PLAYER_EVENT_KIND },
        resolveA5(ACK_UNPROCESSED_RESULT, slot.key),
      )
    },
  },
  {
    rule: queueTransitionRuleById('QT-05'),
    run: () =>
      evaluateQueueTransition({
        kind: 'ack-unavailable',
        slot: queueSlot(UNSENT_STATE),
      }),
  },
  {
    rule: queueTransitionRuleById('QT-06'),
    run: () => {
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
  },
  {
    rule: queueTransitionRuleById('QT-07'),
    run: () => {
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
  },
  {
    rule: queueTransitionRuleById('QT-08'),
    run: () => {
      const slot = queueSlot(UNSENT_STATE)
      return evaluateQueueTransition(
        { kind: 'apply-a5', slot, eventKind: NON_PLAYER_EVENT_KIND },
        resolveA5(ACK_EVACUATED_RESULT, slot.key),
      )
    },
  },
  {
    rule: queueTransitionRuleById('QT-09'),
    run: () =>
      evaluateQueueTransition(
        {
          kind: 'p3-acceptance-persisted',
          acceptance: { key: eventKey(), content: BASE_CONTENT },
          persistenceSucceeded: true,
        },
        { resolveAcceptedAt: () => ({ known: true, value: {} }) },
      ),
  },
  {
    rule: queueTransitionRuleById('QT-10'),
    run: () =>
      evaluateQueueTransition(
        {
          kind: 'i6-evacuation-saved',
          slot: p3QueueSlot(SYNCED_STATE),
        },
        { confirmI6EvacuationSaved: () => true },
      ),
  },
  {
    rule: queueTransitionRuleById('QT-11'),
    run: () =>
      evaluateQueueTransition({
        kind: 'discard',
        slot: queueSlot(UNSENT_STATE),
        confirmed24HoursElapsed: true,
      }),
  },
  {
    rule: queueTransitionRuleById('QT-12'),
    run: () =>
      evaluateQueueTransition({
        kind: 'discard',
        slot: queueSlot(ACTION_REQUIRED_STATE),
        confirmed24HoursElapsed: true,
      }),
  },
  {
    rule: queueTransitionRuleById('QT-13'),
    run: () =>
      evaluateQueueTransition(
        {
          kind: 'discard',
          slot: queueSlot(SYNCED_STATE),
          confirmed24HoursElapsed: true,
        },
        { resolveRg1State: () => RG1_STATE.INACTIVE_CONFIRMED },
      ),
  },
  {
    rule: queueTransitionRuleById('QT-14'),
    run: () =>
      evaluateQueueTransition({
        kind: 'discard',
        slot: queueSlot(EVACUATED_STATE),
        confirmed24HoursElapsed: true,
      }),
  },
]

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
  expect(
    noTransitionRows.every(
      (rule) => rule.target === queueTransitionRuleById('QT-11').target,
    ),
  ).toBe(true)
}

describe('queueTransition', () => {
  it('14 行の ID と表駆動ケースを完全一致させる', () => {
    const tableA5ResultIds = QUEUE_TRANSITION_RULES.flatMap((rule) =>
      'a5ResultIds' in rule.condition ? rule.condition.a5ResultIds : [],
    )

    expect(QUEUE_TRANSITION_RULES).toHaveLength(14)
    expect(QUEUE_TRANSITION_ROW_IDS).toHaveLength(14)
    expect(new Set(QUEUE_TRANSITION_ROW_IDS).size).toBe(14)
    expect(new Set(QUEUE_TRANSITION_ROW_IDS)).toEqual(new Set(EXPECTED_ROW_IDS))
    expect(QUEUE_TRANSITION_ROW_IDS).toEqual(
      QUEUE_TRANSITION_RULES.map((rule) => rule.id),
    )
    expect(TRANSITION_CASES).toHaveLength(14)
    expect(TRANSITION_CASES.map((testCase) => testCase.rule.id)).toEqual(
      QUEUE_TRANSITION_ROW_IDS,
    )
    expect(tableA5ResultIds).toHaveLength(CANON_ACK_RESULTS.length)
    expect(new Set(tableA5ResultIds)).toEqual(
      new Set(CANON_ACK_RESULTS.map((result) => result.id)),
    )
  })

  it('未知の行 ID を fail-closed で拒否する', () => {
    expect(() =>
      queueTransitionRuleById('QT-UNKNOWN' as QueueTransitionRowId),
    ).toThrow('キュー遷移表の行 ID を解決できません')
  })

  it.each(TRANSITION_CASES)('$rule.id の要求を表どおり判定する', (testCase) => {
    const result = testCase.run()

    expect(result.rowId).toBe(testCase.rule.id)
    expect(result.applied).toBe(testCase.rule.transitionAllowed)
    if (result.applied) {
      expect(result.target).toBe(testCase.rule.target)
    }
  })

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
        { kind: 'apply-a5', slot, eventKind: NON_PLAYER_EVENT_KIND },
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
      { kind: 'apply-a5', slot, eventKind: NON_PLAYER_EVENT_KIND },
      resolveA5(ACK_ACCEPTED_RESULT, mismatchedKey),
    )

    expect(result.applied).toBe(false)
  })

  it('変異: D1 の prefix 情報だけで同期済みにする経路を持たない', () => {
    const prefixOnlyRequest = {
      kind: 'apply-a5',
      slot: queueSlot(UNSENT_STATE),
      eventKind: NON_PLAYER_EVENT_KIND,
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
        { kind: 'apply-a5', slot, eventKind: NON_PLAYER_EVENT_KIND },
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
      { kind: 'apply-a5', slot, eventKind: NON_PLAYER_EVENT_KIND },
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
    const result = evaluateQueueTransition(
      {
        kind: 'action-replacement-persisted',
        slot,
        replacement: { key: eventKey({ d5: {} }), content: {} },
      },
      { confirmTombstoneGeneration: () => true },
    )

    expect(result.applied).toBe(true)
    expect(result.rowId).toBe('QT-06')
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
    const result = evaluateQueueTransition(
      {
        kind: 'p3-acceptance-persisted',
        acceptance: { key: eventKey(), content: BASE_CONTENT },
        persistenceSucceeded: false,
      },
      { resolveAcceptedAt: () => ({ known: true, value: {} }) },
    )

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
          eventKind: NON_PLAYER_EVENT_KIND,
        }),
    },
    {
      name: 'B3 理由分類',
      run: () => {
        const slot = queueSlot(UNSENT_STATE)
        return evaluateQueueTransition(
          { kind: 'apply-a5', slot, eventKind: NON_PLAYER_EVENT_KIND },
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
          slot: p3QueueSlot(SYNCED_STATE),
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
      name: 'accepted_at',
      run: () =>
        evaluateQueueTransition({
          kind: 'p3-acceptance-persisted',
          acceptance: { key: eventKey(), content: BASE_CONTENT },
          persistenceSucceeded: true,
        }),
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

  it('明示的に不明な B3 分類と accepted_at を fail-closed にする', () => {
    const slot = queueSlot(UNSENT_STATE)
    const unknownB3 = evaluateQueueTransition(
      { kind: 'apply-a5', slot, eventKind: NON_PLAYER_EVENT_KIND },
      {
        ...resolveA5(ACK_REJECTED_RESULT, slot.key),
        classifyB3: () => ({ kind: B3_REASON_KIND.UNKNOWN }),
      },
    )
    const unknownAcceptedAt = evaluateQueueTransition(
      {
        kind: 'p3-acceptance-persisted',
        acceptance: { key: eventKey(), content: BASE_CONTENT },
        persistenceSucceeded: true,
      },
      { resolveAcceptedAt: () => ({ known: false }) },
    )

    expect(unknownB3.applied).toBe(false)
    expect(unknownAcceptedAt.applied).toBe(false)
  })
})
