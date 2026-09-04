import { describe, expect, it } from 'vitest'
import syncProtocolRelations from '@design-relations/sync-protocol.json'
import { EVENT_FIELD_REQUIREDNESS, EVENT_FIELD_RULES } from './eventFieldRules'
import { EVENT_KIND_RULES, EVENT_PARTICIPATION } from './eventKinds'
import { IDEMPOTENCY_COLLISION_RULES } from './idempotencyCollision'
import { V12_BOUNDARY_RULES } from './requestBoundary'
import {
  CANON_IDEMPOTENCY_OUT_OF_SCOPE,
  readCanonEventFieldRules,
  readCanonIdempotencyCollisionRules,
  readCanonParticipationRules,
  readCanonV12BoundaryRules,
  type CanonEventFieldRule,
  type CanonEventKindRule,
  type CanonIdempotencyCollisionRule,
  type CanonV12BoundaryRule,
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

type ComparableV12BoundaryRule = {
  id: string
  condition: string
  outcomes: readonly string[]
  effect: unknown
}

type ComparableIdempotencyCollisionRule = {
  id: string
  rightHandSide: string
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

function expectV12BoundaryRulesToMatchCanon(
  rules: readonly ComparableV12BoundaryRule[],
  canonRules: readonly CanonV12BoundaryRule[],
): void {
  expect(new Set(rules.map((rule) => rule.id))).toEqual(
    new Set(canonRules.map((rule) => rule.id)),
  )
  expect(
    new Map(
      rules.map((rule) => [
        rule.id,
        {
          condition: rule.condition,
          outcomes: rule.outcomes,
          effect: rule.effect,
        },
      ]),
    ),
  ).toEqual(
    new Map(
      canonRules.map((rule) => [
        rule.id,
        {
          condition: rule.condition,
          outcomes: rule.outcomes,
          effect: rule.effect,
        },
      ]),
    ),
  )
}

function expectIdempotencyRulesToMatchCanon(
  rules: readonly ComparableIdempotencyCollisionRule[],
  canonRules: readonly CanonIdempotencyCollisionRule[],
): void {
  expect(new Set(rules.map((rule) => rule.id))).toEqual(
    new Set(canonRules.map((rule) => rule.id)),
  )
  expect(new Map(rules.map((rule) => [rule.id, rule.rightHandSide]))).toEqual(
    new Map(canonRules.map((rule) => [rule.id, rule.rightHandSide])),
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

  it('V12 境界表を R-V12-BOUNDARY と順序非依存の exact-set で照合する', () => {
    const reversedCanonRules = [...readCanonV12BoundaryRules()].reverse()

    expectV12BoundaryRulesToMatchCanon(V12_BOUNDARY_RULES, reversedCanonRules)
  })

  it('変異 M10: 終了後 P3 の V12 必須化を検出する', () => {
    const mutatedRules = structuredClone(V12_BOUNDARY_RULES)
    const target = mutatedRules.find((rule) => rule.id === 'VF3')

    expect(target).toBeDefined()
    if (!target) {
      throw new Error('VF3 がありません')
    }
    if (target.effect.kind !== 'presence') {
      throw new Error('VF3 の写像が不正です')
    }
    ;(target.effect as { required: boolean }).required = true

    expect(() =>
      expectV12BoundaryRulesToMatchCanon(
        mutatedRules,
        readCanonV12BoundaryRules(),
      ),
    ).toThrow()
  })

  it('変異 M11: 進行中 P3 の不成立を B4 に変えたことを検出する', () => {
    const mutatedRules = structuredClone(V12_BOUNDARY_RULES)
    const target = mutatedRules.find((rule) => rule.id === 'VF5')

    expect(target).toBeDefined()
    if (!target) {
      throw new Error('VF5 がありません')
    }
    if (target.effect.kind !== 'failure') {
      throw new Error('VF5 の写像が不正です')
    }
    ;(target.effect as { result: string }).result = 'B4'

    expect(() =>
      expectV12BoundaryRulesToMatchCanon(
        mutatedRules,
        readCanonV12BoundaryRules(),
      ),
    ).toThrow()
  })

  it('R-V12-BOUNDARY の未知 ID を fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-V12-BOUNDARY'].source_elements
    sourceElements[0] = sourceElements[0]!.replace('VF1:', 'VF7:')

    expect(() => readCanonV12BoundaryRules(mutatedRelations)).toThrowError(
      /R-V12-BOUNDARY の ID/,
    )
  })

  it.each([
    ['条件', 'VF1:未知の条件=V12必須'],
    ['帰結', 'VF1:P1・P2・P4=未知の帰結'],
  ])('R-V12-BOUNDARY の未知%s語を fail-closed で拒否する', (_, mutation) => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    mutatedRelations['R-V12-BOUNDARY'].source_elements[0] = mutation

    expect(() => readCanonV12BoundaryRules(mutatedRelations)).toThrowError(
      /R-V12-BOUNDARY の(?:条件|帰結)/,
    )
  })

  it('DI2・DI3・I2・I3 の右辺をオラクルと逐語照合する', () => {
    const reversedCanonRules = [
      ...readCanonIdempotencyCollisionRules(),
    ].reverse()

    expectIdempotencyRulesToMatchCanon(
      IDEMPOTENCY_COLLISION_RULES,
      reversedCanonRules,
    )
  })

  it('D5 衝突規則の射程外 ID を理由つきで列挙する', () => {
    for (const elements of Object.values(CANON_IDEMPOTENCY_OUT_OF_SCOPE)) {
      for (const element of elements) {
        expect(element.id.length).toBeGreaterThan(0)
        expect(element.reason.length).toBeGreaterThan(0)
      }
    }
  })

  it.each(['R-BOUNDARY', 'R-P3-BOUNDARY'] as const)(
    '%s の allow-list にない未知 ID を fail-closed で拒否する',
    (relationId) => {
      const mutatedRelations = structuredClone(syncProtocolRelations)
      mutatedRelations[relationId].source_elements.push(
        'UNKNOWN:D5衝突規則の未知要素',
      )

      expect(() =>
        readCanonIdempotencyCollisionRules(mutatedRelations),
      ).toThrowError(/未知の ID/)
    },
  )

  it('実装対象の右辺変更を逐語照合で検出する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-BOUNDARY'].source_elements
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith('DI2:'),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements[targetIndex] =
      'DI2:D1付き経路の既存D5・同一内容=保存済み結果を再掲'
    expect(() =>
      expectIdempotencyRulesToMatchCanon(
        IDEMPOTENCY_COLLISION_RULES,
        readCanonIdempotencyCollisionRules(mutatedRelations),
      ),
    ).toThrow()
  })
})
