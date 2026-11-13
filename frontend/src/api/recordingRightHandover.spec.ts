import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from './client'
import {
  acquireRecordingRightHandover,
  releaseRecordingRightHandover,
} from './recordingRightHandover'

vi.mock('./client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./client')>()
  return { ...actual, apiRequest: vi.fn() }
})

const tenant = '10000000-0000-4000-8000-000000000001'
const game = '10000000-0000-4000-8000-000000000002'
const from = '10000000-0000-4000-8000-000000000003'
const to = '10000000-0000-4000-8000-000000000004'
const request = '10000000-0000-4000-8000-000000000005'
const d4 = 'd4.1.' + 'A'.repeat(55)
const nextD4 = 'd4.1.' + 'B'.repeat(55)
const proof = 'C'.repeat(43)
const credentials = { deviceId: from, deviceCredential: 'credential' }

const apiRequest = vi.mocked(client.apiRequest)

beforeEach(() => {
  apiRequest.mockReset()
})

describe('記録権引き継ぎAPI', () => {
  it('解放は明示確認と旧V12を送り、新V12を含まない応答を返す', async () => {
    apiRequest.mockResolvedValue({
      tenant_id: tenant,
      game_id: game,
      handover_request_id: request,
      from_device_id: from,
      from_generation: '7',
      to_device_id: to,
      last_d1: 12,
      released_at: '2026-11-13T00:00:00Z',
    })
    const result = await releaseRecordingRightHandover(
      game,
      {
        handoverRequestId: request,
        toDeviceId: to,
        fromD4: d4,
        lastD1: 12,
        recordingRightProof: proof,
      },
      credentials,
    )
    expect(result.from_generation).toBe('7')
    expect(apiRequest).toHaveBeenCalledWith(
      'POST',
      `/games/${game}/recording-right/handover/release`,
      expect.objectContaining({
        tenantBound: true,
        deviceCredentials: credentials,
        body: expect.objectContaining({
          handover_request_id: request,
          to_device_id: to,
          from_d4: d4,
          last_d1: 12,
          recording_right_proof: proof,
          confirm_release: true,
        }),
      }),
    )
  })

  it('取得は新世代のD4と生のV12を返す', async () => {
    apiRequest.mockResolvedValue({
      tenant_id: tenant,
      game_id: game,
      handover_request_id: request,
      device_id: to,
      d4: nextD4,
      recovery_generation: '1',
      recording_right_proof: proof,
    })
    const result = await acquireRecordingRightHandover(game, request, {
      deviceId: to,
      deviceCredential: 'new-credential',
    })
    expect(result.d4).toBe(nextD4)
    expect(result.device_id).toBe(to)
    expect(result.recording_right_proof).toBe(proof)
  })

  it('短い/欠けたproofや余剰keyを成功へ補完しない', async () => {
    apiRequest.mockResolvedValue({
      tenant_id: tenant,
      game_id: game,
      handover_request_id: request,
      device_id: to,
      d4: nextD4,
      recovery_generation: '1',
      recording_right_proof: 'short',
    })
    await expect(
      acquireRecordingRightHandover(game, request, {
        deviceId: to,
        deviceCredential: 'new-credential',
      }),
    ).rejects.toThrow('引き継ぎの応答を確認できません')
    apiRequest.mockResolvedValue({
      tenant_id: tenant,
      game_id: game,
      handover_request_id: request,
      from_device_id: from,
      from_generation: '7',
      to_device_id: to,
      last_d1: 12,
      released_at: '2026-11-13T00:00:00Z',
      extra: true,
    })
    await expect(
      releaseRecordingRightHandover(
        game,
        {
          handoverRequestId: request,
          toDeviceId: to,
          fromD4: d4,
          lastD1: 12,
          recordingRightProof: proof,
        },
        credentials,
      ),
    ).rejects.toThrow('引き継ぎの応答を確認できません')
  })
})
