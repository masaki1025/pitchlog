import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import './entry'
import { domainOperations } from './publicApi'

describe('ドメイン公開口の疎通操作', () => {
  it('操作表を凍結し、公開操作を閉じた集合に限定する', () => {
    expect(Object.isFrozen(domainOperations)).toBe(true)
    expect(Object.keys(domainOperations)).toEqual([
      'ping',
      'applyGameLifecycle',
      'deriveState',
      'deriveOrdinaryPitch',
      'replayPastCorrectionPage',
      'deriveTerminalPitch',
      'deriveStrikeoutPitch',
      'deriveBattedHit',
      'deriveInterference',
      'derivePlayPrefixWithContinuation',
      'deriveLineupPlayPrefixWithContinuation',
      'deriveFirstPitchWithContinuation',
      'deriveOrdinaryPitchWithContinuation',
      'validateInitialGameRoster',
      'quantizeCourse',
      'applyUndo',
      'applySubstitutionV1',
      'deriveInitialSubstitutionStateV1',
      'transitionSubstitutionV1',
      'advanceSubstitutionAfterPitchV1',
      'transitionTiebreakStartV1',
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

describe('純取消の採用済み公開境界', () => {
  it('空履歴でもstateEffectを含む全5key/全23flagを返す', () => {
    const input = {
      current: {
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
      },
      history: { stack: [] },
    }
    const raw = JSON.stringify(input)
    const output = JSON.parse(domainOperations.applyUndo(raw))
    expect(Object.keys(output)).toEqual(['ok', 'value'])
    expect(Object.keys(output.value)).toEqual([
      'operationResult',
      'after',
      'stateEffect',
      'historyEffect',
      'historyContext',
    ])
    expect(Object.keys(output.value.stateEffect)).toEqual([
      'stateFields',
      'scoreboard',
      'statFlags',
      'historyAndResult',
    ])
    expect(Object.keys(output.value.stateEffect.statFlags)).toHaveLength(23)
    expect(Object.values(output.value.stateEffect.statFlags)).toEqual(
      Array(23).fill({ kind: 'unchanged' }),
    )
    expect(output.value.after).toEqual(input.current)
    expect(output.value.operationResult).toBe('nothing-to-undo')
    expect(output.value.historyEffect).toEqual({ pops: '0' })
    expect(output.value.historyContext).toEqual([])
    expect(JSON.stringify(input)).toBe(raw)
  })
})

describe('取消の複合不正に対する既決の拒否順', () => {
  const contract = JSON.parse(
    readFileSync(
      resolve(
        process.cwd(),
        '../contracts/state-transition/undo_cases_v1.json',
      ),
      'utf8',
    ),
  )
  const example = contract.cases.find(
    (row: { request: { history: { stack: unknown[] } } }) =>
      row.request.history.stack.length > 0,
  )
  function input() {
    return JSON.parse(JSON.stringify(example.request))
  }
  function equalSpan(request: ReturnType<typeof input>, location: string) {
    const row = request.history.stack[0]
    const entry = location.startsWith('tail-')
      ? JSON.parse(JSON.stringify(row))
      : row
    if (location.endsWith('state'))
      entry.difference.stateFields['state.count.balls'] = {
        before: '1',
        after: '1',
      }
    else if (location.endsWith('board'))
      entry.difference.scoreboard.hits = { before: '0', after: '0' }
    else {
      request.current.battingOrderBySide = { away: '1', home: '1' }
      entry.difference.battingOrderBySide = {
        away: { before: '1', after: '1' },
      }
    }
    if (location.startsWith('tail-')) request.history.stack.push(entry)
  }
  it.each([
    'head-state',
    'head-board',
    'head-cursor',
    'tail-state',
    'tail-board',
    'tail-cursor',
  ])('%sの同値spanより正準decimal拒否を先に返す', (location) => {
    for (const bad of ['decimal', 'type', 'range', 'valid']) {
      const request = input()
      equalSpan(request, location)
      if (bad !== 'valid') request.current.stateFields['state.inning'] = '01'
      if (bad === 'type')
        request.current.stateFields['state.gameEnded'] = 'false'
      if (bad === 'range')
        request.current.stateFields['state.count.strikes'] = '3'
      expect(
        JSON.parse(domainOperations.applyUndo(JSON.stringify(request))),
      ).toEqual({
        ok: false,
        error: {
          code:
            bad === 'decimal' ? 'INVALID_DECIMAL_INTEGER' : 'INVALID_REQUEST',
        },
      })
    }
  })
  it('同値spanがなくてもdecimal拒否のコードを保持する', () => {
    const request = input()
    request.current.stateFields['state.inning'] = '01'
    expect(
      JSON.parse(domainOperations.applyUndo(JSON.stringify(request))),
    ).toEqual({
      ok: false,
      error: { code: 'INVALID_DECIMAL_INTEGER' },
    })
  })
})
