import { describe, expect, it } from 'vitest'
import { applyGameLifecycle } from './gameLifecycle'

/** 保存/認可の代わりにせず、唯一核の状態差分だけを検査する。 */
function request() {
  return {
    formatVersion: 'native-game-lifecycle-v1',
    action: 'end',
    current: {
      stateFields: {
        'state.inning': '9',
        'state.half': 'bottom',
        'state.outs': '1',
        'state.count.strikes': '1',
        'state.count.balls': '2',
        'state.runners': 'empty',
        'state.battingOrder': '1',
        'state.tiebreakActive': false,
        'state.gameEnded': true,
        'state.score': { home: '3', away: '2' },
      },
      scoreboard: {
        inningScores: { home: '3', away: '2' },
        hits: '2',
        errors: '0',
        strikeouts: '1',
        walks: '0',
      },
      battingOrderBySide: { home: '1', away: '1' },
    },
    lifecycle: { status: 'in_progress', lastVersion: '0', active: null },
    target: null,
    event: {
      eventId: '00000000-0000-4000-8000-000000000001',
      receiptId: '00000000-0000-4000-8000-000000000002',
    },
  }
}

describe('game lifecycle pure kernel', () => {
  it('終了と再開は全得点/カウントを保持し、再開だけ終了ロックを解除する', () => {
    const input = request()
    const ended = JSON.parse(applyGameLifecycle(JSON.stringify(input)))
    expect(ended.ok).toBe(true)
    expect(ended.value.current).toEqual(input.current)
    expect(ended.value.lifecycle.lastVersion).toBe('1')
    const reopened = JSON.parse(
      applyGameLifecycle(
        JSON.stringify({
          ...input,
          action: 'reopen',
          lifecycle: ended.value.lifecycle,
          target: ended.value.lifecycle.active,
          event: {
            eventId: '00000000-0000-4000-8000-000000000003',
            receiptId: '00000000-0000-4000-8000-000000000004',
          },
        }),
      ),
    )
    const expected = structuredClone(input.current)
    expected.stateFields['state.gameEnded'] = false
    expect(reopened.value.current).toEqual(expected)
    expect(reopened.value.lifecycle).toEqual({
      status: 'in_progress',
      lastVersion: '1',
      active: null,
    })
    expect(input.current.stateFields['state.gameEnded']).toBe(true)
  })

  it('終了していない試合を再開成功にしない', () => {
    expect(
      JSON.parse(
        applyGameLifecycle(JSON.stringify({ ...request(), action: 'reopen' })),
      ),
    ).toEqual({ ok: false, error: { code: 'LIFECYCLE_STATE_MISMATCH' } })
  })
})
