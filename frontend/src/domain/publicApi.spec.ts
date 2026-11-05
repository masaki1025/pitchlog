import { describe, expect, it } from 'vitest'

import './entry'
import { domainOperations } from './publicApi'

describe('ドメイン公開口の疎通操作', () => {
  it('操作表を凍結し、公開操作を承認済み12口に限定する', () => {
    expect(Object.isFrozen(domainOperations)).toBe(true)
    expect(Object.keys(domainOperations)).toEqual([
      'ping',
      'deriveState',
      'deriveOrdinaryPitch',
      'deriveTerminalPitch',
      'deriveStrikeoutPitch',
      'derivePlayPrefixWithContinuation',
      'deriveLineupPlayPrefixWithContinuation',
      'deriveFirstPitchWithContinuation',
      'deriveOrdinaryPitchWithContinuation',
      'applyUndo',
      'validateInitialGameRoster',
      'quantizeCourse',
    ])
  })

  it('build 入口が同じ凍結済み公開表を globalThis に置く', () => {
    const domainGlobal = globalThis as typeof globalThis & {
      PitchlogDomain?: typeof domainOperations
    }
    expect(domainGlobal.PitchlogDomain).toBe(domainOperations)
    expect(Object.isFrozen(domainGlobal.PitchlogDomain)).toBe(true)
  })

  it.each(['0', '-1', '9007199254740993', '18446744073709551621'])(
    '十進文字列 %s を JSON 文字列のまま往復する',
    (value) => {
      const response = domainOperations.ping(JSON.stringify({ value }))
      expect(response).toBe(JSON.stringify({ ok: true, value }))
    },
  )

  it('不正な JSON と不正な入力を構造化エラーで返す', () => {
    expect(domainOperations.ping('{')).toBe(
      '{"ok":false,"error":{"code":"INVALID_JSON"}}',
    )
    expect(domainOperations.ping('{"value":1}')).toBe(
      '{"ok":false,"error":{"code":"INVALID_DECIMAL_INTEGER"}}',
    )
    expect(domainOperations.ping('{"value":"-0"}')).toBe(
      '{"ok":false,"error":{"code":"INVALID_DECIMAL_INTEGER"}}',
    )
    expect(domainOperations.ping('{"value":"1","other":"2"}')).toBe(
      '{"ok":false,"error":{"code":"INVALID_REQUEST"}}',
    )
  })
})

describe('取消の JSON 境界', () => {
  const initial = {
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
      'state.score': { home: '0', away: '0' },
    },
    scoreboard: {
      inningScores: { home: '0', away: '0' },
      hits: '0',
      errors: '0',
      strikeouts: '0',
      walks: '0',
    },
  }
  const ball = {
    kind: 'confirmed-play',
    difference: {
      stateFields: {
        'state.count.balls': { before: '0', after: '1' },
      },
      scoreboard: {},
      statFlags: {
        投球回算入アウト: false,
        投球数: true,
        奪三振: false,
        与四球: false,
        与死球: false,
        被安打: false,
        被本塁打: false,
        失点: false,
        失策: false,
        打席: false,
        打数: false,
        安打: false,
        本塁打: false,
        塁打: false,
        犠打: false,
        犠飛: false,
        四球: false,
        死球: false,
        三振: false,
        打撃妨害出塁: false,
        走塁妨害出塁: false,
        得点: false,
        打点: false,
      },
    },
  }
  it('1 球の差分を逆適用し、空の履歴文脈を返す', () => {
    const current = structuredClone(initial)
    current.stateFields['state.count.balls'] = '1'
    const response = JSON.parse(
      domainOperations.applyUndo(
        JSON.stringify({ current, history: { stack: [ball] } }),
      ),
    )
    expect(response).toEqual({
      ok: true,
      value: {
        operationResult: 'applied',
        after: initial,
        historyEffect: { pops: '1' },
        historyContext: [],
      },
    })
  })
  it('空スタックは状態を変えず nothing-to-undo を返す', () => {
    const response = JSON.parse(
      domainOperations.applyUndo(
        JSON.stringify({ current: initial, history: { stack: [] } }),
      ),
    )
    expect(response.value.operationResult).toBe('nothing-to-undo')
    expect(response.value.after).toEqual(initial)
    expect(response.value.historyEffect).toEqual({ pops: '0' })
  })
  it('v3 の両cursorを差分の before へ戻す', () => {
    const current = structuredClone(initial)
    current.stateFields['state.battingOrder'] = '2'
    const entry = structuredClone(ball)
    Object.assign(entry.difference.stateFields, {
      'state.battingOrder': { before: '1', after: '2' },
    })
    Object.assign(entry.difference, {
      battingOrderBySide: { away: { before: '1', after: '2' } },
    })
    const response = JSON.parse(
      domainOperations.applyUndo(
        JSON.stringify({
          current: { ...current, battingOrderBySide: { away: '2', home: '5' } },
          history: { stack: [entry] },
        }),
      ),
    )
    expect(response.value.after.battingOrderBySide).toEqual({
      away: '1',
      home: '5',
    })
  })
  it('数値型・未知キー・不正差分を拒否する', () => {
    expect(
      domainOperations.applyUndo(
        JSON.stringify({
          current: {
            ...initial,
            stateFields: { ...initial.stateFields, 'state.outs': 0 },
          },
          history: { stack: [] },
        }),
      ),
    ).toBe('{"ok":false,"error":{"code":"INVALID_REQUEST"}}')
    expect(
      domainOperations.applyUndo(
        JSON.stringify({ current: initial, history: { stack: [], extra: 1 } }),
      ),
    ).toBe('{"ok":false,"error":{"code":"INVALID_REQUEST"}}')
    const broken = structuredClone(ball)
    Object.assign(broken.difference, {
      scoreboard: { hits: { before: '0' } },
    })
    expect(
      domainOperations.applyUndo(
        JSON.stringify({ current: initial, history: { stack: [broken] } }),
      ),
    ).toBe('{"ok":false,"error":{"code":"INVALID_REQUEST"}}')
  })
})
