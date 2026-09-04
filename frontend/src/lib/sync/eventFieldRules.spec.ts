import { describe, expect, it } from 'vitest'
import {
  EVENT_FIELD_REQUIREDNESS,
  EVENT_FIELD_RULES,
  EVENT_SLOT_IDS,
  REQUEST_ONLY_IDS,
  type EventSlotId,
  type RequestOnlyId,
} from './eventFieldRules'

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
})
