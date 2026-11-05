import canonical from '../../../contracts/state-transition/lineup_play_prefix_payload_schema_v1.json'

/**
 * 正準schemaを変更せず、spike候補の明示進塁だけを同じ閉検査へ追加する。
 *
 * wire値を旧形へ書き換えず、原値をこの拡張schemaで厳格に検証する。
 */
type Json = Record<string, unknown>

const schema = structuredClone(canonical) as Json
const definitions = schema.$defs as Json

const holdAdvance = {
  type: 'object',
  properties: {
    modality: { enum: ['hold', 'not-applicable'] },
    destination: { const: null },
  },
  required: ['modality', 'destination'],
  additionalProperties: false,
}

const moveAdvance = {
  type: 'object',
  properties: {
    modality: { enum: ['optional', 'forced'] },
    destination: { enum: ['1', '2', '3', '4'] },
  },
  required: ['modality', 'destination'],
  additionalProperties: false,
}

const advance = { oneOf: [holdAdvance, moveAdvance] }

const t1 = definitions.T1 as Json
const runnerDefaultAdvance = t1.properties as Json
const runnerDefaultAdvanceFields =
  runnerDefaultAdvance.runnerDefaultAdvance as Json
const runnerDefaultAdvanceProperties =
  runnerDefaultAdvanceFields.properties as Json
runnerDefaultAdvanceProperties.first = advance
runnerDefaultAdvanceProperties.second = advance
runnerDefaultAdvanceProperties.third = advance

const notApplied = {
  type: 'object',
  properties: {
    kind: { const: 'not-applied' },
    overrides: { type: 'array', maxItems: 0 },
  },
  required: ['kind', 'overrides'],
  additionalProperties: false,
}

const applied = {
  type: 'object',
  properties: {
    kind: { const: 'applied' },
    overrides: {
      type: 'array',
      minItems: 1,
      // このspikeの成功入力は一塁走者1人だけ。複数走者はwireで拒否する。
      maxItems: 1,
      items: {
        type: 'object',
        properties: {
          runnerBase: { const: '1' },
          destination: { enum: ['2', '3', '4'] },
        },
        required: ['runnerBase', 'destination'],
        additionalProperties: false,
      },
    },
  },
  required: ['kind', 'overrides'],
  additionalProperties: false,
}

// T1入力は既存の文字列not-appliedと、候補のapplied objectを両立する。
const t1Overrides = { oneOf: [{ const: 'not-applied' }, applied] }
// V7観測は既存のnot-applied objectと、候補のapplied objectを両立する。
const observationOverrides = { oneOf: [notApplied, applied] }

const battedHitT1Input = definitions.BattedHitT1Input as Json
const battedHitT1InputProperties = battedHitT1Input.properties as Json
battedHitT1InputProperties.runnerAdvanceOverrides = t1Overrides

const battedHitObservations = definitions.BattedHitObservations as Json
const battedHitObservationProperties = battedHitObservations.properties as Json
battedHitObservationProperties.runnerAdvanceOverridesByRunner =
  observationOverrides

export const lineupPrefixSpikeSchema = schema
