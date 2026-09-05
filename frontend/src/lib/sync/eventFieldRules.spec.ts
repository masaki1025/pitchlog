import { describe, expect, it } from 'vitest'
import {
  EVENT_FIELD_REQUIREDNESS,
  EVENT_FIELD_PRESENCE,
  EVENT_FIELD_RULES,
  EVENT_SLOT_IDS,
  isCancellableEventKind,
  REQUEST_ONLY_IDS,
  resolveEventFieldPresence,
  SYNC_EVENT_PATH,
  type EventFieldConditionContext,
  type EventFieldRule,
  type EventSlotId,
  type RequestOnlyId,
} from './eventFieldRules'
import {
  EVENT_KIND_RULES,
  EVENT_PARTICIPATION,
  type EventKind,
  type EventKindId,
} from './eventKinds'

function getEventFieldRule(id: EventFieldRule['id']): EventFieldRule {
  const rule = EVENT_FIELD_RULES.find((candidate) => candidate.id === id)
  if (!rule) {
    throw new Error(`イベントフィールド規則がありません: ${id}`)
  }
  return rule
}

function getEventKind(id: EventKindId): EventKind {
  const eventKind = EVENT_KIND_RULES.find((candidate) => candidate.id === id)
  if (!eventKind) {
    throw new Error(`イベント種別がありません: ${id}`)
  }
  return eventKind
}

function conditionContext(
  eventKind: EventKind,
  overrides: Partial<EventFieldConditionContext> = {},
): EventFieldConditionContext {
  return {
    path: SYNC_EVENT_PATH.P1,
    eventKind,
    participation: eventKind.participation,
    cancellable: isCancellableEventKind(eventKind),
    ...overrides,
  }
}

describe('eventFieldRules', () => {
  it('ID が一意で必須区分が3種に閉じている', () => {
    const ids = EVENT_FIELD_RULES.map((rule) => rule.id)
    const requirednesses = EVENT_FIELD_RULES.map((rule) => rule.requiredness)

    expect(new Set(ids).size).toBe(ids.length)
    expect(new Set(requirednesses)).toEqual(
      new Set(Object.values(EVENT_FIELD_REQUIREDNESS)),
    )
  })

  it('V10 だけが3要素の合成 shape を持つ', () => {
    const compositeRules = EVENT_FIELD_RULES.filter(
      (rule) => rule.shape.kind === 'composite',
    )

    expect(compositeRules).toHaveLength(1)
    expect(compositeRules[0]).toMatchObject({
      id: 'V10',
      shape: {
        kind: 'composite',
        elements: ['試合', '対象の D4', '対象の D1'],
      },
    })
  })

  it('イベントスロットと要求レベルを単一表の排他的な分割として導出する', () => {
    const allIds = new Set(EVENT_FIELD_RULES.map((rule) => rule.id))
    const eventSlotIds = new Set<string>(EVENT_SLOT_IDS)
    const requestOnlyIds = new Set<string>(REQUEST_ONLY_IDS)
    const overlap = [...eventSlotIds].filter((id) => requestOnlyIds.has(id))
    const combined = new Set([...eventSlotIds, ...requestOnlyIds])

    expect(overlap).toHaveLength(0)
    expect(combined).toEqual(allIds)
  })

  it('V12 を型と実行時の双方でイベントスロットから除外する', () => {
    const v12IsExcludedAtTypeLevel: 'V12' extends EventSlotId ? false : true =
      true
    const v12IsRequestOnlyAtTypeLevel: 'V12' extends RequestOnlyId
      ? true
      : false = true

    expect(v12IsExcludedAtTypeLevel).toBe(true)
    expect(v12IsRequestOnlyAtTypeLevel).toBe(true)
    expect(EVENT_SLOT_IDS).not.toContain('V12')
    expect(REQUEST_ONLY_IDS).toContain('V12')
  })

  it('全 conditions トークンを既知の経路条件へ写像する', () => {
    const eventKind = getEventKind('1')

    for (const rule of EVENT_FIELD_RULES) {
      expect(() =>
        resolveEventFieldPresence(rule, conditionContext(eventKind)),
      ).not.toThrow()
    }
  })

  it('D1 付き経路と P3 の必須・禁止条件を写像する', () => {
    const eventKind = getEventKind('1')
    const d1Rule = getEventFieldRule('V2')
    const expectedByPath = [
      [SYNC_EVENT_PATH.P1, EVENT_FIELD_PRESENCE.REQUIRED],
      [SYNC_EVENT_PATH.P2, EVENT_FIELD_PRESENCE.REQUIRED],
      [SYNC_EVENT_PATH.P4, EVENT_FIELD_PRESENCE.REQUIRED],
      [SYNC_EVENT_PATH.P3, EVENT_FIELD_PRESENCE.FORBIDDEN],
    ] as const

    for (const [path, expected] of expectedByPath) {
      expect(
        resolveEventFieldPresence(
          d1Rule,
          conditionContext(eventKind, { path }),
        ),
      ).toBe(expected)
    }
  })

  it('参加区分・取消可能性・墓標改訂条件を写像する', () => {
    const logicalKind = getEventKind('1')
    const syncOrderKind = getEventKind('6')
    const tombstoneKind = getEventKind('8')
    const revisionKind = getEventKind('9')
    const changeKind = getEventKind('10')

    expect(
      resolveEventFieldPresence(
        getEventFieldRule('V6'),
        conditionContext(logicalKind),
      ),
    ).toBe(EVENT_FIELD_PRESENCE.REQUIRED)
    expect(
      resolveEventFieldPresence(
        getEventFieldRule('V6'),
        conditionContext(syncOrderKind),
      ),
    ).toBe(EVENT_FIELD_PRESENCE.FORBIDDEN)
    expect(
      resolveEventFieldPresence(
        getEventFieldRule('V8'),
        conditionContext(logicalKind, { cancellable: true }),
      ),
    ).toBe(EVENT_FIELD_PRESENCE.REQUIRED)
    expect(
      resolveEventFieldPresence(
        getEventFieldRule('V8'),
        conditionContext(logicalKind, { cancellable: false }),
      ),
    ).toBe(EVENT_FIELD_PRESENCE.FORBIDDEN)
    for (const eventKind of [tombstoneKind, revisionKind]) {
      expect(
        resolveEventFieldPresence(
          getEventFieldRule('V9'),
          conditionContext(eventKind),
        ),
      ).toBe(EVENT_FIELD_PRESENCE.REQUIRED)
      expect(
        resolveEventFieldPresence(
          getEventFieldRule('V10'),
          conditionContext(eventKind),
        ),
      ).toBe(EVENT_FIELD_PRESENCE.REQUIRED)
    }
    expect(
      resolveEventFieldPresence(
        getEventFieldRule('V10'),
        conditionContext(changeKind, {
          path: SYNC_EVENT_PATH.P3,
          participation: EVENT_PARTICIPATION.DEPENDENT,
        }),
      ),
    ).toBe(EVENT_FIELD_PRESENCE.REQUIRED)
  })

  it('未知の conditions トークンを fail-closed で拒否する', () => {
    const eventKind = getEventKind('1')
    const mutatedRule = {
      ...getEventFieldRule('V1'),
      conditions: ['未知の条件'],
    }

    expect(() =>
      resolveEventFieldPresence(mutatedRule, conditionContext(eventKind)),
    ).toThrowError(/未知のイベントフィールド条件/)
  })
})
