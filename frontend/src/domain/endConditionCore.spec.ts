import { expect, it } from 'vitest'
import {
  evaluateEndConditionNoEnd,
  readContinuationRules,
  type EndConditionState,
} from './firstPitchContinuation'

const initial: EndConditionState = {
  inning: 1n,
  half: 'top',
  home: 0n,
  away: 0n,
  tiebreakActive: false,
  gameEnded: false,
}
const rules = (change: Record<string, unknown> = {}) => {
  const parsed = readContinuationRules({
    regulationInnings: '9',
    coldConditions: [],
    extensionLimit: null,
    tiebreak: null,
    dh: false,
    ...change,
  })
  if (!parsed.ok) throw new Error('test rule must parse')
  return parsed.value
}

it('旧初球と新ordinaryが消費する同じtyped規則核からR7/R9の実値を返す', () => {
  for (const regulationInnings of ['7', '9']) {
    expect(
      evaluateEndConditionNoEnd(initial, rules({ regulationInnings })),
    ).toEqual({
      regulationInnings: BigInt(regulationInnings),
      inning: 1n,
      half: 'top',
      coldBranches: [],
      drawBranch: 'DRAW-07',
      tiebreakActive: false,
      configuredExtensionLimit: null,
    })
  }
})

it('共通核はcold全段/位置/実得点差で分岐し、固定no-endではない', () => {
  const configured = rules({
    coldConditions: [
      { pointDifference: '10', startInning: '5' },
      { pointDifference: '7', startInning: '7' },
    ],
  })
  const top = { ...initial, inning: 5n, home: 10n }
  expect(evaluateEndConditionNoEnd(top, configured)?.coldBranches).toEqual([
    'COLD-01',
    'COLD-01',
  ])
  expect(
    evaluateEndConditionNoEnd({ ...top, half: 'bottom' }, configured),
  ).toBeNull()
  expect(
    evaluateEndConditionNoEnd({ ...top, home: 0n, away: 10n }, configured)
      ?.coldBranches,
  ).toEqual(['COLD-04', 'COLD-01'])
  expect(
    evaluateEndConditionNoEnd({ ...top, half: 'bottom', home: 9n }, configured)
      ?.coldBranches,
  ).toEqual(['COLD-06', 'COLD-01'])
})

it('共通核が規定終了/有限上限/相関/TBを実評価し、両formatterは判断を複製しない', () => {
  expect(
    evaluateEndConditionNoEnd(
      { ...initial, inning: 9n, half: 'bottom', home: 1n },
      rules(),
    ),
  ).toBeNull()
  expect(
    evaluateEndConditionNoEnd(
      { ...initial, inning: 10n },
      rules({ extensionLimit: '9' }),
    ),
  ).toBeNull()
  expect(
    evaluateEndConditionNoEnd(initial, rules({ extensionLimit: '8' })),
  ).toBeNull()
  expect(
    evaluateEndConditionNoEnd(
      initial,
      rules({ coldConditions: [{ pointDifference: '1', startInning: '10' }] }),
    ),
  ).toBeNull()
  const configured = rules({
    extensionLimit: '12',
    tiebreak: {
      startInning: '10',
      runnerPlacement: '無死一・二塁',
      leadoffRule: '継続打順',
    },
  })
  expect(
    evaluateEndConditionNoEnd({ ...initial, inning: 10n }, configured),
  ).toBeNull()
  expect(
    evaluateEndConditionNoEnd(
      { ...initial, inning: 10n, tiebreakActive: true },
      configured,
    ),
  ).toEqual({
    regulationInnings: 9n,
    inning: 10n,
    half: 'top',
    coldBranches: [],
    drawBranch: 'DRAW-08',
    tiebreakActive: true,
    configuredExtensionLimit: 12n,
  })
})

