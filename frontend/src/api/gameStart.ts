import { getActivePinia } from 'pinia'
import { useAuthStore } from '../stores/authStore'
import { apiRequest } from './client'

/** 開始通信の外形だけを検査する。認可・開始確定・記録権を判定しない。 */
export type GameStartJson =
  | null
  | boolean
  | number
  | string
  | readonly GameStartJson[]
  | { readonly [key: string]: GameStartJson }

export interface StartLineupInput {
  readonly player_id: string
  readonly batting_order: number | null
  readonly fielding_position: GameStartJson
}

export interface GameStartRequest {
  readonly start_request_id: string
  readonly device_id: string
  readonly device_credential: string
  readonly away: readonly StartLineupInput[]
  readonly home: readonly StartLineupInput[]
}

export interface GameStartOwner {
  readonly tenant_id: string
  readonly game_id: string
  readonly start_request_id: string
  readonly device_id: string
}

export interface InitialDeviceEnrollmentResponse {
  readonly tenant_id: string
  readonly device_id: string
  readonly device_credential: string
}

export interface InitialGameStartResponse extends GameStartOwner {
  readonly d4: string
  readonly recovery_generation: string
  readonly recording_right_proof: string
  readonly started_at: string
  readonly away_lineup_id: string
  readonly home_lineup_id: string
}

/** 提示資格・原応答・元例外を保持しない外形エラー。 */
export class GameStartDataError extends Error {
  constructor() {
    super('開始データを確認できません')
    this.name = 'GameStartDataError'
  }
}

function invalid(): never {
  throw new GameStartDataError()
}

function dataRecord(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null) return invalid()
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) return invalid()
  const descriptors = Object.getOwnPropertyDescriptors(value)
  if (Object.getOwnPropertySymbols(descriptors).length !== 0) return invalid()
  const snapshot: Record<string, unknown> = Object.create(null) as Record<
    string,
    unknown
  >
  for (const key of Object.keys(descriptors)) {
    const descriptor = descriptors[key]!
    if (!Object.hasOwn(descriptor, 'value') || !descriptor.enumerable)
      return invalid()
    snapshot[key] = descriptor.value
  }
  // 検査後に元objectを再読取しない。Proxy/getterによる値の差替えを防ぐ。
  return Object.freeze(snapshot)
}

function exactRecord(
  value: unknown,
  fields: readonly string[],
): Record<string, unknown> {
  const record = dataRecord(value)
  const keys = Object.keys(record)
  if (
    keys.length !== fields.length ||
    keys.some((key) => !fields.includes(key))
  ) {
    return invalid()
  }
  return record
}

function uuid(value: unknown): string {
  // 実通信codecと同じcanonical UUID。UUIDの外形を認可証明にはしない。
  if (
    typeof value !== 'string' ||
    value.length !== 36 ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      value,
    )
  )
    return invalid()
  return value
}

function secret(value: unknown): string {
  if (typeof value !== 'string' || value.length === 0 || value.length > 4096)
    return invalid()
  return value
}

function arrayValues(value: unknown): readonly unknown[] {
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype)
    return invalid()
  const descriptors = Object.getOwnPropertyDescriptors(value as object)
  if (Object.getOwnPropertySymbols(descriptors).length !== 0) return invalid()
  const lengthDescriptor = descriptors.length
  if (
    lengthDescriptor === undefined ||
    !Object.hasOwn(lengthDescriptor, 'value')
  )
    return invalid()
  const length: unknown = lengthDescriptor.value
  if (typeof length !== 'number' || !Number.isSafeInteger(length) || length < 0)
    return invalid()
  const keys = Object.keys(descriptors).filter((key) => key !== 'length')
  if (
    keys.length !== length ||
    keys.some((key, index) => key !== String(index))
  )
    return invalid()
  const snapshot: unknown[] = []
  for (const key of keys) {
    const descriptor = descriptors[key]!
    if (!Object.hasOwn(descriptor, 'value') || !descriptor.enumerable)
      return invalid()
    snapshot.push(descriptor.value)
  }
  return Object.freeze(snapshot)
}

