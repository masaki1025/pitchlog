import { describe, expect, it } from 'vitest'
import { undoRead } from '../screens/GameScreenUndoProduct.test-support'
import {
  isSubstitutionPayload,
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