// 248入力の具体化は入力座標/derivedSourceInputだけから行い、decisionを参照しない。
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  evaluateEndCondition,
  validEndRules,
  type EndBoundary,
} from './endConditionCore'
import type { ContinuationRules } from './firstPitchContinuation'
const gameEnd = JSON.parse(
  readFileSync(
    resolve('../contracts/state-transition/game_end_contract_v1.json'),
    'utf8',
  ),
) as {
  decisionRows: Array<{ branchId: string; remarks: string }>
  cases: Array<{
    caseId: string
    branchId: string
    inputCoordinate: Record<string, unknown>
    derivedSourceInput: Record<string, unknown>
    decision: unknown
  }>
  validationErrors: Array<{ axisId: string; invalidValue: unknown }>
}
function adapted(c: (typeof gameEnd.cases)[number]): {
  state: EndConditionState
  rules: ContinuationRules
  boundary: EndBoundary
} {
  const coordinate = c.inputCoordinate,
    input = c.derivedSourceInput
  const regulation = BigInt(coordinate['gameEnd.regulationInnings'] as number)
  const extension = coordinate['gameEnd.extensionLimit']
  let limit: bigint | null = null
  if (extension === 'finite:R') limit = regulation
  else if (extension === 'finite:R+1') limit = regulation + 1n
  else if (extension === 'finite:99') limit = 99n
  else if (extension !== 'none') throw Error('unresolved actual input')
  const half = input['state.half'] as 'top' | 'bottom',
    inning = BigInt(input['state.inning'] as number)
  const score = input['state.score'] as { home: number; away: number }
  const state: EndConditionState = {
    inning,
    half,
    home: BigInt(score.home),
    away: BigInt(score.away),
    tiebreakActive: coordinate['state.tiebreakActive'] as boolean,
    gameEnded: coordinate['state.gameEnded'] as boolean,
  }
  const cold = input['gameEnd.coldConditions'] as Array<{
    pointDifference: number
    startInning: number
  }>
  const rules: ContinuationRules = {
    regulationInnings: regulation,
    extensionLimit: limit,
    coldConditions: cold.map((x) => ({
      pointDifference: BigInt(x.pointDifference),
      startInning: BigInt(x.startInning),
    })),
    dh: false,
    tiebreak:
      coordinate['gameEnd.tiebreak'] === 'none'
        ? null
        : {
            startInning: regulation + 1n,
            runnerPlacement: 'first-second',
            leadoffRule: 'designated',
          },
  }
  const boundary: EndBoundary = { completedHalf: null, completedInning: null }
  // rowの規範remarksは入力境界の出典。decision/outcome/期待flagは参照しない。
  // coverageイベントは追加軸であり、最終表/裏完了というrow前提を上書きしない。
  const row = gameEnd.decisionRows.find((r) => r.branchId === c.branchId)
  if (!row) throw Error('missing normative row')
  if (row.remarks.includes('攻守交代後の判定位置')) {
    expect(half).toBe('top')
    expect(coordinate['state.outs']).toBe(0)
    boundary.completedHalf = 'bottom'
    boundary.completedInning = inning - 1n
  } else if (row.remarks.includes('表完了')) {
    expect(half).toBe('bottom')
    expect(coordinate['state.outs']).toBe(0)
    boundary.completedHalf = 'top'
    boundary.completedInning = inning
  } else if (
    !row.remarks.includes('確定プレイ') &&
    !row.remarks.includes('本塁打プレイ')
  )
    throw Error('unresolved normative boundary')
  return { state, rules, boundary }
}
it.each(gameEnd.cases)('$caseId 一般T2既248の全decision', (c) => {
  const a = adapted(c)
  expect(evaluateEndCondition(a.state, a.rules, a.boundary)).toStrictEqual(
    c.decision,
  )
})
it.each(gameEnd.validationErrors)('$axisId $invalidValue 既12設定拒否', (c) => {
  const r: ContinuationRules = {
    regulationInnings: 9n,
    coldConditions: [],
    extensionLimit: 10n,
    tiebreak: null,
    dh: false,
  }
  const value = c.invalidValue
  if (c.axisId === 'gameEnd.regulationInnings')
    r.regulationInnings = BigInt(value as number)
  else if (value === 'tier-count:17')
    r.coldConditions = Array.from({ length: 17 }, () => ({
      pointDifference: 7n,
      startInning: 7n,
    }))
  else if (value === 'point-difference:0')
    r.coldConditions = [{ pointDifference: 0n, startInning: 7n }]
  else if (value === 'point-difference:100')
    r.coldConditions = [{ pointDifference: 100n, startInning: 7n }]
  else if (value === 'start-inning:0')
    r.coldConditions = [{ pointDifference: 7n, startInning: 0n }]
  else if (value === 'start-inning:100')
    r.coldConditions = [{ pointDifference: 7n, startInning: 100n }]
  else if (value === 'finite:R-1') r.extensionLimit = 8n
  else if (value === 'finite:100') r.extensionLimit = 100n
  else if (value === 'start:R')
    r.tiebreak = {
      startInning: 9n,
      runnerPlacement: 'first-second',
      leadoffRule: 'designated',
    }
  else if (value === 'start:L+1-when-finite')
    r.tiebreak = {
      startInning: 11n,
      runnerPlacement: 'first-second',
      leadoffRule: 'designated',
    }
  else if (value === 'start:100')
    r.tiebreak = {
      startInning: 100n,
      runnerPlacement: 'first-second',
      leadoffRule: 'designated',
    }
  else throw Error('unresolved invalid input')
  expect(validEndRules(r)).toBe(false)
  expect(
    evaluateEndCondition(initial, r, {
      completedHalf: null,
      completedInning: null,
    }),
  ).toBeNull()
})

