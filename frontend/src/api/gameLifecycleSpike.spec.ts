import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  endPayload,
  postGameLifecycle,
  readGameLifecycle,
  reopenPayload,
  type GameLifecycleRead,
} from './gameLifecycleSpike'
import { apiRequest } from './client'

vi.mock('./client', () => ({
  apiRequest: vi.fn(),
}))

const lifecycle: GameLifecycleRead = {
  gameId: '00000000-0000-4000-8000-000000000001',
  status: 'in_progress',
  generation: 1,
  d4: 'd4',
  watermark: 3,
  nextD1: 4,
  nextD2: 4001,
  truncated: false,
  stateDigest: 'sha256:state',
  currentState: {
    stateFields: {
      'state.half': 'top',
      'state.count.strikes': '0',
      'state.count.balls': '0',
      'state.outs': '0',
      'state.runners': 'empty',
      'state.battingOrder': '1',
      'state.tiebreakActive': false,
      'state.gameEnded': false,
      'state.inning': '1',
      'state.score': { home: '1', away: '0' },
    },
    scoreboard: {
      inningScores: { home: '1', away: '0' },
      hits: '1',
      errors: '0',
      strikeouts: '0',
      walks: '0',
    },
  },
  activeFinalization: null,
  nextFinalization: { version: 2, previous: { version: 1, d1: 2 } },
  finalizations: [
    {
      version: 1,
      d1: 2,
      d5: '00000000-0000-4000-8000-000000000002',
      state: {},
      stateDigest: 'sha256:old',
      finalizationDigest: 'sha256:old-final',
      invalidatedBy: { d1: 3, d5: '00000000-0000-4000-8000-000000000003' },
    },
  ],
  events: [],
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('game lifecycle payloads', () => {
  it('進行中は次の版と前版参照で終了payloadを作る', () => {
    expect(endPayload(lifecycle)).toEqual({
      formatVersion: 'game-lifecycle-spike-v1',
      action: 'end',
      finalization: {
        version: 2,
        previous: { version: 1, d1: 2 },
        state: lifecycle.currentState,
      },
    })
  })

  it('終了確定は有効版を失効対象にした再開payloadを作る', () => {
    const finished: GameLifecycleRead = {
      ...lifecycle,
      status: 'finished',
      activeFinalization: lifecycle.finalizations[0]!,
      nextFinalization: null,
    }
    expect(reopenPayload(finished)).toEqual({
      formatVersion: 'game-lifecycle-spike-v1',
      action: 'reopen',
      finalization: {
        version: 1,
        target: { version: 1, d1: 2 },
        state: lifecycle.currentState,
      },
    })
  })

  it('状態に合わない操作はpayloadを作らない', () => {
    expect(endPayload({ ...lifecycle, nextFinalization: null })).toBeNull()
    expect(reopenPayload(lifecycle)).toBeNull()
  })
})

describe('game lifecycle sync request', () => {
  it('正式wireのgame_end_declarationとして送る', async () => {
    const response = {
      advancedD3: 2,
      eventResults: [
        {
          d4: 'd4',
          d1: 4,
          d5: 'd5',
          a5Result: '受理',
        },
      ],
    }
    vi.mocked(apiRequest).mockResolvedValue(response)
    const payload = endPayload(lifecycle)!
    const result = await postGameLifecycle(lifecycle.gameId, {
      d4: lifecycle.d4,
      d1: lifecycle.nextD1,
      d2: lifecycle.nextD2,
      recordingRightProof: 'proof',
      payload,
      syncCredentials: {
        deviceId: 'device',
        deviceCredential: 'credential',
        attempt: 'attempt',
      },
    })
    expect(result).toEqual({ sent: true, a5Result: '受理', response })
    const call = vi.mocked(apiRequest).mock.calls.at(-1)
    expect(call).toBeDefined()
    const [method, path, options] = call!
    expect(method).toBe('POST')
    expect(path).toBe(`/games/${lifecycle.gameId}/sync/events`)
    const body = options?.body as {
      recording_right_proof: string
      events: Array<Record<string, unknown>>
    }
    expect(body.recording_right_proof).toBe('proof')
    expect(body.events).toHaveLength(1)
    expect(body.events[0]).toMatchObject({
      d1: 4,
      d4: 'd4',
      game_id: lifecycle.gameId,
      event_kind: 'game_end_declaration',
      d2: 4001,
      payload,
    })
    expect(options?.syncCredentials).toEqual({
      deviceId: 'device',
      deviceCredential: 'credential',
      attempt: 'attempt',
    })
  })

  it('ACKのa5が読めない応答を成功にしない', async () => {
    vi.mocked(apiRequest).mockResolvedValue({ eventResults: [] })
    const result = await postGameLifecycle(lifecycle.gameId, {
      d4: lifecycle.d4,
      d1: lifecycle.nextD1,
      d2: lifecycle.nextD2,
      recordingRightProof: 'proof',
      payload: endPayload(lifecycle)!,
      syncCredentials: {
        deviceId: 'device',
        deviceCredential: 'credential',
        attempt: 'attempt',
      },
    })
    expect(result).toEqual({ sent: false, reason: 'ack-shape' })
  })

  it('HTTP失敗を送信成功にしない', async () => {
    vi.mocked(apiRequest).mockRejectedValue(new Error('http'))
    const result = await postGameLifecycle(lifecycle.gameId, {
      d4: lifecycle.d4,
      d1: lifecycle.nextD1,
      d2: lifecycle.nextD2,
      recordingRightProof: 'proof',
      payload: endPayload(lifecycle)!,
      syncCredentials: {
        deviceId: 'device',
        deviceCredential: 'credential',
        attempt: 'attempt',
      },
    })
    expect(result).toEqual({ sent: false, reason: 'network-or-http' })
  })
})

describe('game lifecycle read', () => {
  it('tenant束縛のGETを使う', async () => {
    vi.mocked(apiRequest).mockResolvedValue(lifecycle)
    await expect(readGameLifecycle(lifecycle.gameId)).resolves.toBe(lifecycle)
    expect(apiRequest).toHaveBeenCalledWith(
      'GET',
      `/spike/games/${lifecycle.gameId}/lifecycle`,
      { tenantBound: true, signal: undefined },
    )
  })
})
