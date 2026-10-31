import schema from '../../../contracts/state-transition/play_prefix_v2_payload_schema.json'
import type {
  PlayRequest,
  PlaySuccess,
  Snapshot,
} from '../../../contracts/state-transition/play_prefix_v2'
import type {
  PlayPrefixV7,
  PlayPrefixV8,
  Observations,
  Participants,
} from '../../../contracts/state-transition/play_prefix_v2_payload_v1'
import identity from '../../public/domain/pitchlog-domain.json'
import { sameOrdinaryWire } from './ordinaryPitchWire'

export type { PlayRequest, PlaySuccess, Snapshot, PlayPrefixV7 }
/** 構造検査だけにschemaを使う。野球の期待値/状態計算は持たない。 */
type Schema = {
  $ref?: string
  const?: unknown
  enum?: unknown[]
  type?: string
  oneOf?: Schema[]
  anyOf?: Schema[]
  properties?: Record<string, Schema>
  required?: string[]
  additionalProperties?: boolean
  items?: Schema
  minItems?: number
  maxItems?: number
  minLength?: number
  maxLength?: number
  pattern?: string
}
const definitions = schema.$defs as Record<string, Schema>
export function exactPlayObject(
  value: unknown,
  keys: readonly string[],
): value is Record<string, unknown> {
  return (
    value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    Object.keys(value).length === keys.length &&
    keys.every((k) => Object.hasOwn(value, k))
  )
}
const schemaKeywords = new Set([
  '$defs',
  '$id',
  '$ref',
  '$schema',
  'additionalProperties',
  'anyOf',
  'const',
  'enum',
  'items',
  'maxItems',
  'maxLength',
  'minItems',
  'minLength',
  'oneOf',
  'pattern',
  'properties',
  'required',
  'type',
])
function matches(value: unknown, rule: Schema): boolean {
  // 未対応の将来制約を無視して通さず、更新時は明示的に追随する。
  if (
    Object.keys(rule).some((k) => !schemaKeywords.has(k)) ||
    (rule.type !== undefined &&
      !['object', 'array', 'string', 'boolean', 'null'].includes(rule.type))
  )
    return false
  if (rule.$ref) {
    const key = rule.$ref.replace('#/$defs/', '')
    return (
      rule.$ref === '#/$defs/' + key &&
      Object.hasOwn(definitions, key) &&
      matches(value, definitions[key]!)
    )
  }
  if (Object.hasOwn(rule, 'const') && !sameOrdinaryWire(value, rule.const))
    return false
  if (rule.enum && !rule.enum.some((v) => sameOrdinaryWire(v, value)))
    return false
  if (rule.oneOf && rule.oneOf.filter((v) => matches(value, v)).length !== 1)
    return false
  if (rule.anyOf && !rule.anyOf.some((v) => matches(value, v))) return false
  if (rule.type === 'null') return value === null
  if (rule.type === 'boolean') return typeof value === 'boolean'
  if (rule.type === 'string')
    return (
      typeof value === 'string' &&
      (rule.minLength === undefined || value.length >= rule.minLength) &&
      (rule.maxLength === undefined || value.length <= rule.maxLength) &&
      (rule.pattern === undefined ||
        new RegExp(rule.pattern).exec(value)?.[0] === value) &&
      value.trim() === value
    )
  if (rule.type === 'array')
    return (
      Array.isArray(value) &&
      (rule.minItems === undefined || value.length >= rule.minItems) &&
      (rule.maxItems === undefined || value.length <= rule.maxItems) &&
      (!rule.items || value.every((v) => matches(v, rule.items!)))
    )
  if (rule.type === 'object') {
    if (value === null || typeof value !== 'object' || Array.isArray(value))
      return false
    const row = value as Record<string, unknown>,
      properties = rule.properties ?? {}
    return (
      (rule.required ?? []).every((k) => Object.hasOwn(row, k)) &&
      Object.entries(row).every(([k, v]) =>
        Object.hasOwn(properties, k)
          ? matches(v, properties[k]!)
          : rule.additionalProperties !== false,
      )
    )
  }
  return true
}
/** 正式schemaの名前付き構造だけを検証し、unknown定義は拒否する。 */
export function isPlayDefinition<T>(value: unknown, name: string): value is T {
  return Object.hasOwn(definitions, name) && matches(value, definitions[name]!)
}
/** hash対象はJSONの正準値だけ。getter/非有限値/非plain値を通さない。 */
export function canonicalPlayJson(value: unknown): string {
  const encode = (v: unknown): unknown => {
    if (v === null || typeof v === 'boolean' || typeof v === 'string') return v
    if (typeof v === 'number' && Number.isFinite(v) && !Object.is(v, -0))
      return v
    if (Array.isArray(v)) {
      if (
        Object.keys(v).length !== v.length ||
        Object.getOwnPropertySymbols(v).length ||
        Array.from({ length: v.length }, (_, i) => String(i)).some(
          (k) => !Object.hasOwn(v, k),
        )
      )
        throw new Error('記録の正準値を確認できません')
      return v.map(encode)
    }
    if (
      typeof v !== 'object' ||
      v === null ||
      Object.getPrototypeOf(v) !== Object.prototype ||
      Object.getOwnPropertySymbols(v).length
    )
      throw new Error('記録の正準値を確認できません')
    const out: Record<string, unknown> = {}
    for (const k of Object.keys(v).sort()) {
      const p = Object.getOwnPropertyDescriptor(v, k)
      if (!p || !Object.hasOwn(p, 'value') || !p.enumerable)
        throw new Error('記録の正準値を確認できません')
      Object.defineProperty(out, k, {
        value: encode(p.value),
        enumerable: true,
      })
    }
    return out
  }
  return JSON.stringify(encode(value))
}
export async function playHash(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalPlayJson(value))
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest), (b) =>
    b.toString(16).padStart(2, '0'),
  ).join('')
}
/** 自己digest二欄だけを除く、サーバーと同じ選択fieldのW。 */
export function playWireHead(q: PlayRequest, response: PlaySuccess) {
  const r = response.value,
    ref = r.nextPrefixRef,
    source = q.source
  if (
    !isPlayDefinition<PlayRequest>(q, 'PlayRequest') ||
    !isPlayDefinition<PlaySuccess>(response, 'PlaySuccess') ||
    !sameOrdinaryWire(r.previousPrefixRef, q.prefixRef) ||
    !sameOrdinaryWire(r.playIdentity, q.playIdentity) ||
    !sameOrdinaryWire(r.sourcePosition, source.position) ||
    ref.checkpoint.id !== q.nextCheckpoint.id ||
    ref.checkpoint.revision !== q.nextCheckpoint.revision ||
    r.executionArtifactSha256 !== source.executionArtifactSha256
  )
    throw new Error('投球の実応答を確認できません')
  return {
    formatVersion: 'play-prefix-wire-head-v2',
    version: ref.version,
    scope: ref.scope,
    tenantId: ref.tenantId,
    gameId: ref.gameId,
    generation: ref.generation,
    length: ref.length,
    checkpointId: ref.checkpoint.id,
    checkpointRevision: ref.checkpoint.revision,
    historyVersion: ref.historyVersion,
    origin: ref.origin,
    previousPrefixRef: q.prefixRef,
    rules: q.rules,
    rulesDigest: source.rulesDigest,
    layoutDigest: source.layoutDigest,
    priorArtifactSha256: source.priorArtifactSha256,
    executionArtifactSha256: source.executionArtifactSha256,
    sourcePosition: source.position,
    playIdentity: q.playIdentity,
    responsibility: source.responsibility,
    before: q.t1.before,
    T1: r.t1,
    T2: r.t2,
    newHistoryEntry: r.newHistoryEntry,
    runners: r.runners,
    participants: r.participants,
  }
}
export async function sealPlayMetadata(
  request: PlayRequest,
  response: PlaySuccess,
): Promise<{ request: PlayRequest; response: PlaySuccess }> {
  const digest = await playHash(playWireHead(request, response))
  return {
    request: {
      ...structuredClone(request),
      nextCheckpoint: { ...request.nextCheckpoint, digest },
    },
    response: {
      ok: true,
      value: {
        ...structuredClone(response.value),
        nextPrefixRef: {
          ...response.value.nextPrefixRef,
          checkpoint: { ...response.value.nextPrefixRef.checkpoint, digest },
        },
      },
    },
  }
}
function observationsValid(v: Observations): boolean {
  return (
    isPlayDefinition(v, 'PayloadObservations') &&
    [v.course.x, v.course.y].every(
      (x) => /^(0|[1-9][0-9]*)$/.test(x) && x.trim() === x && BigInt(x) <= 263n,
    ) &&
    (v.pitchSpeed.kmh === null
      ? v.pitchSpeed.outsideRangeConfirmed === false
      : /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(v.pitchSpeed.kmh) &&
        v.pitchSpeed.kmh.trim() === v.pitchSpeed.kmh)
  )
}
export async function formatTerminalPitchWire(
  request: PlayRequest,
  response: PlaySuccess,
  observations: Observations,
  participants: Participants,
): Promise<{ payload: PlayPrefixV7; stateDiff: PlayPrefixV8 }> {
  const digest = await playHash(playWireHead(request, response))
  const payload: PlayPrefixV7 = {
    formatVersion: 'play-prefix-play-v2',
    observations,
    participants,
    calculation: {
      formatVersion: 'play-prefix-calculation-v2',
      artifactSha256: identity.sha256,
      request,
      response,
    },
  }
  if (
    !matches(payload, schema as Schema) ||
    !observationsValid(observations) ||
    request.nextCheckpoint.digest !== digest ||
    response.value.nextPrefixRef.checkpoint.digest !== digest ||
    request.source.executionArtifactSha256 !== identity.sha256 ||
    participants.battingOrder !==
      request.t1.before.stateFields['state.battingOrder'] ||
    !sameOrdinaryWire(
      {
        batterId: participants.batterId,
        pitcherId: participants.pitcherId,
        battingOrder: participants.battingOrder,
      },
      request.source.participants,
    )
  )
    throw new Error('投球の保存値を確認できません')
  return structuredClone({
    payload,
    stateDiff: response.value.newHistoryEntry.difference,
  })
}
