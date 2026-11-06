import 'fake-indexeddb/auto'

import { ApiTenantVerificationError } from './client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { useAuthStore } from '../stores/authStore'
import { setVerifiedAuthForTest } from './auth.test-support'
import { undoRead } from '../screens/GameScreenUndoProduct.test-support'
import {
  isSubstitutionPayload,
  postSubstitution,
  substitutionBody,
  substitutionEvent,
  type SubstitutionPayload,
} from './substitutionWire'

const game = undoRead()
const d5 = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const payload: SubstitutionPayload = {
  formatVersion: 'substitution-event-v1',
  expectedCheckpoint: game.checkpoint.ref,
  eventId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  operation: {
    kind: 'pitcher',
    side: 'home',
    outgoingId: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    incomingId: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    count: { strikes: '1', balls: '2' },
    dh: 'retain',
  },
  incomingSnapshots: [
    { playerId: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', uniformNumber: '18' },
  ],
}

describe('交代P2 wire', () => {
  it('既同期のD1/権利証明境界で閉本文を組み立てる', () => {
    const event = substitutionEvent(game.id, game.current_d4, d5, 1000, payload)
    const slot = {
      game: game.id,
      d4: game.current_d4,
      d1: 2,
      d5,
      version: 1,
      event,
      state: '未送信' as const,
    }
    const body = substitutionBody(slot, 'opaque-proof')
    expect(body.events).toHaveLength(1)
    expect(body.events[0]).toMatchObject({
      d1: 2,
      d5,
      event_kind: 'substitution',
      payload,
    })
    expect(body.recording_right_proof).toBe('opaque-proof')
  })

  it('未知field・誤count・不足・不正IDを閉じる', () => {
    expect(isSubstitutionPayload(payload)).toBe(true)
    expect(isSubstitutionPayload({ ...payload, extra: true })).toBe(false)
    expect(
      isSubstitutionPayload({
        ...payload,
        expectedCheckpoint: { ...payload.expectedCheckpoint, revision: '01' },
      }),
    ).toBe(false)
    expect(
      isSubstitutionPayload({
        ...payload,
        operation: {
          ...payload.operation,
          count: { strikes: '3', balls: '2' },
        },
      }),
    ).toBe(false)
    expect(
      isSubstitutionPayload({
        ...payload,
        operation: { ...payload.operation, incomingId: d5, extra: null },
      }),
    ).toBe(false)
    expect(isSubstitutionPayload({ ...payload, eventId: 'not-a-uuid' })).toBe(
      false,
    )
    expect(
      isSubstitutionPayload({
        ...payload,
        incomingSnapshots: [{ playerId: d5, uniformNumber: '18' }],
      }),
    ).toBe(false)
  })
})

describe('交代の実client C2境界', () => {
  let pinia: Pinia
  const tenant = '10000000-0000-4000-8000-000000000001'
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    localStorage.clear()
    setVerifiedAuthForTest(useAuthStore(), { teamId: tenant, teamName: 'unit' })
    vi.stubGlobal('isSecureContext', true)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    disposePinia(pinia)
  })
  it.each([true, false])(
    'tenant/challengeを実送信しC2一致=%sだけを解釈する',
    async (matches) => {
      const attempt = 'ffffffff-ffff-4fff-8fff-ffffffffffff'
      const sentD5 = matches ? d5 : 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
      const device = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
      const calls: Headers[] = []
      vi.stubGlobal(
        'fetch',
        vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
          const headers = new Headers(init?.headers)
          calls.push(headers)
          const challenge = headers.get('X-Pitchlog-Tenant-Challenge')
          return new Response('{}', {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
              ...(matches && challenge
                ? {
                    'X-Pitchlog-Tenant-Match': '1',
                    'X-Pitchlog-Tenant-Challenge': challenge,
                  }
                : {}),
            },
          })
        }),
      )
      const event = substitutionEvent(
        game.id,
        game.current_d4,
        sentD5,
        1000,
        payload,
      )
      const result = await postSubstitution(
        {
          game: game.id,
          d4: game.current_d4,
          d1: 2,
          d5: sentD5,
          version: 1,
          event,
          state: '未送信',
        },
        'unit-proof',
        { deviceId: device, deviceCredential: 'unit-credential', attempt },
      )
      expect(calls).toHaveLength(1)
      expect(calls[0]!.get('X-Pitchlog-Expected-Tenant')).toBe(tenant)
      expect(calls[0]!.get('X-Pitchlog-Tenant-Challenge')).toMatch(
        /^[a-f0-9-]{36}$/,
      )
      expect(calls[0]!.get('X-Pitchlog-Sync-Attempt')).toBe(attempt)
      expect(result.sent).toBe(matches)
      if (!matches && !result.sent) {
        expect(result.reason).toBe('no-response')
        expect(result.error).toBeInstanceOf(ApiTenantVerificationError)
        expect(Object.hasOwn(result, 'response')).toBe(false)
        expect(useAuthStore().isAuthenticated).toBe(false)
      }
    },
  )
})
