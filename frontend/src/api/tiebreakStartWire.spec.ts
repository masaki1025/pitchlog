import { describe, expect, it } from 'vitest'
import {
  TIEBREAK_START_FORMAT,
  TIEBREAK_START_KIND,
  isTiebreakStartPayload,
  tiebreakStartBody,
  tiebreakStartEvent,
  type TiebreakStartPayload,
} from './tiebreakStartWire'
import type { DurableQueueSlot } from '../lib/sync/durableQueue'

const gameId = '10000000-0000-0000-0000-000000000001'
const d4 = 'd4-generation'
const d5 = '20000000-0000-0000-0000-000000000001'
const eventId = '30000000-0000-0000-0000-000000000001'
const firstRunnerId = '40000000-0000-0000-0000-000000000001'
const secondRunnerId = '40000000-0000-0000-0000-000000000002'

function payload(): TiebreakStartPayload {
  return {
    formatVersion: TIEBREAK_START_FORMAT,
    expectedCheckpoint: {
      id: '50000000-0000-0000-0000-000000000001',
      revision: '7',
      digest: 'a'.repeat(64),
    },
    eventId,
    runnerPlacement: 'first-second',
    leadoffBatter: '4',
    inning: '10',
    firstRunnerId,
    secondRunnerId,
  }
}

describe('タイブレーク開始wire', () => {
  it('閉じたpayloadだけを受理し、二重配置を拒否する', () => {
    expect(isTiebreakStartPayload(payload())).toBe(true)
    expect(
      isTiebreakStartPayload({
        ...payload(),
        secondRunnerId: firstRunnerId,
      }),
    ).toBe(false)
    expect(isTiebreakStartPayload({ ...payload(), leadoffBatter: '10' })).toBe(
      false,
    )
    expect(isTiebreakStartPayload({ ...payload(), unexpected: true })).toBe(
      false,
    )
  })

  it('種別4のイベントを保存種別tiebreak_startへ対応付ける', () => {
    const event = tiebreakStartEvent(gameId, d4, d5, 12, payload())
    expect(event.fields.V5).toBe('4')
    expect(event.fields.V6).toBe(12)
    expect(event.fields.V7).toEqual(payload())
  })
})

it('保存本文は参加区分4をDB/P1のtiebreak_start literalへ写す', () => {
  const event = tiebreakStartEvent(gameId, d4, d5, 12, payload())
  const slot: DurableQueueSlot = {
    game: gameId,
    d4,
    d1: 1,
    d5,
    version: 1,
    event,
    state: 'unsent' as DurableQueueSlot['state'],
  }
  const body = tiebreakStartBody({
    gameId,
    recordingRightProof: 'opaque-proof',
    slots: [slot],
    eventKinds: [TIEBREAK_START_KIND],
  })
  expect(body.events).toHaveLength(1)
  expect(body.events[0]!.event_kind).toBe('tiebreak_start')
  expect(body.events[0]!.payload).toEqual(payload())
})
