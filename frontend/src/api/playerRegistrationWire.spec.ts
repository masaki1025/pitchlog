import { describe, expect, it } from 'vitest'
import {
  isPlayerRegistrationInput,
  PLAYER_REGISTRATION_KIND,
  playerRegistrationBody,
  playerRegistrationEvent,
  playerRegistrationInput,
  readPlayerRegistrationAck,
} from './playerRegistrationWire'
import type { DurableQueueSlot } from '../lib/sync/durableQueue'
import { queueStateId } from '../lib/sync/queueState'

const game = '11111111-1111-4111-8111-111111111111'
const d4 = 'grant-1'
const d5 = '22222222-2222-4222-8222-222222222222'
const temporary = '33333333-3333-4333-8333-333333333333'
const team = '44444444-4444-4444-8444-444444444444'
const official = '55555555-5555-4555-8555-555555555555'

function input() {
  return playerRegistrationInput({
    temporaryId: temporary,
    teamRecordId: team,
    name: '断中登録選手',
    throws: 'left',
    bats: 'both',
    uniformNumber: '18',
    rosterStatusKey: 'active',
  })
}

function slot(): DurableQueueSlot {
  return {
    game,
    d4,
    d1: 3,
    d5,
    version: 1,
    event: playerRegistrationEvent(game, d4, d5, input()),
    state: queueStateId('未送信'),
  }
}

describe('playerRegistrationWire', () => {
  it('保存した登録入力から閉じた wire を毎回同じ形で作る', () => {
    const first = playerRegistrationBody(slot(), 'proof')
    const second = playerRegistrationBody(slot(), 'proof')
    expect(first).toEqual(second)
    expect(first.events).toEqual([
      {
        d5,
        d1: 3,
        d4,
        game_id: game,
        event_kind: 'player_registration',
        payload: { player_id: temporary },
        registration: {
          temporary_id: temporary,
          team_record_id: team,
          name: '断中登録選手',
          throws: 'left',
          bats: 'both',
          uniform_number: '18',
          roster_status_key: 'active',
        },
      },
    ])
    expect(JSON.stringify(first)).not.toMatch(/formatVersion|temporaryId/)
  })

  it('未指定の任意項目を wire へ足さない', () => {
    const value = playerRegistrationInput({
      temporaryId: temporary,
      teamRecordId: team,
      name: '断中登録選手',
      throws: null,
      bats: null,
      uniformNumber: null,
      rosterStatusKey: 'active',
    })
    const body = playerRegistrationBody(
      {
        ...slot(),
        event: playerRegistrationEvent(game, d4, d5, value),
      },
      'proof',
    )
    expect(body.events[0]?.registration).toEqual({
      temporary_id: temporary,
      team_record_id: team,
      name: '断中登録選手',
      roster_status_key: 'active',
    })
  })

  it('登録以外のスロットを送信本文へ変換しない', () => {
    expect(() =>
      playerRegistrationBody(
        {
          ...slot(),
          event: {
            fields: { V1: d5, V3: d4, V4: game, V5: '3', V7: {} },
          },
        },
        'proof',
      ),
    ).toThrow(/保存済みその場登録/)
    expect(PLAYER_REGISTRATION_KIND.id).toBe('6')
  })

  it('余分なキーや空値を入力として受理しない', () => {
    expect(isPlayerRegistrationInput({ ...input(), extra: true })).toBe(false)
    expect(isPlayerRegistrationInput({ ...input(), name: '' })).toBe(false)
    expect(isPlayerRegistrationInput({ ...input(), throws: 'switch' })).toBe(
      false,
    )
  })

  it('受理 ACK から一時IDと正式IDの写像を返す', () => {
    const parsed = readPlayerRegistrationAck(
      {
        advancedD3: 3,
        eventResults: [{ d1: 3, d4, d5, a5Result: '受理' }],
        playerIdMappings: [{ temporaryId: temporary, officialId: official }],
      },
      { d4, d1: 3, d5, temporaryId: temporary },
    )
    expect(parsed?.mapping).toEqual({
      temporaryId: temporary,
      officialId: official,
    })
    expect(parsed?.ack.boundaryResult).toBe('B1')
  })

  it('写像の欠落・余分・別IDでは同期済みの根拠にしない', () => {
    const base = {
      advancedD3: 3,
      eventResults: [{ d1: 3, d4, d5, a5Result: '受理' }],
    }
    expect(
      readPlayerRegistrationAck(base, {
        d4,
        d1: 3,
        d5,
        temporaryId: temporary,
      }),
    ).toBeUndefined()
    expect(
      readPlayerRegistrationAck(
        {
          ...base,
          playerIdMappings: [
            { temporaryId: temporary, officialId: official },
            {
              temporaryId: '66666666-6666-4666-8666-666666666666',
              officialId: official,
            },
          ],
        },
        { d4, d1: 3, d5, temporaryId: temporary },
      ),
    ).toBeUndefined()
    expect(
      readPlayerRegistrationAck(
        {
          ...base,
          playerIdMappings: [
            {
              temporaryId: '66666666-6666-4666-8666-666666666666',
              officialId: official,
            },
          ],
        },
        { d4, d1: 3, d5, temporaryId: temporary },
      ),
    ).toBeUndefined()
  })

  it('拒否 ACK から写像を取り出さない', () => {
    expect(
      readPlayerRegistrationAck(
        {
          advancedD3: 3,
          eventResults: [{ d1: 3, d4, d5, a5Result: '拒否' }],
          playerIdMappings: [{ temporaryId: temporary, officialId: official }],
        },
        { d4, d1: 3, d5, temporaryId: temporary },
      ),
    ).toBeUndefined()
  })
})
