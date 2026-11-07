import { expect, it } from 'vitest'
import { deriveLineupPitch, deriveTerminal } from './state'
import { domainOperations } from './publicApi'
import { prepareLineupContinuation } from './lineupPlayPrefixContinuation'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Scoreboard, StateFields } from './stateTypes'

/** 既契約 ST-MATRIX-9971ebafa8bb7fda の入力座標。 */
const before: StateFields = {
  half: 'top',
  inning: 1n,
  outs: 0n,
  strikes: 0n,
  balls: 0n,
  runners: 'first-third',
  battingOrder: 1n,
  tiebreakActive: false,
  gameEnded: false,
  home: 0n,
  away: 0n,
}
const board: Scoreboard = {
  home: 0n,
  away: 0n,
  hits: 0n,
  errors: 0n,
  strikeouts: 0n,
  walks: 0n,
}
const cursors = { away: 1n, home: 1n }

it('申告敬遠は一三塁を既四球核で進め、今回の投球数だけ0にする', () => {
  const value = deriveLineupPitch(
    before,
    board,
    'batting-result.intentional-walk',
    'non-pitch-event',
    cursors,
  )
  expect(value).not.toBeNull()
  expect(value?.countEffect).toEqual({
    strikes: { kind: 'reset', value: 0n },
    balls: { kind: 'reset', value: 0n },
  })
  expect(value?.plateAppearanceEnded).toBe(true)
  expect(value?.batterDestination).toEqual({ kind: 'reach', base: 1n })
  expect(value?.runnerDefaultAdvance).toEqual({
    first: { modality: 'forced', destination: 2n },
    second: { modality: 'not-applicable', destination: null },
    third: { modality: 'hold', destination: null },
  })
  expect(value?.outEffect).toEqual({ count: 0n, targets: [] })
  expect(value?.statFlags).toEqual({
    投球回算入アウト: false,
    投球数: false,
    奪三振: false,
    与四球: true,
    与死球: false,
    被安打: false,
    被本塁打: false,
    失点: false,
    失策: false,
    打席: true,
    打数: false,
    安打: false,
    本塁打: false,
    塁打: false,
    犠打: false,
    犠飛: false,
    四球: true,
    死球: false,
    三振: false,
    打撃妨害出塁: false,
    走塁妨害出塁: false,
    得点: false,
    打点: false,
  })
  expect(value?.after.stateFields).toEqual({
    ...before,
    runners: 'loaded',
    battingOrder: 2n,
  })
  expect(value?.after.scoreboard).toEqual({ ...board, walks: 1n })
  expect(value?.after.battingOrderBySide).toEqual({ away: 2n, home: 1n })
})

it('旧入口・投球偽装・未知非投球・未確定状態を拒否する', () => {
  const result = 'batting-result.intentional-walk'
  expect(deriveTerminal(before, board, result, 'non-pitch-event')).toBeNull()
  expect(
    deriveLineupPitch(before, board, result, 'pitch-event', cursors),
  ).toBeNull()
  expect(
    deriveLineupPitch(
      before,
      board,
      'batting-result.walk',
      'non-pitch-event',
      cursors,
    ),
  ).toBeNull()
  for (const changed of [
    { ...before, runners: 'empty' as const },
    { ...before, outs: 1n },
    { ...before, balls: 1n },
    { ...before, strikes: 1n },
    { ...before, gameEnded: true },
  ])
    expect(
      deriveLineupPitch(changed, board, result, 'non-pitch-event', cursors),
    ).toBeNull()
})

it('既v3継続の同一T1/T2核が一三塁の申告敬遠を次sourceへ接ぐ', () => {
  const vectors = JSON.parse(
    readFileSync(
      resolve('../contracts/state-transition/lineup_play_prefix_cases_v1.json'),
      'utf8',
    ),
  ) as { cases: Array<{ caseId: string; request: Record<string, unknown> }> }
  const original = vectors.cases.find(
    (item) => item.caseId === 'V3-STRIKEOUT-1-B1-O2',
  )
  expect(original).toBeDefined()
  const request = structuredClone(original!.request)
  const t1 = request.t1 as Record<string, unknown>
  const source = request.source as Record<string, unknown>
  const beforeState = (t1.before as Record<string, unknown>)
    .stateFields as Record<string, unknown>
  const sourceState = (source.after as Record<string, unknown>)
    .stateFields as Record<string, unknown>
  for (const state of [beforeState, sourceState]) {
    state['state.count.strikes'] = '0'
    state['state.count.balls'] = '0'
    state['state.outs'] = '0'
  }
  const priorT2 = source.t2 as Record<string, unknown>
  const priorFacts = priorT2.facts as Record<string, unknown>
  priorFacts.afterOuts = '0'
  t1.resultId = 'batting-result.intentional-walk'
  t1.pitchEventKind = 'non-pitch-event'
  const prepared = prepareLineupContinuation(JSON.stringify(request))
  expect(prepared.ok, JSON.stringify(prepared)).toBe(true)
  const reply = JSON.parse(
    domainOperations.deriveLineupPlayPrefixWithContinuation(
      JSON.stringify(request),
    ),
  ) as Record<string, unknown>
  expect(reply.ok, JSON.stringify(reply)).toBe(true)
  const value = reply.value as Record<string, unknown>
  const t1Result = value.t1 as Record<string, unknown>
  expect((t1Result.statFlags as Record<string, unknown>).投球数).toBe(false)
  expect((t1Result.statFlags as Record<string, unknown>).四球).toBe(true)
  expect(
    (value.runners as Array<Record<string, unknown>>).map(
      (runner) => runner.base,
    ),
  ).toEqual(['2', '3', '1'])
})
