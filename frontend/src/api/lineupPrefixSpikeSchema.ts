import canonical from '../../../contracts/state-transition/lineup_play_prefix_payload_schema_v1.json'

/** 正式資産の4安打を保持し、凡打死だけを候補に加える閉schema。 */
function battedOutCandidateSchema() {
  const schema = structuredClone(canonical)
  const defs = schema.$defs as unknown as Record<
    string,
    { properties: Record<string, unknown> }
  >
  const t1 = defs.BattedHitT1Input
  const observations = defs.BattedHitObservations
  const original = [
    'batting-result.single',
    'batting-result.double',
    'batting-result.triple',
    'batting-result.home-run',
  ]
  for (const variant of [t1, observations]) {
    const result = variant?.properties.resultId as { enum?: unknown }
    if (JSON.stringify(result?.enum) !== JSON.stringify(original))
      throw new Error('打球候補の親schemaが変わりました')
    variant!.properties.resultId = {
      enum: [...original, 'batting-result.batted-out'],
    }
  }
  if (
    JSON.stringify(t1!.properties.thirdOutObservation) !==
      JSON.stringify({ const: 'none' }) ||
    JSON.stringify(observations!.properties.thirdOutObservation) !==
      JSON.stringify({
        type: 'object',
        properties: { kind: { const: 'none' } },
        required: ['kind'],
        additionalProperties: false,
      })
  )
    throw new Error('第3アウト候補の親schemaが変わりました')
  t1!.properties.thirdOutObservation = {
    enum: ['none', 'batter-before-first'],
  }
  observations!.properties.thirdOutObservation = {
    oneOf: [
      {
        type: 'object',
        properties: { kind: { const: 'none' } },
        required: ['kind'],
        additionalProperties: false,
      },
      {
        type: 'object',
        properties: {
          kind: { const: 'batter-before-first' },
          batter: {
            type: 'object',
            properties: {
              kind: { const: 'official' },
              player_id: { type: 'string', format: 'uuid' },
            },
            required: ['kind', 'player_id'],
            additionalProperties: false,
          },
        },
        required: ['kind', 'batter'],
        additionalProperties: false,
      },
    ],
  }
  ;(t1 as unknown as { oneOf: unknown }).oneOf = [
    {
      properties: {
        resultId: { enum: original },
        thirdOutObservation: { const: 'none' },
      },
    },
    {
      properties: {
        resultId: { const: 'batting-result.batted-out' },
        thirdOutObservation: { enum: ['none', 'batter-before-first'] },
      },
    },
  ]
  ;(observations as unknown as { oneOf: unknown }).oneOf = [
    {
      properties: {
        resultId: { enum: original },
        thirdOutObservation: {
          type: 'object',
          properties: { kind: { const: 'none' } },
          required: ['kind'],
          additionalProperties: false,
        },
      },
    },
    {
      properties: {
        resultId: { const: 'batting-result.batted-out' },
        thirdOutObservation: observations!.properties.thirdOutObservation,
      },
    },
  ]
  const branches = schema.oneOf as unknown as Array<Record<string, unknown>>
  const hitBranch = branches[1] as {
    properties: {
      observations: {
        allOf: Array<{
          properties?: {
            resultId?: { const: string }
            thirdOutObservation?: unknown
          }
        }>
      }
      calculation: {
        properties: {
          request: {
            properties: {
              t1: {
                allOf: Array<{
                  properties?: {
                    resultId?: { const: string }
                    thirdOutObservation?: unknown
                  }
                }>
              }
            }
          }
        }
      }
    }
  }
  if (
    branches.length !== 8 ||
    hitBranch.properties.observations.allOf[1]?.properties?.resultId?.const !==
      'batting-result.single' ||
    hitBranch.properties.calculation.properties.request.properties.t1.allOf[1]
      ?.properties?.resultId?.const !== 'batting-result.single'
  )
    throw new Error('打球variantの親schemaが変わりました')
  for (const [offset, result] of original.entries()) {
    const branch = branches[offset + 1] as typeof hitBranch
    if (
      branch.properties.observations.allOf[1]?.properties?.resultId?.const !==
        result ||
      branch.properties.calculation.properties.request.properties.t1.allOf[1]
        ?.properties?.resultId?.const !== result
    )
      throw new Error('既安打variantの親schemaが変わりました')
    branch.properties.observations.allOf[1]!.properties!.thirdOutObservation = {
      type: 'object',
      properties: { kind: { const: 'none' } },
      required: ['kind'],
      additionalProperties: false,
    }
    branch.properties.calculation.properties.request.properties.t1.allOf[1]!.properties!.thirdOutObservation =
      { const: 'none' }
  }
  const outBranch = structuredClone(hitBranch)
  outBranch.properties.observations.allOf[1]!.properties!.resultId!.const =
    'batting-result.batted-out'
  outBranch.properties.calculation.properties.request.properties.t1.allOf[1]!.properties!.resultId!.const =
    'batting-result.batted-out'
  delete outBranch.properties.observations.allOf[1]!.properties!
    .thirdOutObservation
  delete outBranch.properties.calculation.properties.request.properties.t1
    .allOf[1]!.properties!.thirdOutObservation
  branches.splice(5, 0, outBranch as unknown as Record<string, unknown>)
  return schema
}

export const lineupPrefixSpikeSchema = battedOutCandidateSchema()
