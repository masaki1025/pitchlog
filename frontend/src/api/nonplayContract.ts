/** 既閉契約の形だけを読む。計算・原本資格・保存成功を導出しない。 */
import lifecycle from '../../../contracts/state-transition/game_lifecycle_schema_v1.json'
import nonplay from '../../../contracts/state-transition/nonplay_prefix_bridge_schema_v1.json'
import undo from '../../../contracts/state-transition/undo_schema_v1.json'
import lineup from '../../../contracts/state-transition/lineup_play_prefix_schema_v1.json'
import payload from '../../../contracts/state-transition/lineup_play_prefix_payload_schema_v1.json'
import { sameOrdinaryWire } from './ordinaryPitchWire'
import { canonicalPlayJson } from './terminalPitchWire'

type Rule = {
  $ref?: string
  $id?: string
  $defs?: Record<string, Rule>
  type?: string
  const?: unknown
  enum?: unknown[]
  anyOf?: Rule[]
  oneOf?: Rule[]
  allOf?: Rule[]
  properties?: Record<string, Rule>
  required?: string[]
  additionalProperties?: boolean | Rule
  items?: Rule
  minimum?: number
  maximum?: number
  minItems?: number
  maxItems?: number
  minLength?: number
  maxLength?: number
  pattern?: string
  uniqueItems?: boolean
}
const schemas = {
  game_lifecycle_schema_v1: lifecycle,
  nonplay_prefix_bridge_schema_v1: nonplay,
  undo_schema_v1: undo,
  lineup_play_prefix_schema_v1: lineup,
  lineup_play_prefix_payload_schema_v1: payload,
} as unknown as Record<string, Rule>
export type NonplaySchema =
  | 'game_lifecycle_schema_v1'
  | 'nonplay_prefix_bridge_schema_v1'
  | 'undo_schema_v1'
  | 'lineup_play_prefix_schema_v1'
  | 'lineup_play_prefix_payload_schema_v1'
const allowed = new Set([
  '$comment',
  '$defs',
  '$id',
  '$ref',
  '$schema',
  'additionalProperties',
  'allOf',
  'anyOf',
  'const',
  'enum',
  'items',
  'maxItems',
  'maxLength',
  'maximum',
  'minLength',
  'minimum',
  'oneOf',
  'pattern',
  'properties',
  'required',
  'title',
  'type',
  'uniqueItems',
  'x-pitchlog-axis-id',
])
function object(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}
function matches(v: unknown, rule: Rule, origin: string): boolean {
  if (Object.keys(rule).some((k) => !allowed.has(k))) return false
  if (rule.$ref) {
    const [file, pointer] = rule.$ref.split('#')
    if (!pointer?.startsWith('/$defs/') || pointer.slice(8).includes('/'))
      return false
    const target =
      file === ''
        ? origin
        : Object.keys(schemas).find(
            (k) => file === k + '.json' || file === schemas[k]?.$id,
          )
    const key = pointer.slice(7),
      schema = target === undefined ? undefined : schemas[target]
    if (!schema?.$defs || !Object.hasOwn(schema.$defs, key)) return false
    return matches(v, schema.$defs[key]!, target!)
  }
  if (Object.hasOwn(rule, 'const') && !sameOrdinaryWire(v, rule.const))
    return false
  if (rule.enum && !rule.enum.some((x) => sameOrdinaryWire(v, x))) return false
  if (rule.allOf && !rule.allOf.every((x) => matches(v, x, origin)))
    return false
  if (rule.anyOf && !rule.anyOf.some((x) => matches(v, x, origin))) return false
  if (
    rule.oneOf &&
    rule.oneOf.filter((x) => matches(v, x, origin)).length !== 1
  )
    return false
  if (rule.type === 'null' && v !== null) return false
  if (rule.type === 'boolean' && typeof v !== 'boolean') return false
  if (
    rule.type === 'integer' &&
    (typeof v !== 'number' || !Number.isSafeInteger(v))
  )
    return false
  if (rule.type === 'number' && (typeof v !== 'number' || !Number.isFinite(v)))
    return false
  if (rule.type === 'string' && typeof v !== 'string') return false
  if (rule.type === 'array' && !Array.isArray(v)) return false
  if (rule.type === 'object' && !object(v)) return false
  if (
    rule.type &&
    ![
      'null',
      'boolean',
      'integer',
      'number',
      'string',
      'array',
      'object',
    ].includes(rule.type)
  )
    return false
  if (
    typeof v === 'number' &&
    ((rule.minimum !== undefined && v < rule.minimum) ||
      (rule.maximum !== undefined && v > rule.maximum))
  )
    return false
  if (
    typeof v === 'string' &&
    ((rule.minLength !== undefined && [...v].length < rule.minLength) ||
      (rule.maxLength !== undefined && [...v].length > rule.maxLength) ||
      (rule.pattern !== undefined && !new RegExp(rule.pattern).test(v)))
  )
    return false
  if (
    Array.isArray(v) &&
    ((rule.minItems !== undefined && v.length < rule.minItems) ||
      (rule.maxItems !== undefined && v.length > rule.maxItems) ||
      (rule.uniqueItems === true &&
        v.some((item, index) =>
          v.slice(index + 1).some((other) => sameOrdinaryWire(item, other)),
        )) ||
      (rule.items !== undefined &&
        !v.every((x) => matches(x, rule.items!, origin))))
  )
    return false
  if (object(v)) {
    if (rule.required?.some((k) => !Object.hasOwn(v, k))) return false
    for (const [key, value] of Object.entries(v)) {
      const child = rule.properties?.[key]
      if (
        child
          ? !matches(value, child, origin)
          : rule.additionalProperties === false ||
            (typeof rule.additionalProperties === 'object' &&
              !matches(value, rule.additionalProperties, origin))
      )
        return false
    }
  }
  return true
}
/** 固定schemaの名前付き型だけを検査。外部取得・未対応制約の無視はしない。 */
export function isNonplayDefinition<T>(
  value: unknown,
  name: string,
  schema: NonplaySchema = 'nonplay_prefix_bridge_schema_v1',
): value is T {
  try {
    const rule =
      name === '$root' ? schemas[schema] : schemas[schema]?.$defs?.[name]
    if (rule === undefined) return false
    canonicalPlayJson(value)
    return matches(value, rule, schema)
  } catch {
    return false
  }
}