it('7回選択は7回裏完了で終了し、選択した延長上限だけで引き分け/継続する', () => {
  const completed = (inning: bigint): EndBoundary => ({
    completedHalf: 'bottom',
    completedInning: inning,
  })
  const sevenNoExtra = rules({
    regulationInnings: '7',
    extensionLimit: '7',
  })
  expect(
    evaluateEndCondition(
      { ...initial, inning: 8n, half: 'top', home: 3n, away: 1n },
      sevenNoExtra,
      completed(7n),
    ),
  ).toMatchObject({ outcome: 'normal-end', endConditionDetected: true })
  expect(
    evaluateEndCondition(
      { ...initial, inning: 8n, half: 'top', home: 2n, away: 2n },
      sevenNoExtra,
      completed(7n),
    ),
  ).toMatchObject({ outcome: 'limit-draw', endConditionDetected: true })

  const sevenNine = rules({
    regulationInnings: '7',
    extensionLimit: '9',
  })
  expect(
    evaluateEndCondition(
      { ...initial, inning: 8n, half: 'top', home: 2n, away: 2n },
      sevenNine,
      completed(7n),
    ),
  ).toMatchObject({ outcome: 'extra-continue', endConditionDetected: false })
  expect(
    evaluateEndCondition(
      { ...initial, inning: 10n, half: 'top', home: 2n, away: 2n },
      sevenNine,
      completed(9n),
    ),
  ).toMatchObject({ outcome: 'limit-draw', endConditionDetected: true })

  const sevenTwelve = rules({
    regulationInnings: '7',
    extensionLimit: '12',
  })
  expect(
    evaluateEndCondition(
      { ...initial, inning: 10n, half: 'top', home: 2n, away: 2n },
      sevenTwelve,
      completed(9n),
    ),
  ).toMatchObject({ outcome: 'extra-continue', endConditionDetected: false })
  expect(
    evaluateEndCondition(
      { ...initial, inning: 13n, half: 'top', home: 2n, away: 2n },
      sevenTwelve,
      completed(12n),
    ),
  ).toMatchObject({ outcome: 'limit-draw', endConditionDetected: true })

  // 未選択時の9回既定は従来どおり9回裏完了で引き分け判定する。
  expect(
    evaluateEndCondition(
      { ...initial, inning: 10n, half: 'top', home: 2n, away: 2n },
      rules({ extensionLimit: '9' }),
      completed(9n),
    ),
  ).toMatchObject({ outcome: 'limit-draw', endConditionDetected: true })
})