/** JSON値を防御的に複製する。名簿の意味や守備位置の採否は検証しない。 */
function copyJson(
  value: unknown,
  ancestors = new Set<object>(),
): GameStartJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean')
    return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return invalid()
    return value
  }
  if (typeof value !== 'object' || ancestors.has(value)) return invalid()
  ancestors.add(value)
  try {
    if (Array.isArray(value)) {
      return Object.freeze(
        arrayValues(value).map((entry) => copyJson(entry, ancestors)),
      )
    }
    const source = dataRecord(value)
    const result: Record<string, GameStartJson> = Object.create(null) as Record<
      string,
      GameStartJson
    >
    for (const key of Object.keys(source))
      result[key] = copyJson(source[key], ancestors)
    return Object.freeze(result)
  } finally {
    ancestors.delete(value)
  }
}

function lineup(value: unknown): readonly StartLineupInput[] {
  const rows = arrayValues(value)
  if (rows.length !== 9 && rows.length !== 10) return invalid()
  return Object.freeze(
    rows.map((entry) => {
      const row = exactRecord(entry, [
        'player_id',
        'batting_order',
        'fielding_position',
      ])
      const order = row.batting_order
      if (
        order !== null &&
        (typeof order !== 'number' ||
          !Number.isInteger(order) ||
          order < 1 ||
          order > 9)
      ) {
        return invalid()
      }
      return Object.freeze({
        player_id: uuid(row.player_id),
        batting_order: order,
        fielding_position: copyJson(row.fielding_position),
      })
    }),
  )
}

/** 不正objectのgetter等が投げても原例外を利用者側へ連結しない。 */
function safe<T>(parse: () => T): T {
  try {
    return parse()
  } catch {
    throw new GameStartDataError()
  }
}

export function parseGameStartRequest(value: unknown): GameStartRequest {
  return safe(() => {
    const row = exactRecord(value, [
      'start_request_id',
      'device_id',
      'device_credential',
      'away',
      'home',
    ])
    return Object.freeze({
      start_request_id: uuid(row.start_request_id),
      device_id: uuid(row.device_id),
      device_credential: secret(row.device_credential),
      away: lineup(row.away),
      home: lineup(row.home),
    })
  })
}

export function parseGameStartOwner(value: unknown): GameStartOwner {
  return safe(() => {
    const row = exactRecord(value, [
      'tenant_id',
      'game_id',
      'start_request_id',
      'device_id',
    ])
    return Object.freeze({
      tenant_id: uuid(row.tenant_id),
      game_id: uuid(row.game_id),
      start_request_id: uuid(row.start_request_id),
      device_id: uuid(row.device_id),
    })
  })
}

export function parseDeviceEnrollmentResponse(
  value: unknown,
  expectedTenant: string,
): InitialDeviceEnrollmentResponse {
  return safe(() => {
    const row = exactRecord(value, [
      'tenant_id',
      'device_id',
      'device_credential',
    ])
    const tenant = uuid(row.tenant_id)
    if (tenant !== uuid(expectedTenant)) return invalid()
    return Object.freeze({
      tenant_id: tenant,
      device_id: uuid(row.device_id),
      device_credential: secret(row.device_credential),
    })
  })
}

function recoveryGeneration(value: unknown): string {
  if (
    typeof value !== 'string' ||
    value.length === 0 ||
    value.length > 19 ||
    value[0] === '0' ||
    [...value].some((character) => character < '0' || character > '9') ||
    BigInt(value) > 9223372036854775807n
  )
    return invalid()
  return value
}

function awareTimestamp(value: unknown): string {
  if (typeof value !== 'string') return invalid()
  const match =
    /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$/.exec(
      value,
    )
  if (match === null || match[0].length !== value.length) return invalid()
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const days = [
    31,
    year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28,
    31,
    30,
    31,
    30,
    31,
    31,
    30,
    31,
    30,
    31,
  ]
  const maximum = days[month - 1]
  const offset = match[7]
  if (
    year < 1 ||
    maximum === undefined ||
    day < 1 ||
    day > maximum ||
    Number(match[4]) > 23 ||
    Number(match[5]) > 59 ||
    Number(match[6]) > 59 ||
    offset === undefined ||
    (offset !== 'Z' &&
      (Number(offset.slice(1, 3)) > 23 || Number(offset.slice(4)) > 59)) ||
    !Number.isFinite(Date.parse(value))
  )
    return invalid()
  return value
}

