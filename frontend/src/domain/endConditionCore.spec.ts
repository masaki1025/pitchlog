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
