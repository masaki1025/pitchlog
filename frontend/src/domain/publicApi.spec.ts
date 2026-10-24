import { describe, expect, it } from 'vitest'

import './entry'
import { domainOperations } from './publicApi'

describe('ドメイン公開口の疎通操作', () => {
  it('操作表を凍結し、公開操作を ping と deriveState にする', () => {
    expect(Object.isFrozen(domainOperations)).toBe(true)
    expect(Object.keys(domainOperations)).toEqual([
      'ping',
      'deriveState',
      'applyOperation',
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

describe('T1 状態計算の境界', () => {
  const emptyState = {
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
  }
  const emptyBoard = {
    inningScores: { home: '0', away: '0' },
    hits: '0',
    errors: '0',
    strikeouts: '0',
    walks: '0',
  }

  function request(resultId: string) {
    return JSON.stringify({
      before: { stateFields: emptyState, scoreboard: emptyBoard },
      resultId,
      pitchEventKind: 'pitch-event',
    })
  }

  it('単打を十進文字列のまま計算し、走者一塁と打順 2 を返す', () => {
    const body = JSON.parse(
      domainOperations.deriveState(request('batting-result.single')),
    )
    expect(body.ok).toBe(true)
    expect(body.value.after.stateFields['state.runners']).toBe('first')
    expect(body.value.after.stateFields['state.battingOrder']).toBe('2')
    expect(body.value.after.stateFields['state.count.strikes']).toBe('0')
    expect(body.value.after.stateFields['state.score']).toEqual({
      home: '0',
      away: '0',
    })
    expect(body.value.statFlags['安打']).toBe(true)
  })

  it('未知の結果 ID と数値の入力を拒否する', () => {
    expect(
      JSON.parse(
        domainOperations.deriveState(request('batting-result.unknown')),
      ).error.code,
    ).toBe('INVALID_REQUEST')
    const numeric = JSON.stringify({
      before: {
        stateFields: { ...emptyState, 'state.count.strikes': 0 },
        scoreboard: emptyBoard,
      },
      resultId: 'batting-result.ball',
    })
    expect(JSON.parse(domainOperations.deriveState(numeric)).error.code).toBe(
      'INVALID_STATE',
    )
  })

  it('タイブレーク開始を十進文字列のまま適用する', () => {
    const body = JSON.parse(
      domainOperations.applyOperation(
        JSON.stringify({
          before: { stateFields: emptyState, scoreboard: emptyBoard },
          operation: {
            kind: 'tiebreak-start',
            spec: {
              runnerPlacement: 'first-second',
              leadoffBatter: '1',
              inning: '8',
              activationRelation: 'ready',
            },
          },
        }),
      ),
    )
    expect(body.ok).toBe(true)
    expect(body.value.operationResult).toBe('applied')
    expect(body.value.after.stateFields['state.runners']).toBe('first-second')
    expect(body.value.after.stateFields['state.battingOrder']).toBe('1')
    expect(body.value.after.stateFields['state.tiebreakActive']).toBe(true)
    expect(body.value.after.stateFields['state.inning']).toBe('8')
  })

  it('終了済み試合の終了宣言を事前条件で拒否する', () => {
    const body = JSON.parse(
      domainOperations.applyOperation(
        JSON.stringify({
          before: {
            stateFields: { ...emptyState, 'state.gameEnded': true },
            scoreboard: emptyBoard,
          },
          operation: { kind: 'game-end-declaration' },
        }),
      ),
    )
    expect(body.value.operationResult).toBe('rejected-precondition')
    expect(body.value.after.stateFields['state.gameEnded']).toBe(true)
    expect(body.value.written.gameEnded).toBe(false)
  })

  it('未知の操作種別を拒否する', () => {
    const body = JSON.parse(
      domainOperations.applyOperation(
        JSON.stringify({
          before: { stateFields: emptyState, scoreboard: emptyBoard },
          operation: { kind: 'unknown' },
        }),
      ),
    )
    expect(body.error.code).toBe('INVALID_REQUEST')
  })
})
