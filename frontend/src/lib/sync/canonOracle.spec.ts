import { describe, expect, it } from 'vitest'
import syncProtocolRelations from '@design-relations/sync-protocol.json'
import { EVENT_FIELD_REQUIREDNESS, EVENT_FIELD_RULES } from './eventFieldRules'
import { EVENT_KIND_RULES, EVENT_PARTICIPATION } from './eventKinds'
import {
  B3_EXISTING_D5_BRANCH_RULE,
  IDEMPOTENCY_COLLISION_RULES,
} from './idempotencyCollision'
import { V12_BOUNDARY_RULES } from './requestBoundary'
import { TEMPORARY_ID_MAPPING_RULES } from './temporaryIdMapping'
import { PROCESSING_STAGE_RULES } from './processingStages'
import {
  CANON_ACK_STATE_RESULT,
  CANON_IDEMPOTENCY_OUT_OF_SCOPE,
  CANON_TEMPORARY_ID_MAPPING_OUT_OF_SCOPE,
  parseCanonAckStateResults,
  parseCanonBoundaryResults,
  parseCanonP3BoundaryResults,
  parseCanonQueueLifeRules,
  parseCanonTombstoneRule,
  parseCanonTxnRouteRules,
  readCanonAckStateResults,
  readCanonB3BranchRules,
  readCanonBoundaryResults,
  readCanonEventFieldRules,
  readCanonIdempotencyCollisionRules,
  readCanonP3BoundaryResults,
  readCanonParticipationRules,
  readCanonProcessingStageRules,
  readCanonQueueLifeRules,
  readCanonTemporaryIdMappingRules,
  readCanonTombstoneRule,
  readCanonTxnRouteRules,
  readCanonV12BoundaryRules,
  type CanonEventFieldRule,
  type CanonB3BranchRule,
  type CanonBoundaryResult,
  type CanonEventKindRule,
  type CanonIdempotencyCollisionRule,
  type CanonP3BoundaryResult,
  type CanonProcessingStageRule,
  type CanonTemporaryIdMappingRule,
  type CanonTxnRouteRule,
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

type ComparableProcessingStageRule = {
  purpose: string
  relationId: string
  id: string
  rightHandSide: string
}

type CanonTxnRoute = Extract<CanonTxnRouteRule, { kind: 'route' }>

function isCanonTxnRoute(rule: CanonTxnRouteRule): rule is CanonTxnRoute {
  return Object.is(rule.kind, 'route')
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

function expectProcessingStageRulesToMatchCanon(
  rules: readonly ComparableProcessingStageRule[],
  canonRules: readonly CanonProcessingStageRule[],
): void {
  const toRuleMap = (source: readonly ComparableProcessingStageRule[]) =>
    new Map(
      source.map((rule) => [
        `${rule.relationId}:${rule.id}`,
        {
          purpose: rule.purpose,
          rightHandSide: rule.rightHandSide,
        },
      ]),
    )

  expect(toRuleMap(rules)).toEqual(toRuleMap(canonRules))
}

function expectB3BranchRuleToMatchCanon(
  canonRules: readonly CanonB3BranchRule[],
): void {
  expect(canonRules).toEqual([
    {
      purpose: 'b3-branch',
      relationId: 'R-BOUNDARY',
      id: B3_EXISTING_D5_BRANCH_RULE.id,
      rightHandSide: B3_EXISTING_D5_BRANCH_RULE.rightHandSide,
    },
  ])
}

function expectTemporaryIdMappingRulesToMatchCanon(
  rules: readonly ComparableIdempotencyCollisionRule[],
  canonRules: readonly CanonTemporaryIdMappingRule[],
): void {
  expect(new Set(rules.map((rule) => rule.id))).toEqual(
    new Set(canonRules.map((rule) => rule.id)),
  )
  expect(new Map(rules.map((rule) => [rule.id, rule.rightHandSide]))).toEqual(
    new Map(canonRules.map((rule) => [rule.id, rule.rightHandSide])),
  )
}

describe('canonOracle', () => {
  it('R-BOUNDARY から B1〜B7 の境界結果を読む', () => {
    const sourceElements = syncProtocolRelations['R-BOUNDARY'].source_elements
    const expectedResults = sourceElements.slice(0, 7).map((sourceElement) => {
      const separatorIndex = sourceElement.indexOf(':')
      return {
        id: sourceElement.slice(0, separatorIndex),
        name: sourceElement.slice(separatorIndex + 1),
      }
    })

    expect(readCanonBoundaryResults()).toEqual(expectedResults)
    expect(parseCanonBoundaryResults(sourceElements)).toEqual(expectedResults)
  })

  it('R-BOUNDARY の未知 ID を fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    mutatedRelations['R-BOUNDARY'].source_elements.push(
      'UNKNOWN:未知の境界結果',
    )

    expect(() => readCanonBoundaryResults(mutatedRelations)).toThrowError(
      /未知の ID/,
    )
  })

  it('R-BOUNDARY の境界結果欠落を fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    mutatedRelations['R-BOUNDARY'].source_elements.splice(0, 1)

    expect(() => readCanonBoundaryResults(mutatedRelations)).toThrowError(
      /既知 ID 集合/,
    )
  })

  it('CanonBoundaryResult を ID と名称だけに閉じる', () => {
    const result: CanonBoundaryResult = { id: 'boundary', name: 'result' }

    expect(Object.keys(result).sort()).toEqual(['id', 'name'])
  })

  it('R-P3-BOUNDARY から P3 の独立結果8種だけを読む', () => {
    const sourceElements =
      syncProtocolRelations['R-P3-BOUNDARY'].source_elements
    const expectedResults: CanonP3BoundaryResult[] = sourceElements
      .slice(0, 8)
      .map((sourceElement) => {
        const separatorIndex = sourceElement.indexOf(':')
        return separatorIndex < 0
          ? { id: sourceElement, name: sourceElement, accepted: true }
          : {
              id: sourceElement.slice(0, separatorIndex),
              name: sourceElement.slice(separatorIndex + 1),
              accepted: false,
            }
      })

    expect(readCanonP3BoundaryResults()).toEqual(expectedResults)
    expect(parseCanonP3BoundaryResults(sourceElements)).toEqual(expectedResults)
    const acceptedResults = expectedResults.filter((result) => result.accepted)
    expect(acceptedResults).toHaveLength(1)
    expect(acceptedResults[0]?.id).toBe(expectedResults[0]?.id)
  })

  it('R-P3-BOUNDARY の未知 ID を専用 reader でも fail-closed に拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    mutatedRelations['R-P3-BOUNDARY'].source_elements.push(
      'B15:未知の P3 境界結果',
    )

    expect(() => readCanonP3BoundaryResults(mutatedRelations)).toThrowError(
      /未知の ID/,
    )
  })

  it('R-P3-BOUNDARY の受理結果欠落を fail-closed に拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    mutatedRelations['R-P3-BOUNDARY'].source_elements.splice(0, 1)

    expect(() => readCanonP3BoundaryResults(mutatedRelations)).toThrowError(
      /既知 ID 集合/,
    )
  })

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

  it('K5 専用 reader が R-PARTICIPATION の定義行だけを返す', () => {
    const sourceElements =
      syncProtocolRelations['R-PARTICIPATION'].source_elements
    const parsedRule = parseCanonTombstoneRule(sourceElements)
    const readRule = readCanonTombstoneRule()

    expect(readRule).toEqual(parsedRule)
    expect(readRule.id).toBe('K5')
    expect(readRule.tokens).toHaveLength(2)
  })

  it('K5 の未知トークンを fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-PARTICIPATION'].source_elements
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith('K5:'),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements[targetIndex] = `${sourceElements[targetIndex]}+未知トークン`
    expect(() => readCanonTombstoneRule(mutatedRelations)).toThrowError(
      /R-PARTICIPATION の定義が不正/,
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

  it('B3b の右辺3節を製品表と逐語照合する', () => {
    expectB3BranchRuleToMatchCanon(readCanonB3BranchRules())
  })

  it('B3b の右辺変更を製品表との逐語照合で検出する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-BOUNDARY'].source_elements
    const targetId = 'B3b'
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith(`${targetId}:`),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements[targetIndex] = sourceElements[targetIndex]!.replace(
      'T9開始なし',
      'T9開始あり',
    )
    expect(() =>
      expectB3BranchRuleToMatchCanon(readCanonB3BranchRules(mutatedRelations)),
    ).toThrow()
  })

  it('DI1・DI4・I1・I4 の右辺を処理段階の製品表と逐語照合する', () => {
    const productRuleKeys = new Set(
      PROCESSING_STAGE_RULES.map((rule) => `${rule.relationId}:${rule.id}`),
    )
    const reversedCanonRules = readCanonProcessingStageRules()
      .filter((rule) => productRuleKeys.has(`${rule.relationId}:${rule.id}`))
      .reverse()

    expectProcessingStageRulesToMatchCanon(
      PROCESSING_STAGE_RULES,
      reversedCanonRules,
    )
  })

  it('処理段階へ移した4 ID の右辺変更を逐語照合で検出する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-BOUNDARY'].source_elements
    const targetId = 'DI1'
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith(`${targetId}:`),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements[targetIndex] = sourceElements[targetIndex]!.replace(
      '③認可後',
      '③認可前',
    )
    expect(() =>
      expectProcessingStageRulesToMatchCanon(
        PROCESSING_STAGE_RULES,
        readCanonProcessingStageRules(mutatedRelations).filter(
          (rule) => !Object.is(rule.id, 'RG1'),
        ),
      ),
    ).toThrow()
  })

  it('実装済みと射程外の総和を正本の ID 集合と一致させる', () => {
    const implementedRules = [
      ...readCanonIdempotencyCollisionRules(),
      ...readCanonProcessingStageRules(),
      ...readCanonB3BranchRules(),
    ]

    for (const relationId of ['R-BOUNDARY', 'R-P3-BOUNDARY'] as const) {
      const sourceIds = syncProtocolRelations[relationId].source_elements.map(
        (element) => {
          const separatorIndex = element.indexOf(':')
          return separatorIndex < 0 ? element : element.slice(0, separatorIndex)
        },
      )
      const implementedIds = implementedRules
        .filter((rule) => Object.is(rule.relationId, relationId))
        .map((rule) => rule.id)
      const outOfScopeIds = CANON_IDEMPOTENCY_OUT_OF_SCOPE[relationId].map(
        (element) => element.id,
      )

      expect(new Set([...implementedIds, ...outOfScopeIds])).toEqual(
        new Set(sourceIds),
      )
    }
  })

  it('実装対象を射程外から除き P3 受理結果を先頭に保つ', () => {
    const d1OutOfScopeIds = new Set<string>(
      CANON_IDEMPOTENCY_OUT_OF_SCOPE['R-BOUNDARY'].map((element) => element.id),
    )
    const p3OutOfScopeIds = new Set<string>(
      CANON_IDEMPOTENCY_OUT_OF_SCOPE['R-P3-BOUNDARY'].map(
        (element) => element.id,
      ),
    )

    expect(d1OutOfScopeIds.has('DI1')).toBe(false)
    expect(d1OutOfScopeIds.has('DI4')).toBe(false)
    expect(p3OutOfScopeIds.has('I1')).toBe(false)
    expect(p3OutOfScopeIds.has('I4')).toBe(false)
    expect(d1OutOfScopeIds.has('RG1')).toBe(false)
    expect(p3OutOfScopeIds.has('RG1')).toBe(false)
    expect(d1OutOfScopeIds.has('B3b')).toBe(false)
    expect(CANON_IDEMPOTENCY_OUT_OF_SCOPE['R-P3-BOUNDARY'][0]?.id).toBe(
      '変更受理',
    )
  })

  it('射程外に残す4 ID の理由へ受け取り先と依存事項を明記する', () => {
    const expectedReasonParts = Object.freeze({
      B3a: Object.freeze(['T9 の保存', 'TSK-330']),
      DI5: Object.freeze(['U-14', 'B1・B4', 'TSK-330']),
      I5: Object.freeze(['保存・配信', 'TSK-330']),
      I6: Object.freeze(['端末永続化', 'TSK-330']),
    })
    const allOutOfScopeElements = Object.freeze(
      Object.values(CANON_IDEMPOTENCY_OUT_OF_SCOPE).flat(),
    )

    for (const [id, reasonParts] of Object.entries(expectedReasonParts)) {
      const target = allOutOfScopeElements.find((element) =>
        Object.is(element.id, id),
      )

      expect(target).toBeDefined()
      if (!target) {
        throw new Error(`射程外 ID がありません: ${id}`)
      }
      for (const reasonPart of reasonParts) {
        expect(target.reason).toContain(reasonPart)
      }
    }
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

  it.each([
    ['R-BOUNDARY', 'B1'],
    ['R-P3-BOUNDARY', 'B8'],
  ] as const)(
    '%s の射程外行 %s の欠落を fail-closed で拒否する',
    (relationId, removedId) => {
      const mutatedRelations = structuredClone(syncProtocolRelations)
      const sourceElements = mutatedRelations[relationId].source_elements
      const targetIndex = sourceElements.findIndex((element) =>
        element.startsWith(`${removedId}:`),
      )

      expect(targetIndex).toBeGreaterThanOrEqual(0)
      sourceElements.splice(targetIndex, 1)
      expect(() =>
        readCanonIdempotencyCollisionRules(mutatedRelations),
      ).toThrowError(/既知 ID 集合/)
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

  it('C2・C3 の右辺を R-TEMP-ID-MAPPING と逐語照合する', () => {
    const productRuleIds = new Set<string>(
      TEMPORARY_ID_MAPPING_RULES.map((rule) => rule.id),
    )
    const reversedCanonRules = readCanonTemporaryIdMappingRules()
      .filter((rule) => productRuleIds.has(rule.id))
      .reverse()

    expectTemporaryIdMappingRulesToMatchCanon(
      TEMPORARY_ID_MAPPING_RULES,
      reversedCanonRules,
    )
  })

  it('C1 だけを理由つきの射程外 allow-list に置く', () => {
    expect(
      CANON_TEMPORARY_ID_MAPPING_OUT_OF_SCOPE.map((element) => element.id),
    ).toEqual(['C1'])
    for (const element of CANON_TEMPORARY_ID_MAPPING_OUT_OF_SCOPE) {
      expect(element.reason.length).toBeGreaterThan(0)
    }
  })

  it('R-TEMP-ID-MAPPING の allow-list にない未知 ID を fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    mutatedRelations['R-TEMP-ID-MAPPING'].source_elements.push(
      'C5:未知の写像契約',
    )

    expect(() =>
      readCanonTemporaryIdMappingRules(mutatedRelations),
    ).toThrowError(/未知の ID/)
  })

  it('R-TEMP-ID-MAPPING の射程外行 C1 の欠落を fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-TEMP-ID-MAPPING'].source_elements
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith('C1:'),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements.splice(targetIndex, 1)
    expect(() =>
      readCanonTemporaryIdMappingRules(mutatedRelations),
    ).toThrowError(/既知 ID 集合/)
  })

  it('C2・C3 の右辺変更を逐語照合で検出する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-TEMP-ID-MAPPING'].source_elements
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith('C2:'),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements[targetIndex] = 'C2:後続イベントの参照+決定的に解決'
    const productRuleIds = new Set<string>(
      TEMPORARY_ID_MAPPING_RULES.map((rule) => rule.id),
    )
    expect(() =>
      expectTemporaryIdMappingRulesToMatchCanon(
        TEMPORARY_ID_MAPPING_RULES,
        readCanonTemporaryIdMappingRules(mutatedRelations).filter((rule) =>
          productRuleIds.has(rule.id),
        ),
      ),
    ).toThrow()
  })

  it('R-TXN-ROUTE の reader と parser が同じ経路規則を返す', () => {
    const sourceElements = syncProtocolRelations['R-TXN-ROUTE'].source_elements
    const rules: readonly CanonTxnRouteRule[] = readCanonTxnRouteRules()

    expect(rules).toEqual(parseCanonTxnRouteRules(sourceElements))
    expect(rules).toHaveLength(14)
    expect(rules.filter((rule) => Object.is(rule.kind, 'route'))).toHaveLength(
      5,
    )
    expect(rules.filter((rule) => Object.is(rule.kind, 'step'))).toHaveLength(9)
  })

  it('R-TXN-ROUTE のパース結果から14要素を逐語かつ順序込みで復元する', () => {
    const sourceElements = syncProtocolRelations['R-TXN-ROUTE'].source_elements
    const rules = parseCanonTxnRouteRules(sourceElements)
    const reconstructedElements = Object.freeze(
      rules.map((rule) =>
        isCanonTxnRoute(rule)
          ? `${rule.id}:${rule.name}=${rule.stepIds.join(',')}`
          : `${rule.id}:${rule.name}`,
      ),
    )

    expect(reconstructedElements).toEqual(sourceElements)
  })

  it('R-TXN-ROUTE の公開写像を重複のない18組へ展開する', () => {
    const routeRules = parseCanonTxnRouteRules(
      syncProtocolRelations['R-TXN-ROUTE'].source_elements,
    ).filter(isCanonTxnRoute)
    const routeStepPairs = Object.freeze(
      routeRules.flatMap((rule) =>
        rule.stepIds.map((stepId) => `${rule.id}:${stepId}`),
      ),
    )

    expect(routeStepPairs).toHaveLength(18)
    expect(new Set(routeStepPairs).size).toBe(18)
  })

  it('R-TXN-ROUTE の5経路ごとの T 要素列を正本どおりに固定する', () => {
    const expectedStepIds = Object.freeze({
      P1: Object.freeze(['T1', 'T2', 'T3', 'T4', 'T6']),
      P2: Object.freeze(['T1', 'T2', 'T3', 'T4', 'T5', 'T6']),
      P3: Object.freeze(['T1', 'T2', 'T4', 'T6', 'T7']),
      P4: Object.freeze(['T8']),
      P5: Object.freeze(['T9']),
    })
    const routeRules = parseCanonTxnRouteRules(
      syncProtocolRelations['R-TXN-ROUTE'].source_elements,
    ).filter(isCanonTxnRoute)

    expect(routeRules).toHaveLength(5)
    for (const rule of routeRules) {
      expect(rule.stepIds).toEqual(expectedStepIds[rule.id])
    }
  })

  it('R-TXN-ROUTE の未知 ID を fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    mutatedRelations['R-TXN-ROUTE'].source_elements.push('UNKNOWN:未知の経路')

    expect(() => readCanonTxnRouteRules(mutatedRelations)).toThrowError(
      /未知の ID/,
    )
  })

  it('R-TXN-ROUTE の T 要素行に混入した等号を拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-TXN-ROUTE'].source_elements
    const targetId = 'T3'
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith(`${targetId}:`),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements[targetIndex] = 'T3:prefix更新=何か'
    expect(() => readCanonTxnRouteRules(mutatedRelations)).toThrowError(
      /T 要素形式/,
    )
  })

  it('R-TXN-ROUTE の経路行から等号が欠落した形式を拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-TXN-ROUTE'].source_elements
    const targetId = 'P1'
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith(`${targetId}:`),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements[targetIndex] = 'P1:D1付きイベント'
    expect(() => readCanonTxnRouteRules(mutatedRelations)).toThrowError(
      /経路形式/,
    )
  })

  it('R-TXN-ROUTE の経路が参照しない T 要素を拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-TXN-ROUTE'].source_elements
    const targetId = 'P2'
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith(`${targetId}:`),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements[targetIndex] = sourceElements[targetIndex]!.replace(
      ',T5',
      '',
    )
    expect(() => readCanonTxnRouteRules(mutatedRelations)).toThrowError(
      /参照 T 要素.*既知 ID 集合/,
    )
  })

  it('R-TXN-ROUTE の重複 ID を拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-TXN-ROUTE'].source_elements
    const targetId = 'P4'
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith(`${targetId}:`),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements.push(sourceElements[targetIndex]!)
    expect(() => readCanonTxnRouteRules(mutatedRelations)).toThrowError(
      /ID が重複/,
    )
  })

  it('R-QUEUE-LIFE の全伝播先を source_elements の被覆として照合する', () => {
    const relation = syncProtocolRelations['R-QUEUE-LIFE']
    const sourceElements = relation.source_elements
    const sourceElementSet = new Set<string>(sourceElements)
    const propagatedElements = new Set<string>()

    expect(sourceElements).toHaveLength(5)
    expect(parseCanonQueueLifeRules(sourceElements)).toEqual(
      readCanonQueueLifeRules(),
    )
    expect(new Set(Object.keys(relation.expected_elements))).toEqual(
      new Set(relation.targets),
    )
    for (const targetElements of Object.values(relation.expected_elements)) {
      for (const element of targetElements) {
        expect(sourceElementSet.has(element)).toBe(true)
        propagatedElements.add(element)
      }
    }
    expect(propagatedElements).toEqual(sourceElementSet)
  })

  it('R-QUEUE-LIFE の未知状態を fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    mutatedRelations['R-QUEUE-LIFE'].source_elements.push('未知のキュー状態')

    expect(() => readCanonQueueLifeRules(mutatedRelations)).toThrowError(
      /未知の状態または ID/,
    )
  })

  it('R-QUEUE-LIFE の未知 I6 トークンを fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    const sourceElements = mutatedRelations['R-QUEUE-LIFE'].source_elements
    const targetIndex = sourceElements.findIndex((element) =>
      element.startsWith('I6:'),
    )

    expect(targetIndex).toBeGreaterThanOrEqual(0)
    sourceElements[targetIndex] = sourceElements[targetIndex]!.replace(
      '+復元規則なし',
      '+未知の保持契約',
    )
    expect(() => readCanonQueueLifeRules(mutatedRelations)).toThrowError(
      /未知の I6 トークン/,
    )
  })

  it('R-ACK-STATE の全結果を各伝播先と照合する', () => {
    const relation = syncProtocolRelations['R-ACK-STATE']
    const sourceElements = relation.source_elements
    const sourceElementSet = new Set<string>(sourceElements)

    expect(sourceElements).toHaveLength(5)
    expect(CANON_ACK_STATE_RESULT).toEqual({
      ACCEPTED: '受理',
      DUPLICATE: '重複',
      REJECTED: '拒否',
      EVACUATED: '退避',
      UNPROCESSED: '未処理',
    })
    expect(new Set(Object.values(CANON_ACK_STATE_RESULT))).toEqual(
      sourceElementSet,
    )
    expect(parseCanonAckStateResults(sourceElements)).toEqual(
      readCanonAckStateResults(),
    )
    expect(new Set(Object.keys(relation.expected_elements))).toEqual(
      new Set(relation.targets),
    )
    for (const targetElements of Object.values(relation.expected_elements)) {
      expect(targetElements).toHaveLength(sourceElements.length)
      expect(new Set(targetElements)).toEqual(sourceElementSet)
    }
  })

  it('R-ACK-STATE の未知要素を fail-closed で拒否する', () => {
    const mutatedRelations = structuredClone(syncProtocolRelations)
    mutatedRelations['R-ACK-STATE'].source_elements[0] = '未知のA5結果'

    expect(() => readCanonAckStateResults(mutatedRelations)).toThrowError(
      /未知の要素/,
    )
  })
})