it('COLD03: 裏の有効得点playで第三アウトも確定していてもafter表へ取り落とさない', () => {
  const configured = rules({
    coldConditions: [{ pointDifference: '7', startInning: '7' }],
  })
  const before = {
    ...initial,
    inning: 7n,
    half: 'bottom' as const,
    home: 0n,
    away: 0n,
  }
  const beforeOuts = 2n
  const afterOuts = 0n
  const state = { ...before, inning: 8n, half: 'top' as const, home: 7n }
  expect(beforeOuts).toBe(2n)
  expect(afterOuts).toBe(0n)
  expect(
    evaluateEndCondition(state, configured, {
      completedHalf: before.half,
      completedInning: before.inning,
    }),
  ).toStrictEqual({
    outcome: 'cold-end',
    endConditionDetected: true,
    lockFurtherPlayInput: true,
    promptEndDeclaration: true,
    automaticallyEndsGame: false,
    xMark: 'recorded-score',
  })
  // 同じafter位置だけで半回完了を捏造せず、旧open wrapperは旧返値を保持する。
  expect(evaluateEndConditionNoEnd(state, configured)).not.toBeNull()
})

it('D01=Bは裏のプレイ中のサヨナラとコールド同時成立だけを優先する', () => {
  const configured = rules({
    coldConditions: [{ pointDifference: '1', startInning: '7' }],
    extensionLimit: '9',
  })
  const finalBottom = {
    ...initial,
    inning: 9n,
    half: 'bottom' as const,
    home: 1n,
  }
  const midPlay = { completedHalf: null, completedInning: null }
  const ended = (outcome: string, xMark: string) => ({
    outcome,
    endConditionDetected: true,
    lockFurtherPlayInput: true,
    promptEndDeclaration: true,
    automaticallyEndsGame: false,
    xMark,
  })
  expect(evaluateEndCondition(finalBottom, configured, midPlay)).toEqual({
    outcome: 'walk-off',
    endConditionDetected: true,
    lockFurtherPlayInput: true,
    promptEndDeclaration: true,
    automaticallyEndsGame: false,
    xMark: 'recorded-score',
  })
  // 表完了の未実施裏はmid-bottomではなく、既cold/Xを維持する。
  expect(
    evaluateEndCondition(finalBottom, configured, {
      completedHalf: 'top',
      completedInning: 9n,
    }),
  ).toStrictEqual(ended('cold-end', 'x-mark'))
  expect(
    evaluateEndCondition(finalBottom, rules(), {
      completedHalf: 'top',
      completedInning: 9n,
    }),
  ).toStrictEqual(ended('normal-end', 'x-mark'))
  // E08: 裏完了境界でのcold優先をnormal-endへ反転しない。
  expect(
    evaluateEndCondition(
      { ...finalBottom, inning: 10n, half: 'top' },
      configured,
      { completedHalf: 'bottom', completedInning: 9n },
    ),
  ).toStrictEqual(ended('cold-end', 'recorded-score'))
  // OUT3で無効となった得点を推測復元せず、供給された有効0-0を使う。
  expect(
    evaluateEndCondition(
      { ...initial, inning: 10n },
      rules({ extensionLimit: '9' }),
      { completedHalf: 'bottom', completedInning: 9n },
    ),
  ).toStrictEqual(ended('limit-draw', 'recorded-score'))
  expect(
    evaluateEndCondition(
      { ...initial, inning: 5n, half: 'bottom', home: 5n },
      rules({ coldConditions: [{ pointDifference: '5', startInning: '5' }] }),
      midPlay,
    ),
  ).toStrictEqual(ended('cold-end', 'recorded-score'))
})
