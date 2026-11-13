import { apiRequest, type DeviceCredentials } from './client'
import { canonicalUuid } from './authIntent'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const D4 = /^d4\.1\.[A-Za-z0-9_-]{55}$/
const PROOF = /^[A-Za-z0-9_-]{43}$/
const POSITIVE = /^[1-9][0-9]*$/

export type HandoverRelease = Readonly<{
  tenant_id: string
  game_id: string
  handover_request_id: string
  from_device_id: string
  from_generation: string
  to_device_id: string
  last_d1: number
  released_at: string
}>

export type HandoverGrant = Readonly<{
  tenant_id: string
  game_id: string
  handover_request_id: string
  device_id: string
  d4: string
  recovery_generation: string
  recording_right_proof: string
}>

function invalid(): never {
  throw new Error('引き継ぎの応答を確認できません')
}

function record(
  value: unknown,
  keys: readonly string[],
): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    return invalid()
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) return invalid()
  const descriptors = Object.getOwnPropertyDescriptors(value)
  if (Object.getOwnPropertySymbols(descriptors).length !== 0) return invalid()
  const names = Object.keys(descriptors)
  if (
    names.length !== keys.length ||
    names.some((name) => !keys.includes(name))
  )
    return invalid()
  const snapshot: Record<string, unknown> = Object.create(null) as Record<
    string,
    unknown
  >
  for (const name of names) {
    const descriptor = descriptors[name]!
    if (!Object.hasOwn(descriptor, 'value') || !descriptor.enumerable)
      return invalid()
    snapshot[name] = descriptor.value
  }
  return snapshot
}

function uuid(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !UUID.test(value) ||
    !canonicalUuid.test(value)
  )
    return invalid()
  return value
}

function timestamp(value: unknown): string {
  if (typeof value !== 'string' || Number.isNaN(Date.parse(value)))
    return invalid()
  return value
}

function release(value: unknown): HandoverRelease {
  const row = record(value, [
    'tenant_id',
    'game_id',
    'handover_request_id',
    'from_device_id',
    'from_generation',
    'to_device_id',
    'last_d1',
    'released_at',
  ])
  if (
    typeof row.last_d1 !== 'number' ||
    !Number.isSafeInteger(row.last_d1) ||
    row.last_d1 < 0 ||
    typeof row.from_generation !== 'string' ||
    !POSITIVE.test(row.from_generation)
  )
    return invalid()
  return Object.freeze({
    tenant_id: uuid(row.tenant_id),
    game_id: uuid(row.game_id),
    handover_request_id: uuid(row.handover_request_id),
    from_device_id: uuid(row.from_device_id),
    from_generation: row.from_generation,
    to_device_id: uuid(row.to_device_id),
    last_d1: row.last_d1,
    released_at: timestamp(row.released_at),
  })
}

function grant(value: unknown): HandoverGrant {
  const row = record(value, [
    'tenant_id',
    'game_id',
    'handover_request_id',
    'device_id',
    'd4',
    'recovery_generation',
    'recording_right_proof',
  ])
  if (
    typeof row.d4 !== 'string' ||
    !D4.test(row.d4) ||
    typeof row.recovery_generation !== 'string' ||
    !POSITIVE.test(row.recovery_generation) ||
    typeof row.recording_right_proof !== 'string' ||
    !PROOF.test(row.recording_right_proof)
  )
    return invalid()
  return Object.freeze({
    tenant_id: uuid(row.tenant_id),
    game_id: uuid(row.game_id),
    handover_request_id: uuid(row.handover_request_id),
    device_id: uuid(row.device_id),
    d4: row.d4,
    recovery_generation: row.recovery_generation,
    recording_right_proof: row.recording_right_proof,
  })
}

/** 旧保持端末の明示解放を送る。新V12はこの応答に含まれない。 */
export async function releaseRecordingRightHandover(
  gameId: string,
  payload: Readonly<{
    handoverRequestId: string
    toDeviceId: string
    fromD4: string
    lastD1: number
    recordingRightProof: string
  }>,
  credentials: DeviceCredentials,
  signal?: AbortSignal,
): Promise<HandoverRelease> {
  if (
    !canonicalUuid.test(gameId) ||
    !canonicalUuid.test(payload.handoverRequestId) ||
    !canonicalUuid.test(payload.toDeviceId) ||
    !D4.test(payload.fromD4) ||
    !Number.isSafeInteger(payload.lastD1) ||
    payload.lastD1 < 0 ||
    !PROOF.test(payload.recordingRightProof)
  )
    throw new Error('引き継ぎの要求が正しくありません')
  return release(
    await apiRequest<unknown>(
      'POST',
      `/games/${encodeURIComponent(gameId)}/recording-right/handover/release`,
      {
        tenantBound: true,
        deviceCredentials: credentials,
        body: {
          handover_request_id: payload.handoverRequestId,
          to_device_id: payload.toDeviceId,
          from_d4: payload.fromD4,
          last_d1: payload.lastD1,
          recording_right_proof: payload.recordingRightProof,
          confirm_release: true,
        },
        signal,
      },
    ),
  )
}

/** 新保持端末が同じ要求の配達を受け、新世代の記録権値を得る。 */
export async function acquireRecordingRightHandover(
  gameId: string,
  handoverRequestId: string,
  credentials: DeviceCredentials,
  signal?: AbortSignal,
): Promise<HandoverGrant> {
  if (!canonicalUuid.test(gameId) || !canonicalUuid.test(handoverRequestId))
    throw new Error('引き継ぎの要求が正しくありません')
  return grant(
    await apiRequest<unknown>(
      'POST',
      `/games/${encodeURIComponent(gameId)}/recording-right/handover/acquire`,
      {
        tenantBound: true,
        deviceCredentials: credentials,
        body: { handover_request_id: handoverRequestId },
        signal,
      },
    ),
  )
}
