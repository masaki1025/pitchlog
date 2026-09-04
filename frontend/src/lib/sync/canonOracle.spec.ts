import { describe, expect, it } from 'vitest'
import syncProtocolRelations from '@design-relations/sync-protocol.json'
import { EVENT_FIELD_REQUIREDNESS, EVENT_FIELD_RULES } from './eventFieldRules'
import { EVENT_KIND_RULES, EVENT_PARTICIPATION } from './eventKinds'
import {
  readCanonEventFieldRules,
  readCanonParticipationRules,
  type CanonEventFieldRule,
  type CanonEventKindRule,
} from './canonOracle'

type ComparableRule = {
  id: string
  requiredness: string
  conditions: readonly string[]
  shape: unknown
}

type ComparableEventKind = {
  id: string
  name: string
  participation: string
  hasRevisionOrder: boolean
}

function expectRulesToMatchCanon(
  rules: readonly ComparableRule[],
  canonRules: readonly CanonEventFieldRule[],
): void {
  expect(new Set(rules.map((rule) => rule.id))).toEqual(
    new Set(canonRules.map((rule) => rule.id)),
  )
  expect(new Map(rules.map((rule) => [rule.id, rule.requiredness]))).toEqual(
    new Map(canonRules.map((rule) => [rule.id, rule.requiredness])),
  )
  expect(new Map(rules.map((rule) => [rule.id, rule.conditions]))).toEqual(
    new Map(canonRules.map((rule) => [rule.id, rule.conditions])),
  )
  expect(new Map(rules.map((rule) => [rule.id, rule.shape]))).toEqual(
    new Map(canonRules.map((rule) => [rule.id, rule.shape])),
  )

  const eventSlotIds = rules
    .filter(
      (rule) => rule.requiredness !== EVENT_FIELD_REQUIREDNESS.REQUEST_LEVEL,
    )
    .map((rule) => rule.id)
  const canonEventSlotIds = canonRules
    .filter(
      (rule) => rule.requiredness !== EVENT_FIELD_REQUIREDNESS.REQUEST_LEVEL,
    )
    .map((rule) => rule.id)
  expect(new Set(eventSlotIds)).toEqual(new Set(canonEventSlotIds))
}

function expectEventKindsToMatchCanon(
  eventKinds: readonly ComparableEventKind[],
  canonEventKinds: readonly CanonEventKindRule[],
): void {
  expect(new Set(eventKinds.map((eventKind) => eventKind.id))).toEqual(
    new Set(canonEventKinds.map((eventKind) => eventKind.id)),
  )
  expect(
    new Map(
      eventKinds.map((eventKind) => [
        eventKind.id,
        {
          name: eventKind.name,
          participation: eventKind.participation,
          hasRevisionOrder: eventKind.hasRevisionOrder,
        },
      ]),
    ),
  ).toEqual(
    new Map(
      canonEventKinds.map((eventKind) => [
        eventKind.id,
        {
          name: eventKind.name,
          participation: eventKind.participation,
          hasRevisionOrder: eventKind.hasRevisionOrder,
        },
      ]),
    ),
  )
}

