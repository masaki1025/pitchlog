/** P3実clientが資格・tenant C2を送受信し、異なるechoを拒否する。 */
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { IDBFactory } from 'fake-indexeddb'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import fixture from './fixtures/lineupPrefixGame.recorded.v3.json'
import { setVerifiedAuthForTest } from './auth.test-support'
import { ApiTenantVerificationError } from './client'
import { useAuthStore } from '../stores/authStore'
import {
  p3ChangeBody,
  postP3Change,
  type P3TargetOffer,
} from './pastCorrectionProduct'

const game = fixture.value
const play = game.page.items[0]!.play_row
const offer: P3TargetOffer = {
  target_reference: { game: game.id, d4: game.current_d4, d1: 1 },
  expected_version: 1,
  expected_prefix_ref: game.prefix_ref as P3TargetOffer['expected_prefix_ref'],
  target_event_id: play.source_event_id,
  target_play_id: play.id,
  original_result_id: 'batting-result.called-pitch',
}
const body = p3ChangeBody(
  offer,
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  game.recovery_generation,
  'unit-proof',
  'batting-result.ball',
  {
    pitchTypeKey: 'pitch-type.straight',
    course: { unit: '1/263', x: '100', y: '150' },
    pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
    stance: null,
    battingSide: null,
  },
)
const credential = {
  deviceId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  deviceCredential: 'unit-credential',
  attempt: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
}
let pinia: Pinia

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: game.prefix_ref.tenantId,
    teamName: '実client対向',
  })
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('isSecureContext', true)
})

afterEach(() => {
  disposePinia(pinia)
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function response(challenge: string, match = '1') {
  return new Response(
    JSON.stringify({
      boundary: '変更受理',
      target_reference: {
        試合: game.id,
        '対象の D4': game.current_d4,
        '対象の D1': 1,
      },
      expected_version: 1,
      d5: body.change.d5,
      confirmed_content: body.change.payload,
      accepted_at: '2026-11-07T00:00:00+00:00',
    }),
    {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'X-Pitchlog-Tenant-Match': match,
        'X-Pitchlog-Tenant-Challenge': challenge,
      },
    },
  )
}

it('P3だけを許す実clientの端末資格と同tenant challenge echoで受理する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url, init) => {
      const headers = new Headers(init?.headers)
      expect(headers.get('X-Pitchlog-Expected-Tenant')).toBe(
        game.prefix_ref.tenantId,
      )
      expect(headers.get('X-Pitchlog-Tenant-Challenge')).toMatch(
        /^[0-9a-f-]{36}$/,
      )
      expect(headers.get('X-Pitchlog-Device-Id')).toBe(credential.deviceId)
      expect(headers.get('X-Pitchlog-Sync-Attempt')).toBe(credential.attempt)
      expect(headers.get('X-Pitchlog-Device-Credential')).toBe(
        credential.deviceCredential,
      )
      expect(JSON.parse(String(init?.body))).toEqual(body)
      return response(headers.get('X-Pitchlog-Tenant-Challenge')!)
    }),
  )
  expect((await postP3Change(body, credential)).kind).toBe('accepted')
  expect(fetch).toHaveBeenCalledOnce()
})

it('C2 echo不一致をACK成功へ上げず認証を失効する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url, init) =>
      response(
        new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge')!,
        '0',
      ),
    ),
  )
  await expect(postP3Change(body, credential)).rejects.toBeInstanceOf(
    ApiTenantVerificationError,
  )
  expect(useAuthStore().isAuthenticated).toBe(false)
})

it('安全な耐久保存を開始できないときはP3を送信しない', async () => {
  vi.stubGlobal('isSecureContext', false)
  const fetcher = vi.fn()
  vi.stubGlobal('fetch', fetcher)
  await expect(postP3Change(body, credential)).rejects.toThrow(
    '元の同期要求と試行を耐久確認できません',
  )
  expect(fetcher).not.toHaveBeenCalled()
})