/** 実応答の外形と期待ownerを照合する。呼出しだけで開始成功にはしない。 */
export function parseInitialGameStartResponse(
  value: unknown,
  expectedOwner: GameStartOwner,
): InitialGameStartResponse {
  return safe(() => {
    const row = exactRecord(value, [
      'tenant_id',
      'game_id',
      'start_request_id',
      'device_id',
      'd4',
      'recovery_generation',
      'recording_right_proof',
      'started_at',
      'away_lineup_id',
      'home_lineup_id',
    ])
    const expected = parseGameStartOwner(expectedOwner)
    for (const key of [
      'tenant_id',
      'game_id',
      'start_request_id',
      'device_id',
    ] as const) {
      if (uuid(row[key]) !== expected[key]) return invalid()
    }
    if (
      typeof row.d4 !== 'string' ||
      row.d4.length === 0 ||
      row.d4.length > 128
    )
      return invalid()
    return Object.freeze({
      ...expected,
      d4: row.d4,
      recovery_generation: recoveryGeneration(row.recovery_generation),
      recording_right_proof: secret(row.recording_right_proof),
      started_at: awareTimestamp(row.started_at),
      away_lineup_id: uuid(row.away_lineup_id),
      home_lineup_id: uuid(row.home_lineup_id),
    })
  })
}

/** C2と認証世代に束縛した一回の輸送。原例外・資格を公開エラーへ残さない。 */
async function scopedRequest<T>(
  expectedTenant: string,
  send: () => Promise<unknown>,
  decode: (value: unknown) => T,
): Promise<T> {
  try {
    const tenant = uuid(expectedTenant)
    const pinia = getActivePinia()
    if (!pinia) return invalid()
    const auth = useAuthStore(pinia)
    auth.syncFromStorage()
    const epoch = auth.authEpoch
    const assertCurrent = () => {
      if (
        getActivePinia() !== pinia ||
        !auth.hasHydrated ||
        !auth.isAuthenticated ||
        auth.teamId !== tenant ||
        auth.authEpoch !== epoch
      )
        invalid()
    }
    assertCurrent()
    const value = await send()
    assertCurrent()
    const result = decode(value)
    assertCurrent()
    return result
  } catch {
    throw new GameStartDataError()
  }
}

/** 応答を受けても、呼出し側が端末資格を耐久保存するまでは開始に使わない。 */
export async function enrollInitialDevice(
  expectedTenant: string,
  signal?: AbortSignal,
): Promise<InitialDeviceEnrollmentResponse> {
  return scopedRequest(
    expectedTenant,
    () =>
      apiRequest<unknown>('POST', '/devices/enroll', {
        tenantBound: true,
        signal,
      }),
    (value) => parseDeviceEnrollmentResponse(value, expectedTenant),
  )
}

async function sendStart(
  ownerValue: GameStartOwner,
  requestValue: GameStartRequest,
  resolve: boolean,
  signal?: AbortSignal,
): Promise<InitialGameStartResponse> {
  try {
    const owner = parseGameStartOwner(ownerValue)
    const request = parseGameStartRequest(requestValue)
    if (
      owner.start_request_id !== request.start_request_id ||
      owner.device_id !== request.device_id
    )
      return invalid()
    return await scopedRequest(
      owner.tenant_id,
      () =>
        apiRequest<unknown>(
          'POST',
          `/games/${owner.game_id}/start${resolve ? '/resolve' : ''}`,
          { body: request, tenantBound: true, signal },
        ),
      (value) => parseInitialGameStartResponse(value, owner),
    )
  } catch {
    throw new GameStartDataError()
  }
}

/** 元要求を事前に耐久保存した呼出し側だけが明示的に開始を送る。自動再送しない。 */
export async function startInitialGame(
  owner: GameStartOwner,
  request: GameStartRequest,
  signal?: AbortSignal,
): Promise<InitialGameStartResponse> {
  return sendStart(owner, request, false, signal)
}

/** 保存した元要求を変更せず照会する。不明を取消・新要求可能へ変換しない。 */
export async function resolveInitialGameStart(
  owner: GameStartOwner,
  request: GameStartRequest,
  signal?: AbortSignal,
): Promise<InitialGameStartResponse> {
  return sendStart(owner, request, true, signal)
}
