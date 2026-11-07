import { beforeEach, describe, expect, it, vi } from 'vitest'
import fixture from './fixtures/lineupPrefixGame.recorded.v3.json'
import { apiRequest } from './client'
import {
  p3ChangeBody,
  postP3Change,
  readP3ChangeConfirmation,
  readP3TargetOffer,
} from './pastCorrectionProduct'

vi.mock('./client', () => ({ apiRequest: vi.fn() }))
const request = vi.mocked(apiRequest)
const game = fixture.value
const play = game.page.items[0]!.play_row
const d5 = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const attempt = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const offer = {
  target_reference: { game: game.id, d4: game.current_d4, d1: 1 },
  expected_version: 1,
  expected_prefix_ref: game.prefix_ref,
  target_event_id: play.source_event_id,
  target_play_id: play.id,
  original_result_id: 'batting-result.ball',
}
const observations = {
  pitchTypeKey: 'pitch-type.straight',
  course: { unit: '1/263' as const, x: '100', y: '150' },
  pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
  stance: null,
  battingSide: null,
}

beforeEach(() => request.mockReset())

describe('実P3 wire', () => {
  it('真正GETの版と元参照を読んで、同本文の受理全組だけを採用する', async () => {
    request.mockResolvedValueOnce(offer)
    const read = await readP3TargetOffer(game.id, 1)
    expect(request).toHaveBeenCalledWith(
      'GET',
      `/games/${game.id}/sync/change-target/1`,
      { tenantBound: true, signal: undefined },
    )
    const body = p3ChangeBody(
      read,
      d5,
      game.recovery_generation,
      'presented-proof',
      'batting-result.called-pitch',
      observations,
    )
    expect(body.change.target_reference).toEqual(offer.target_reference)
    expect(body.change.expected_version).toBe(offer.expected_version)
    request.mockResolvedValueOnce({
      boundary: '変更受理',
      target_reference: {
        試合: game.id,
        '対象の D4': game.current_d4,
        '対象の D1': 1,
      },
      expected_version: 1,
      d5,
      confirmed_content: structuredClone(body.change.payload),
      accepted_at: '2026-11-07T00:00:00+00:00',
    })
    const result = await postP3Change(body, {
      deviceId: play.batter_id,
      deviceCredential: 'presented-credential',
      attempt,
    })
    expect(result.kind).toBe('accepted')
    expect(request).toHaveBeenLastCalledWith(
      'POST',
      `/games/${game.id}/sync/change`,
      {
        tenantBound: true,
        syncCredentials: {
          deviceId: play.batter_id,
          deviceCredential: 'presented-credential',
          attempt,
        },
        body,
      },
    )
  })

  it('元版・D4・本文・余分なACKを成功に読まない', async () => {
    request.mockResolvedValueOnce(offer)
    const read = await readP3TargetOffer(game.id, 1)
    const body = p3ChangeBody(
      read,
      d5,
      game.recovery_generation,
      'presented-proof',
      'batting-result.ball',
      observations,
    )
    const valid = {
      boundary: '変更受理',
      target_reference: {
        試合: game.id,
        '対象の D4': game.current_d4,
        '対象の D1': 1,
      },
      expected_version: 1,
      d5,
      confirmed_content: body.change.payload,
      accepted_at: '2026-11-07T00:00:00+00:00',
    }
    for (const changed of [
      { expected_version: 2 },
      {
        target_reference: {
          ...valid.target_reference,
          '対象の D4': 'd4.1.bad',
        },
      },
      {
        confirmed_content: {
          ...body.change.payload,
          replacementResultId: 'bad',
        },
      },
      { extra: true },
    ]) {
      request.mockResolvedValueOnce({ ...valid, ...changed })
      await expect(
        postP3Change(body, {
          deviceId: play.batter_id,
          deviceCredential: 'presented-credential',
          attempt,
        }),
      ).rejects.toThrow()
    }
  })

  it('未知target版と旧numeric D4を読まない', async () => {
    for (const changed of [
      { expected_version: 2 },
      { target_reference: { ...offer.target_reference, d4: 1 } },
      { target_play_id: 'invalid' },
    ]) {
      request.mockResolvedValueOnce({ ...offer, ...changed })
      await expect(readP3TargetOffer(game.id, 1)).rejects.toThrow()
    }
  })

  it('同D5のslot2確認だけをtenantBoundで読み、旧版と別receiptを拒否する', async () => {
    const confirmed = {
      target_reference: offer.target_reference,
      confirmed_version: 2,
      d5,
      source_event_id: play.source_event_id,
      target_play_id: play.id,
      stats_version_id: attempt,
      current_prefix_ref: game.prefix_ref,
      current_after: game.after,
    }
    request.mockResolvedValueOnce(confirmed)
    expect(await readP3ChangeConfirmation(game.id, 1, d5)).toEqual(confirmed)
    expect(request).toHaveBeenLastCalledWith(
      'GET',
      `/games/${game.id}/sync/change-confirmation/1`,
      { tenantBound: true, signal: undefined },
    )
    for (const changed of [
      { confirmed_version: 1 },
      { d5: attempt },
      { source_event_id: 'invalid' },
      { current_prefix_ref: { ...game.prefix_ref, gameId: attempt } },
      { extra: true },
    ]) {
      request.mockResolvedValueOnce({ ...confirmed, ...changed })
      await expect(readP3ChangeConfirmation(game.id, 1, d5)).rejects.toThrow()
    }
  })
})
