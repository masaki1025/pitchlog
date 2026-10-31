import type { Request } from '../../../contracts/state-transition/lineup_play_prefix_v1'
type Mutable<T> = {
  -readonly [P in keyof T]: T[P] extends object ? Mutable<T[P]> : T[P]
}
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'
import { domainOperations } from './publicApi'
const vectors = JSON.parse(
  readFileSync(
    resolve('../contracts/state-transition/lineup_play_prefix_cases_v1.json'),
    'utf8',
  ),
) as {
  cases: Array<{ caseId: string; request: unknown; expected: unknown }>
  rejectionCases: Array<{
    caseId: string
    baseCaseId: string
    replace: { path: string; value: unknown }
    expected: unknown
  }>
}
const invoke = (request: unknown) =>
  JSON.parse(
    domainOperations.deriveLineupPlayPrefixWithContinuation(
      JSON.stringify(request),
    ),
  )
describe('v3両cursor/実名簿の閉数学接続', () => {
  it.each(vectors.cases)('$caseId 全応答', (c) => {
    expect(invoke(c.request)).toStrictEqual(c.expected)
  })
  it.each(vectors.rejectionCases)('$caseId 閉拒否', (c) => {
    const base = vectors.cases.find((x) => x.caseId === c.baseCaseId)!
    const request = structuredClone(base.request) as Record<string, unknown>
    const segments = c.replace.path.split('/').filter(Boolean)
    const last = segments.pop()!
    let view = request
    for (const key of segments) view = view[key] as Record<string, unknown>
    view[last] = c.replace.value
    expect(invoke(request)).toStrictEqual(c.expected)
  })
  it('未知/重複/非有限JSONを成功にしない', () => {
    const c = vectors.cases[0]!
    expect(invoke({ ...(c.request as object), unknown: true })).toStrictEqual({
      ok: false,
      error: { code: 'INVALID_REQUEST' },
    })
    expect(
      JSON.parse(
        domainOperations.deriveLineupPlayPrefixWithContinuation(
          '{"version":"3","version":"3"}',
        ),
      ),
    ).toStrictEqual({ ok: false, error: { code: 'INVALID_JSON' } })
    expect(
      JSON.parse(
        domainOperations.deriveLineupPlayPrefixWithContinuation('{"v":NaN}'),
      ),
    ).toStrictEqual({ ok: false, error: { code: 'INVALID_JSON' } })
  })
})

it.each([
  {
    name: '最終表の未実施裏',
    inning: '9',
    half: 'top' as const,
    score: { home: '7', away: '4' },
    limit: '9',
    cold: [],
    tb: null,
    outcome: 'normal-end',
    mark: 'x-mark',
    required: false,
  },
  {
    name: '有限最終裏同点',
    inning: '9',
    half: 'bottom' as const,
    score: { home: '4', away: '4' },
    limit: '9',
    cold: [],
    tb: null,
    outcome: 'limit-draw',
    mark: 'recorded-score',
    required: false,
  },
  {
    name: 'TB初回は配置を自動実行しない',
    inning: '9',
    half: 'bottom' as const,
    score: { home: '4', away: '4' },
    limit: '99',
    cold: [],
    tb: {
      startInning: '10',
      runnerPlacement: 'first-second',
      leadoffRule: 'designated',
    },
    outcome: 'tiebreak-continue',
    mark: 'recorded-score',
    required: true,
  },
  {
    name: 'COLD05: 裏の第三アウトで先攻coldを検知',
    inning: '7',
    half: 'bottom' as const,
    score: { home: '0', away: '7' },
    limit: '9',
    cold: [{ pointDifference: '7', startInning: '7' }],
    tb: null,
    outcome: 'cold-end',
    mark: 'recorded-score',
    required: false,
  },
])('$name 実T1第三アウトから終了境界を形成する', (row) => {
  const r = structuredClone(vectors.cases[2]!.request) as Mutable<Request>
  r.rules.extensionLimit = row.limit
  r.rules.tiebreak = row.tb
  r.rules.coldConditions = row.cold
  r.t1.before.stateFields['state.half'] = row.half
  r.t1.before.stateFields['state.inning'] = row.inning
  r.t1.before.stateFields['state.score'] = row.score
  r.t1.before.stateFields['state.runners'] = 'empty'
  r.t1.before.scoreboard.inningScores = row.score
  const slot =
    row.half === 'top'
      ? r.t1.before.battingOrderBySide.away
      : r.t1.before.battingOrderBySide.home
  r.t1.before.stateFields['state.battingOrder'] = slot
  r.source.after = structuredClone(r.t1.before)
  r.source.rules = structuredClone(r.rules)
  r.source.runners = []
  const batting = r.source.lineup[row.half === 'top' ? 'away' : 'home']
  const fielding = r.source.lineup[row.half === 'top' ? 'home' : 'away']
  r.source.participants = {
    batterId: batting.battingOrder[slot],
    pitcherId: fielding.pitcherId,
    catcherId: fielding.catcherId,
    battingOrder: slot,
  }
  if (r.source.t2 === null) throw Error('fixture prior T2 required')
  Object.assign(r.source.t2.facts, {
    beforeInning: row.inning,
    beforeHalf: row.half,
    beforeOuts: '2',
    afterInning: row.inning,
    afterHalf: row.half,
    afterOuts: '2',
    halfCompleted: false,
    outsUnchanged: true,
  })
  const response = invoke(r)
  expect(response.ok).toBe(true)
  expect(response.value.t2.decision.outcome).toBe(row.outcome)
  expect(response.value.t2.decision.xMark).toBe(row.mark)
  expect(response.value.t2.tiebreakStartRequired).toBe(row.required)
  expect(response.value.t2.facts.halfCompleted).toBe(true)
  expect(response.value.t2.facts.outsUnchanged).toBe(false)
  expect(response.value.t1.after.stateFields['state.gameEnded']).toBe(false)
  const next = structuredClone(r)
  next.prefixRef = response.value.nextPrefixRef
  next.t1.before = response.value.t1.after
  next.t1.resultId = 'batting-result.called-pitch'
  next.nextCheckpoint = {
    id: '10000000-0000-0000-0000-000000000099',
    revision: '3',
    digest: 'f'.repeat(64),
  }
  next.source = {
    ...next.source,
    kind: 'evaluated-prefix-v3',
    prefixRef: next.prefixRef,
    after: next.t1.before,
    t2: response.value.t2,
    historyDepth: next.prefixRef.length,
    playCount: next.prefixRef.length,
    lastSource: response.value.playIdentity,
    participants: response.value.participants,
    runners: response.value.runners,
    responsibility: response.value.nextResponsibility,
    provenance: {
      kind: 'confirmed-prefix',
      checkpoint: next.prefixRef.checkpoint,
      sourceIdentity: response.value.playIdentity,
      historyDepth: next.prefixRef.length,
    },
  }
  expect(invoke(next).ok).toBe(false)
})

it('prior factsのPositive inning0を実公開口が拒否する', () => {
  const r = structuredClone(vectors.cases[0]!.request) as Mutable<Request>
  if (r.source.t2 === null) throw Error('fixture prior T2 required')
  r.source.t2.facts.beforeInning = '0'
  expect(invoke(r)).toStrictEqual({
    ok: false,
    error: { code: 'PREFIX_SOURCE_MISMATCH' },
  })
})
