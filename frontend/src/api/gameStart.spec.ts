import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../lib/queryClient'
import { useAuthStore } from '../stores/authStore'
import { setVerifiedAuthForTest } from './auth.test-support'
import {
  GameStartDataError,
  parseDeviceEnrollmentResponse,
  parseGameStartOwner,
  parseGameStartRequest,
  parseInitialGameStartResponse,
  enrollInitialDevice,
  startInitialGame,
  resolveInitialGameStart,
} from './gameStart'

const tenant = '10000000-0000-4000-8000-000000000001'
const game = '10000000-0000-4000-8000-000000000002'
const requestId = '10000000-0000-4000-8000-000000000003'
const device = '10000000-0000-4000-8000-000000000004'
const other = '20000000-0000-4000-8000-000000000001'
const credential = 'public-test-device-credential'
const proof = 'public-test-recording-proof'
const owner = {
  tenant_id: tenant,
  game_id: game,
  start_request_id: requestId,
  device_id: device,
}

describe('開始の実HTTP client境界', () => {
  let pinia: Pinia
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    localStorage.clear()
    setVerifiedAuthForTest(useAuthStore(pinia), {
      teamName: '試験',
      teamId: tenant,
    })
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    disposePinia(pinia)
    queryClient.clear()
  })

  function reply(value: unknown, status = 200, matched = true) {
    vi.mocked(fetch).mockImplementation(async (_url, init) => {
      const headers = new Headers(init?.headers)
      return new Response(JSON.stringify(value), {
        status,
        headers: {
          'Content-Type': 'application/json',
          ...(matched
            ? {
                'X-Pitchlog-Tenant-Match': '1',
                'X-Pitchlog-Tenant-Challenge': headers.get(
                  'X-Pitchlog-Tenant-Challenge',
                )!,
              }
            : {}),
        },
      })
    })
  }

  async function rejected(promise: Promise<unknown>) {
    const error: unknown = await promise.catch((value: unknown) => value)
    expect(error).toBeInstanceOf(GameStartDataError)
    expect(String(error)).toBe('GameStartDataError: 開始データを確認できません')
    expect(error).not.toHaveProperty('cause')
    expect(JSON.stringify(error)).not.toContain(credential)
    expect(JSON.stringify(error)).not.toContain(proof)
  }

  it('実clientのC2/Cookie/state headerを通し、enrollに資格本文を送らない', async () => {
    const value = {
      tenant_id: tenant,
      device_id: device,
      device_credential: credential,
    }
    reply(value)
    expect(await enrollInitialDevice(tenant)).toEqual(value)
    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, init] = vi.mocked(fetch).mock.calls[0]!
    expect(url).toBe('/api/devices/enroll')
    expect(init?.method).toBe('POST')
    expect(init?.credentials).toBe('include')
    expect(init?.cache).toBe('no-store')
    expect(init?.body).toBeUndefined()
    const headers = new Headers(init?.headers)
    expect(headers.get('X-Pitchlog-Request')).toBe('1')
    expect(headers.get('X-Pitchlog-Expected-Tenant')).toBe(tenant)
    expect(headers.get('X-Pitchlog-Tenant-Challenge')).toMatch(
      /^[0-9a-f-]{36}$/,
    )
    expect(headers.get('Content-Type')).toBeNull()
  })

  it.each([false, true])(
    'start/resolve(%s)は同owner/全payloadを一回送る',
    async (resolve) => {
      reply(response())
      const signal = new AbortController().signal
      const input = request()
      const send = resolve ? resolveInitialGameStart : startInitialGame
      expect(await send(owner, input, signal)).toEqual(response())
      expect(fetch).toHaveBeenCalledTimes(1)
      const [url, init] = vi.mocked(fetch).mock.calls[0]!
      expect(url).toBe(`/api/games/${game}/start${resolve ? '/resolve' : ''}`)
      expect(JSON.parse(init?.body as string)).toEqual(input)
      expect(Object.keys(JSON.parse(init?.body as string))).toHaveLength(5)
      expect(init?.signal).toBe(signal)
      expect(new Headers(init?.headers).get('X-Pitchlog-Expected-Tenant')).toBe(
        tenant,
      )
    },
  )

  it('要求は送信前にsnapshot化され後発入力変更を混入させない', async () => {
    reply(response())
    const input = request()
    const pending = startInitialGame(owner, input)
    input.away[0]!.player_id = other
    input.device_credential = 'changed'
    expect(await pending).toEqual(response())
    const sent = JSON.parse(vi.mocked(fetch).mock.calls[0]![1]?.body as string)
    expect(sent).toEqual(request())
  })

  it.each(['tenant', 'game', 'request', 'device', 'input-extra'])(
    '送信前の%s不一致をHTTP0で拒否',
    async (kind) => {
      const expected = { ...owner }
      const input = request()
      if (kind === 'tenant') expected.tenant_id = other
      if (kind === 'game') expected.game_id = '../not-a-game'
      if (kind === 'request') expected.start_request_id = other
      if (kind === 'device') expected.device_id = other
      if (kind === 'input-extra')
        Object.assign(input, { tenant_id: credential })
      await rejected(startInitialGame(expected, input))
      expect(fetch).not.toHaveBeenCalled()
    },
  )

  it.each(['owner', 'shape', 'tenant-ack', 'non-json', 'http503', 'network'])(
    '輸送/応答%sの不正を秘密なしの不明へ閉じ自動再送しない',
    async (fault) => {
      if (fault === 'owner') reply({ ...response(), game_id: other })
      if (fault === 'shape') reply({ ...response(), unknown: credential })
      if (fault === 'tenant-ack') reply(response(), 200, false)
      if (fault === 'non-json')
        vi.mocked(fetch).mockResolvedValue(new Response(credential))
      if (fault === 'http503')
        reply({ error: { message: credential, details: proof } }, 503)
      if (fault === 'network')
        vi.mocked(fetch).mockRejectedValue(new Error(credential))
      await rejected(resolveInitialGameStart(owner, request()))
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )

  it('enrollの別tenant応答と送信前別tenantを採らない', async () => {
    reply({
      tenant_id: other,
      device_id: device,
      device_credential: credential,
    })
    await rejected(enrollInitialDevice(tenant))
    expect(fetch).toHaveBeenCalledTimes(1)
    vi.mocked(fetch).mockClear()
    await rejected(enrollInitialDevice(other))
    expect(fetch).not.toHaveBeenCalled()
  })

  it('要求中の認証世代変更では応答を採用しない', async () => {
    let done!: (value: Response) => void
    vi.mocked(fetch).mockReturnValue(
      new Promise((resolve) => {
        done = resolve
      }),
    )
    const pending = startInitialGame(owner, request())
    const headers = new Headers(vi.mocked(fetch).mock.calls[0]![1]?.headers)
    setVerifiedAuthForTest(useAuthStore(pinia), {
      teamName: '別',
      teamId: other,
    })
    done(
      new Response(JSON.stringify(response()), {
        headers: {
          'Content-Type': 'application/json',
          'X-Pitchlog-Tenant-Match': '1',
          'X-Pitchlog-Tenant-Challenge': headers.get(
            'X-Pitchlog-Tenant-Challenge',
          )!,
        },
      }),
    )
    await rejected(pending)
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})

function request() {
  const rows = Array.from({ length: 9 }, (_, index) => ({
    player_id: `30000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
    batting_order: index + 1,
    fielding_position: { selected: index + 1, details: [null, true, 'P'] },
  }))
  return {
    start_request_id: requestId,
    device_id: device,
    device_credential: credential,
    away: rows,
    home: structuredClone(rows),
  }
}
function response() {
  return {
    ...owner,
    d4: 'opaque-reference',
    recovery_generation: '9223372036854775807',
    recording_right_proof: proof,
    started_at: '2026-10-26T12:34:56.123456+09:00',
    away_lineup_id: other,
    home_lineup_id: game,
  }
}
function fails(action: () => unknown) {
  let caught: unknown
  try {
    action()
  } catch (error) {
    caught = error
  }
  expect(caught).toBeInstanceOf(GameStartDataError)
  expect(String(caught)).toBe('GameStartDataError: 開始データを確認できません')
  expect(JSON.stringify(caught)).not.toContain(credential)
  expect(JSON.stringify(caught)).not.toContain(proof)
  expect(caught).not.toHaveProperty('cause')
}

describe('開始通信の外形とowner', () => {
  it('exact5/3を複製して不変化し、名簿の意味検証は追加しない', () => {
    const input = request()
    const result = parseGameStartRequest(input)
    expect(result).toEqual(input)
    expect(Object.keys(result)).toHaveLength(5)
    expect(Object.keys(result.away[0]!)).toHaveLength(3)
    expect(Object.isFrozen(result)).toBe(true)
    expect(Object.isFrozen(result.away)).toBe(true)
    expect(Object.isFrozen(result.away[0]?.fielding_position)).toBe(true)
    input.away[0]!.fielding_position.details[2] = 'changed'
    expect(result.away[0]?.fielding_position).toEqual({
      selected: 1,
      details: [null, true, 'P'],
    })
    const duplicate = request()
    duplicate.away[1]!.player_id = duplicate.away[0]!.player_id
    expect(parseGameStartRequest(duplicate).away[1]?.player_id).toBe(
      duplicate.away[0]!.player_id,
    )
  })
  it('10枠/null打順は外形として受け、DH判定をしない', () => {
    const input: Record<string, unknown> = request()
    const rows = request().away as unknown[]
    rows.push({
      player_id: other,
      batting_order: null,
      fielding_position: null,
    })
    input.away = rows
    expect(parseGameStartRequest(input).away).toHaveLength(10)
    expect(parseGameStartRequest(input).away[9]?.batting_order).toBeNull()
  })
  it.each(['tenant_id', 'game_id', 'started_at', 'd4', 'unknown'])(
    '要求extra %sを拒否',
    (key) => {
      fails(() => parseGameStartRequest({ ...request(), [key]: credential }))
    },
  )
  it.each([
    'start_request_id',
    'device_id',
    'device_credential',
    'away',
    'home',
  ])('要求欠落 %sを拒否', (key) => {
    const input: Record<string, unknown> = request()
    delete input[key]
    fails(() => parseGameStartRequest(input))
  })
  it.each([null, true, 1, '', other + '\n', 'not-uuid'])(
    'UUID不正 %jを変換しない',
    (id) => {
      fails(() => parseGameStartRequest({ ...request(), start_request_id: id }))
    },
  )
  it.each([true, '1', 0, 10, 1.5, Infinity, undefined])(
    'StrictInt不正 %jを拒否',
    (order) => {
      const input = request()
      Object.assign(input.away[0]!, { batting_order: order })
      fails(() => parseGameStartRequest(input))
    },
  )
  it.each([8, 11])('不正枠数 %iを拒否', (length) => {
    const input = request()
    fails(() =>
      parseGameStartRequest({
        ...input,
        away: Array.from({ length }, () => input.away[0]),
      }),
    )
  })
  it.each([
    undefined,
    () => null,
    Symbol('invalid'),
    1n,
    NaN,
    Infinity,
    new Date(),
  ])('非JSON表現を拒否', (position) => {
    const input = request()
    Object.assign(input.away[0]!, { fielding_position: position })
    fails(() => parseGameStartRequest(input))
  })
  it('循環/sparse/隠しfieldを拒否し、getterを実行しない', () => {
    const circular: Record<string, unknown> = {}
    circular.self = circular
    const input = request()
    Object.assign(input.away[0]!, { fielding_position: circular })
    fails(() => parseGameStartRequest(input))
    const sparse = request().away
    delete sparse[0]
    fails(() => parseGameStartRequest({ ...request(), away: sparse }))
    let accessed = false
    const accessor = Object.defineProperty({}, 'start_request_id', {
      enumerable: true,
      get() {
        accessed = true
        throw new Error(credential)
      },
    })
    fails(() => parseGameStartRequest(accessor))
    expect(accessed).toBe(false)
    const hidden = request()
    Object.defineProperty(hidden, 'extra', { value: credential })
    fails(() => parseGameStartRequest(hidden))
  })
  it('JSONの__proto__を値として複製しprototypeを変えない', () => {
    const input = request()
    Object.assign(input.away[0]!, {
      fielding_position: JSON.parse('{"__proto__":{"polluted":true}}'),
    })
    const parsed = parseGameStartRequest(input).away[0]!
      .fielding_position as object
    expect(Object.hasOwn(parsed, '__proto__')).toBe(true)
    expect(Object.getPrototypeOf(parsed)).toBeNull()
    expect(Object.hasOwn(Object.prototype, 'polluted')).toBe(false)
  })
  it('enrollのtenant一致/extra/空資格を検査', () => {
    const enrolled = {
      tenant_id: tenant,
      device_id: device,
      device_credential: credential,
    }
    expect(parseDeviceEnrollmentResponse(enrolled, tenant)).toEqual(enrolled)
    fails(() => parseDeviceEnrollmentResponse(enrolled, other))
    fails(() =>
      parseDeviceEnrollmentResponse({ ...enrolled, extra: true }, tenant),
    )
    fails(() =>
      parseDeviceEnrollmentResponse(
        { ...enrolled, device_credential: '' },
        tenant,
      ),
    )
  })
  it('開始応答exact10と元のopaque文字列を保持', () => {
    const input = response()
    const result = parseInitialGameStartResponse(input, owner)
    expect(result).toEqual(input)
    expect(Object.keys(result)).toHaveLength(10)
    expect(result.recovery_generation).toBe('9223372036854775807')
    expect(Object.isFrozen(result)).toBe(true)
  })
  it.each(['tenant_id', 'game_id', 'start_request_id', 'device_id'] as const)(
    'owner %s不一致を拒否',
    (key) => {
      fails(() =>
        parseInitialGameStartResponse({ ...response(), [key]: other }, owner),
      )
    },
  )
  it('期待ownerのextraも拒否', () => {
    fails(() => parseGameStartOwner({ ...owner, extra: true }))
    fails(() =>
      parseInitialGameStartResponse(response(), {
        ...owner,
        extra: true,
      } as typeof owner),
    )
  })
  it.each([
    '0',
    '01',
    '+1',
    '1\n',
    '1e0',
    ' 1',
    '１',
    '9223372036854775808',
    '99999999999999999999',
    '',
    1,
    true,
  ])('不正epoch %jを拒否', (epoch) => {
    fails(() =>
      parseInitialGameStartResponse(
        { ...response(), recovery_generation: epoch },
        owner,
      ),
    )
  })
  it.each([
    '2026-02-30T00:00:00Z',
    '2026-02-29T00:00:00Z',
    '2026-01-01T00:00:00',
    '2026-01-01T24:00:00Z',
    '2026-01-01T00:00:60Z',
    '2026-01-01T00:00:00+25:00',
    '0000-01-01T00:00:00Z',
    '2026-01-01T00:00:00Z\n',
    1,
  ])('不正日時 %jを拒否', (stamp) => {
    fails(() =>
      parseInitialGameStartResponse(
        { ...response(), started_at: stamp },
        owner,
      ),
    )
  })
  it('有効な閏日/UTCを保持', () => {
    expect(
      parseInitialGameStartResponse(
        { ...response(), started_at: '2024-02-29T00:00:00Z' },
        owner,
      ).started_at,
    ).toBe('2024-02-29T00:00:00Z')
  })
  it.each(['', 'x'.repeat(4097), null, 1])(
    '空/過大/異型資格を拒否',
    (value) => {
      fails(() =>
        parseDeviceEnrollmentResponse(
          { tenant_id: tenant, device_id: device, device_credential: value },
          tenant,
        ),
      )
      fails(() =>
        parseInitialGameStartResponse(
          { ...response(), recording_right_proof: value },
          owner,
        ),
      )
    },
  )
  it('不正応答/任意throwへ資格を残さない', () => {
    fails(() =>
      parseInitialGameStartResponse({ ...response(), extra: proof }, owner),
    )
    fails(() =>
      parseInitialGameStartResponse(
        { ...response(), d4: 'x'.repeat(129) },
        owner,
      ),
    )
    const hostile = new Proxy(
      {},
      {
        getPrototypeOf() {
          throw new Error(credential + proof)
        },
      },
    )
    fails(() => parseGameStartRequest(hostile))
  })
})

describe('検証済みdescriptorのsnapshot境界', () => {
  it('lineup配列Proxyのmapを呼ばず検証した9行だけを返す', () => {
    let calls = 0
    const rows = new Proxy(request().away, {
      get(target, key, receiver) {
        if (key === 'map')
          return () => {
            calls += 1
            return [{ unexpected: true }]
          }
        return Reflect.get(target, key, receiver)
      },
    })
    const result = parseGameStartRequest({ ...request(), away: rows })
    expect(calls).toBe(0)
    expect(result.away).toHaveLength(9)
    expect(result.away[0]?.player_id).toBe(request().away[0]!.player_id)
  })
  it('応答Proxyの再読取によるd4異型差替えを実行しない', () => {
    let reads = 0
    const value = new Proxy(response(), {
      get(target, key, receiver) {
        if (key === 'd4') {
          reads += 1
          return reads >= 4 ? 17 : 'opaque-reference'
        }
        return Reflect.get(target, key, receiver)
      },
    })
    expect(parseInitialGameStartResponse(value, owner).d4).toBe(
      'opaque-reference',
    )
    expect(reads).toBe(0)
  })
  it('nested JsonValueのrecord/arrayも元getやmapを呼ばず複製する', () => {
    let reads = 0
    const nested = new Proxy(
      { selected: 'P' },
      {
        get() {
          reads += 1
          return Infinity
        },
      },
    )
    const array = new Proxy([nested], {
      get(target, key, receiver) {
        if (key === 'map' || key === Symbol.iterator) {
          reads += 1
          throw new Error(credential)
        }
        return Reflect.get(target, key, receiver)
      },
    })
    const input = request()
    Object.assign(input.away[0]!, { fielding_position: array })
    expect(parseGameStartRequest(input).away[0]?.fielding_position).toEqual([
      { selected: 'P' },
    ])
    expect(reads).toBe(0)
  })
  it('descriptor自体が不正な値ならsnapshotでも拒否する', () => {
    const value = new Proxy(response(), {
      getOwnPropertyDescriptor(target, key) {
        const descriptor = Reflect.getOwnPropertyDescriptor(target, key)
        return key === 'd4' ? { ...descriptor, value: 17 } : descriptor
      },
    })
    fails(() => parseInitialGameStartResponse(value, owner))
  })
})
