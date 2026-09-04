import { describe, expect, it } from 'vitest'
import {
  SYNC_EVENT_PATH,
  type EventSlotId,
  type SyncEventPath,
} from './eventFieldRules'
import {
  EVENT_KIND_GROUP,
  EVENT_KIND_RULES,
  EVENT_PARTICIPATION,
  type EventKindId,
} from './eventKinds'
import {
  buildSidecarJoinKey,
  type SyncEvent,
  type TargetEventReference,
} from './syncEvent'
import {
  checkSyncEvent,
  SYNC_EVENT_VIOLATION,
  SyncEventValidationError,
  validateSyncEvent,
  type SourceEventContextResolver,
  type SyncEventValidationContext,
  type SyncEventViolationType,
} from './validateSyncEvent'

type EventFields = SyncEvent['fields']

function d1Fields(kind: EventKindId): EventFields {
  return {
    V1: `d5-${kind}`,
    V2: `d1-${kind}`,
    V3: `d4-${kind}`,
    V4: `game-${kind}`,
    V5: kind,
    V7: {},
  }
}

function targetReference(kind: EventKindId): TargetEventReference {
  return {
    試合: `target-game-${kind}`,
    '対象の D4': `target-d4-${kind}`,
    '対象の D1': `target-d1-${kind}`,
  }
}

function p3Fields(kind: EventKindId): EventFields {
  return {
    V1: `d5-${kind}`,
    V4: `game-${kind}`,
    V5: kind,
    V7: {},
    V10: targetReference(kind),
    V11: `expected-version-${kind}`,
  }
}

const VALID_FIELDS_BY_KIND: Record<EventKindId, EventFields> = {
  '1': { ...d1Fields('1'), V6: 'position-1', V8: {} },
  '2': { ...d1Fields('2'), V10: targetReference('2') },
  '3': { ...d1Fields('3'), V6: 'position-3' },
  '4': { ...d1Fields('4'), V6: 'position-4' },
  '5': { ...d1Fields('5'), V6: 'position-5' },
  '6': d1Fields('6'),
  '7': { ...d1Fields('7'), V6: 'position-7', V8: {} },
  '8': {
    ...d1Fields('8'),
    V9: {},
    V10: targetReference('8'),
  },
  '9': {
    ...d1Fields('9'),
    V6: 'source-position-9',
    V8: {},
    V9: {},
    V10: targetReference('9'),
  },
  '10': p3Fields('10'),
  '11': p3Fields('11'),
  '12': p3Fields('12'),
}

const logicalCancellableSource: SourceEventContextResolver = () => ({
  participation: EVENT_PARTICIPATION.LOGICAL_POSITION,
  cancellable: true,
})

const syncOrderSource: SourceEventContextResolver = () => ({
  participation: EVENT_PARTICIPATION.SYNC_ORDER_ONLY,
  cancellable: false,
})

function eventFor(kind: EventKindId): SyncEvent {
  return { kind, fields: structuredClone(VALID_FIELDS_BY_KIND[kind]) }
}

function pathFor(kind: EventKindId): SyncEventPath {
  const eventKind = EVENT_KIND_RULES.find((candidate) => candidate.id === kind)
  if (!eventKind) {
    throw new Error(`イベント種別がありません: ${kind}`)
  }
  return eventKind.group === EVENT_KIND_GROUP.B
    ? SYNC_EVENT_PATH.P3
    : SYNC_EVENT_PATH.P1
}

function contextFor(
  kind: EventKindId,
  overrides: Partial<SyncEventValidationContext> = {},
): SyncEventValidationContext {
  return {
    path: pathFor(kind),
    sourceEventContextResolver: logicalCancellableSource,
    ...overrides,
  }
}

function expectRejected(
  event: SyncEvent,
  context: SyncEventValidationContext,
  violation: SyncEventViolationType,
  target: string,
): void {
  const result = checkSyncEvent(event, context)
  expect(result.ok).toBe(false)
  if (result.ok) {
    throw new Error('拒否理由が返されませんでした')
  }
  expect(result.reason).toEqual({ violation, target })
  expect(result.reason.violation.length).toBeGreaterThan(0)
  expect(result.reason.target.length).toBeGreaterThan(0)

  try {
    validateSyncEvent(event, context)
    throw new Error('検査例外が送出されませんでした')
  } catch (error) {
    expect(error).toBeInstanceOf(SyncEventValidationError)
    expect((error as SyncEventValidationError).reason).toEqual(result.reason)
  }
}