describe('canonOracle', () => {
  it('規則表を R-EVENT-FIELD と順序非依存の exact-set で照合する', () => {
    const reversedCanonRules = [...readCanonEventFieldRules()].reverse()

    expectRulesToMatchCanon(EVENT_FIELD_RULES, reversedCanonRules)
  })

  it('変異 M1: V9 行の欠落を検出する', () => {
    const mutatedRules = EVENT_FIELD_RULES.filter((rule) => rule.id !== 'V9')

    expect(() =>
      expectRulesToMatchCanon(mutatedRules, readCanonEventFieldRules()),
    ).toThrow()
  })

  it('変異 M2: V6 の無条件化を検出する', () => {
    const mutatedRules = EVENT_FIELD_RULES.map((rule) =>
      rule.id === 'V6'
        ? { ...rule, requiredness: EVENT_FIELD_REQUIREDNESS.UNCONDITIONAL }
        : rule,
    )

    expect(() =>
      expectRulesToMatchCanon(mutatedRules, readCanonEventFieldRules()),
    ).toThrow()
  })

  it('変異 M3: V12 のイベント値化を検出する', () => {
    const mutatedRules = EVENT_FIELD_RULES.map((rule) =>
      rule.id === 'V12'
        ? {
            ...rule,
            requiredness: EVENT_FIELD_REQUIREDNESS.EVENT_KIND_CONDITIONAL,
          }
        : rule,
    )

    expect(() =>
      expectRulesToMatchCanon(mutatedRules, readCanonEventFieldRules()),
    ).toThrow()
  })

  it('変異 M4: 未知の条件語を fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-EVENT-FIELD'].source_elements
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith('V6:'),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements[targetIndex] = `${sourceElements[targetIndex]}+未知の条件語`
    expect(() => readCanonEventFieldRules(mutatedRelations)).toThrowError(
      /未知の正本語/,
    )
  })

  it('変異 M4b: conditions の1トークン欠落を検出する', () => {
    const mutatedRules = EVENT_FIELD_RULES.map((rule) =>
      rule.id === 'V2'
        ? { ...rule, conditions: rule.conditions.slice(1) }
        : rule,
    )

    expect(() =>
      expectRulesToMatchCanon(mutatedRules, readCanonEventFieldRules()),
    ).toThrow()
  })

  it('種別表を R-PARTICIPATION と順序非依存の exact-set で照合する', () => {
    const reversedCanonEventKinds = [...readCanonParticipationRules()].reverse()

    expectEventKindsToMatchCanon(EVENT_KIND_RULES, reversedCanonEventKinds)
  })

  it('変異 M5: 墓標の参加区分を従属へ変えたことを検出する', () => {
    const mutatedEventKinds = EVENT_KIND_RULES.map((eventKind) =>
      eventKind.id === '8'
        ? { ...eventKind, participation: EVENT_PARTICIPATION.DEPENDENT }
        : eventKind,
    )

    expect(() =>
      expectEventKindsToMatchCanon(
        mutatedEventKinds,
        readCanonParticipationRules(),
      ),
    ).toThrow()
  })

  it('変異 M6: 改訂版の参加区分を一律従属へ変えたことを検出する', () => {
    const mutatedEventKinds = EVENT_KIND_RULES.map((eventKind) =>
      eventKind.id === '9'
        ? { ...eventKind, participation: EVENT_PARTICIPATION.DEPENDENT }
        : eventKind,
    )

    expect(() =>
      expectEventKindsToMatchCanon(
        mutatedEventKinds,
        readCanonParticipationRules(),
      ),
    ).toThrow()
  })

  it('変異 M7: undo の参加区分を論理位置ありへ変えたことを検出する', () => {
    const mutatedEventKinds = EVENT_KIND_RULES.map((eventKind) =>
      eventKind.id === '2'
        ? { ...eventKind, participation: EVENT_PARTICIPATION.LOGICAL_POSITION }
        : eventKind,
    )

    expect(() =>
      expectEventKindsToMatchCanon(
        mutatedEventKinds,
        readCanonParticipationRules(),
      ),
    ).toThrow()
  })

  it('変異 M8: 種別の追加と欠落を検出する', () => {
    const addedEventKinds: ComparableEventKind[] = [
      ...EVENT_KIND_RULES,
      { ...EVENT_KIND_RULES[0], id: '13', name: '追加種別' },
    ]
    const removedEventKinds = EVENT_KIND_RULES.filter(
      (eventKind) => eventKind.id !== '1',
    )

    expect(() =>
      expectEventKindsToMatchCanon(
        addedEventKinds,
        readCanonParticipationRules(),
      ),
    ).toThrow()
    expect(() =>
      expectEventKindsToMatchCanon(
        removedEventKinds,
        readCanonParticipationRules(),
      ),
    ).toThrow()
  })

  it('R-PARTICIPATION の未知 ID を fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    mutatedRelations['R-PARTICIPATION'].source_elements.push('13:追加種別=従属')

    expect(() => readCanonParticipationRules(mutatedRelations)).toThrowError(
      /未知の R-PARTICIPATION ID/,
    )
  })
})
