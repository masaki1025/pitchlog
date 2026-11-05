import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { describe, expect, it } from 'vitest'

const source = readFileSync(
  resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
  'utf8',
)
const context = createContext({})
new Script(source).runInContext(context, { timeout: 1000 })
const api = context.PitchlogDomain as {
  applyUndo: (request: string) => string
}

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

describe('ビルド済み artifact の取消計算', () => {
  it('凍結された公開表から 1 球の取消を実行する', () => {
    const current = structuredClone(initial)
    current.stateFields['state.count.balls'] = '1'
    const response = JSON.parse(
      api.applyUndo(JSON.stringify({ current, history: { stack: [ball] } })),
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

  it('空スタックは nothing-to-undo を返す', () => {
    const response = JSON.parse(
      api.applyUndo(
        JSON.stringify({ current: initial, history: { stack: [] } }),
      ),
    )
    expect(response.value.operationResult).toBe('nothing-to-undo')
    expect(response.value.historyEffect).toEqual({ pops: '0' })
  })
})