describe('validateSyncEvent', () => {
  it.each(EVENT_KIND_RULES)(
    '正例: 種別 $id の必須値を受理する',
    (eventKind) => {
      const event = eventFor(eventKind.id)

      expect(checkSyncEvent(event, contextFor(eventKind.id))).toEqual({
        ok: true,
      })
      expect(() =>
        validateSyncEvent(event, contextFor(eventKind.id)),
      ).not.toThrow()
    },
  )

  it.each([SYNC_EVENT_PATH.P1, SYNC_EVENT_PATH.P2, SYNC_EVENT_PATH.P4])(
    '正例: 群 A を D1 付き経路 %s で受理する',
    (path) => {
      expect(() =>
        validateSyncEvent(eventFor('3'), contextFor('3', { path })),
      ).not.toThrow()
    },
  )

  it('対象参照とサイドカー結合キーを3要素で構成する', () => {
    const reference = targetReference('2')

    expect(
      buildSidecarJoinKey(
        reference.試合,
        reference['対象の D4'],
        reference['対象の D1'],
      ),
    ).toEqual([reference.試合, reference['対象の D4'], reference['対象の D1']])
    expect(buildSidecarJoinKey('game', 'd4', 'd1')).toHaveLength(3)
  })

  it('N-1: V1 欠落を拒否する', () => {
    const event = eventFor('1')
    delete event.fields.V1

    expectRejected(
      event,
      contextFor('1'),
      SYNC_EVENT_VIOLATION.MISSING_SLOT,
      'V1',
    )
  })

  it('N-2: 群 A の V2 欠落を拒否する', () => {
    const event = eventFor('3')
    delete event.fields.V2

    expectRejected(
      event,
      contextFor('3'),
      SYNC_EVENT_VIOLATION.MISSING_SLOT,
      'V2',
    )
  })

  it('N-3: P3 の V2 を拒否する', () => {
    const event = eventFor('10')
    event.fields.V2 = 'unexpected-d1'

    expectRejected(
      event,
      contextFor('10'),
      SYNC_EVENT_VIOLATION.FORBIDDEN_SLOT,
      'V2',
    )
  })

  it('N-4: P3 の V3 を拒否する', () => {
    const event = eventFor('10')
    event.fields.V3 = 'unexpected-d4'

    expectRejected(
      event,
      contextFor('10'),
      SYNC_EVENT_VIOLATION.FORBIDDEN_SLOT,
      'V3',
    )
  })

  it.each(['6', '8'] as const)(
    'N-5: 同期順のみ種別 %s の V6 を拒否する',
    (kind) => {
      const event = eventFor(kind)
      event.fields.V6 = 'unexpected-position'

      expectRejected(
        event,
        contextFor(kind),
        SYNC_EVENT_VIOLATION.FORBIDDEN_SLOT,
        'V6',
      )
    },
  )

  it('N-6: 論理位置を持つ種別の V6 欠落を拒否する', () => {
    const event = eventFor('1')
    delete event.fields.V6

    expectRejected(
      event,
      contextFor('1'),
      SYNC_EVENT_VIOLATION.MISSING_SLOT,
      'V6',
    )
  })

  it('N-7: 改訂元が論理位置を持つ場合の V6 欠落を拒否する', () => {
    const event = eventFor('9')
    delete event.fields.V6

    expectRejected(
      event,
      contextFor('9'),
      SYNC_EVENT_VIOLATION.MISSING_SLOT,
      'V6',
    )
  })

  it('N-7: 改訂元が同期順のみの場合の V6 を拒否する', () => {
    const event = eventFor('9')
    delete event.fields.V8

    expectRejected(
      event,
      contextFor('9', { sourceEventContextResolver: syncOrderSource }),
      SYNC_EVENT_VIOLATION.FORBIDDEN_SLOT,
      'V6',
    )
  })

  it('N-7: 改訂版の resolver 未注入を fail-closed で拒否する', () => {
    const event = eventFor('9')
    const context: SyncEventValidationContext = { path: SYNC_EVENT_PATH.P1 }

    expectRejected(
      event,
      context,
      SYNC_EVENT_VIOLATION.SOURCE_CONTEXT_UNAVAILABLE,
      '9',
    )
  })

  it('N-8: 取消可能な種別の V8 欠落を拒否する', () => {
    const event = eventFor('1')
    delete event.fields.V8

    expectRejected(
      event,
      contextFor('1'),
      SYNC_EVENT_VIOLATION.MISSING_SLOT,
      'V8',
    )
  })

  it('N-8: P3 の V8 を拒否する', () => {
    const event = eventFor('10')
    event.fields.V8 = {}

    expectRejected(
      event,
      contextFor('10'),
      SYNC_EVENT_VIOLATION.FORBIDDEN_SLOT,
      'V8',
    )
  })

  it('N-8: 改訂元の取消可能性を resolver から判定する', () => {
    const event = eventFor('9')
    delete event.fields.V6

    expectRejected(
      event,
      contextFor('9', { sourceEventContextResolver: syncOrderSource }),
      SYNC_EVENT_VIOLATION.FORBIDDEN_SLOT,
      'V8',
    )
    delete event.fields.V8
    expect(() =>
      validateSyncEvent(
        event,
        contextFor('9', { sourceEventContextResolver: syncOrderSource }),
      ),
    ).not.toThrow()
  })

  it('N-8: V8 の不透明な値を解釈せず受理する', () => {
    const opaqueValues: unknown[] = [
      {},
      { level: { values: Array.from({ length: 512 }, (_, i) => ({ i })) } },
    ]

    for (const opaqueValue of opaqueValues) {
      const event = eventFor('1')
      event.fields.V8 = opaqueValue
      expect(() => validateSyncEvent(event, contextFor('1'))).not.toThrow()
    }
  })

  it('N-9: 墓標・改訂以外の V9 を拒否する', () => {
    const event = eventFor('3')
    event.fields.V9 = {}

    expectRejected(
      event,
      contextFor('3'),
      SYNC_EVENT_VIOLATION.FORBIDDEN_SLOT,
      'V9',
    )
  })

  it('N-10: V10 から対象の D4 を落とした参照を拒否する', () => {
    // @ts-expect-error 対象参照は正本が定める3要素をすべて必要とする。
    const missingGeneration: TargetEventReference = {
      試合: 'target-game',
      '対象の D1': 'target-d1',
    }
    const event = eventFor('2')
    event.fields.V10 = missingGeneration

    expectRejected(
      event,
      contextFor('2'),
      SYNC_EVENT_VIOLATION.INVALID_COMPOSITE,
      'V10',
    )
  })

  it('N-11: P3 の V11 欠落を拒否する', () => {
    const event = eventFor('10')
    delete event.fields.V11

    expectRejected(
      event,
      contextFor('10'),
      SYNC_EVENT_VIOLATION.MISSING_SLOT,
      'V11',
    )
  })

  it('N-11: 群 A の V11 を拒否する', () => {
    const event = eventFor('1')
    event.fields.V11 = 'unexpected-version'

    expectRejected(
      event,
      contextFor('1'),
      SYNC_EVENT_VIOLATION.FORBIDDEN_SLOT,
      'V11',
    )
  })

  it('N-12: V12 と復旧世代を型と実行時の双方で拒否する', () => {
    const requestOnlyEvent: SyncEvent = {
      kind: '1',
      fields: {
        ...VALID_FIELDS_BY_KIND['1'],
        // @ts-expect-error V12 は要求レベルでありイベントスロットではない。
        V12: 'proof',
      },
    }
    const recoveryGenerationEvent: SyncEvent = {
      kind: '1',
      fields: {
        ...VALID_FIELDS_BY_KIND['1'],
        // @ts-expect-error 復旧世代はイベント値ではなく要求境界に属する。
        復旧世代: 'generation',
      },
    }

    expectRejected(
      requestOnlyEvent,
      contextFor('1'),
      SYNC_EVENT_VIOLATION.UNKNOWN_SLOT,
      'V12',
    )
    expectRejected(
      recoveryGenerationEvent,
      contextFor('1'),
      SYNC_EVENT_VIOLATION.UNKNOWN_SLOT,
      '復旧世代',
    )
  })

  it.each([
    ['V1', 'V2', 'V2'],
    ['V1', 'V3', 'V3'],
    ['V2', 'V3', 'V3'],
  ] as const)('識別子 %s と %s の同値を拒否する', (left, right, target) => {
    const event = eventFor('1')
    event.fields[right] = event.fields[left]

    expectRejected(
      event,
      contextFor('1'),
      SYNC_EVENT_VIOLATION.IDENTIFIER_COLLISION,
      target,
    )
  })

  it('群 B に D1 付き経路、群 A に P3 を渡した場合を拒否する', () => {
    expectRejected(
      eventFor('10'),
      contextFor('10', { path: SYNC_EVENT_PATH.P1 }),
      SYNC_EVENT_VIOLATION.ROUTE_KIND_MISMATCH,
      '10',
    )
    expectRejected(
      eventFor('1'),
      contextFor('1', { path: SYNC_EVENT_PATH.P3 }),
      SYNC_EVENT_VIOLATION.ROUTE_KIND_MISMATCH,
      '1',
    )
  })

  it('変異 M9: 未知スロットを無視せず拒否する', () => {
    const event = eventFor('1')
    const fields = event.fields as Record<string, unknown>
    fields.UNKNOWN = 'value'

    expectRejected(
      event,
      contextFor('1'),
      SYNC_EVENT_VIOLATION.UNKNOWN_SLOT,
      'UNKNOWN',
    )
  })

  it('フィールド存在は値の形式ではなく own property だけで判定する', () => {
    const event = eventFor('3')
    for (const slot of Object.keys(event.fields) as EventSlotId[]) {
      event.fields[slot] = undefined
    }
    event.fields.V1 = undefined
    event.fields.V2 = null
    event.fields.V3 = false

    expect(() => validateSyncEvent(event, contextFor('3'))).not.toThrow()
  })
})
