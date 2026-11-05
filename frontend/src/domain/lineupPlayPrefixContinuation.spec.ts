import { createHash } from 'node:crypto'
import type { Request } from '../../../contracts/state-transition/lineup_play_prefix_v1'
import type {
  NonplayRequest,
  NonplayValue,
} from '../../../contracts/state-transition/lineup_play_prefix_v1'
import type {
  Source as NonplaySource,
  RestoreContext,
} from '../../../contracts/state-transition/nonplay_prefix_bridge_v1'
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

it('D1/D2/適用水位を同じcounterへ潰さず正規要求へ束縛する', () => {
  const fixture = structuredClone(vectors.cases[0]!.request) as Mutable<Request>
  fixture.source.position = { d1: '101', d2: '100001', appliedWatermark: '100' }
  const result = invoke(fixture)
  expect(result.ok).toBe(true)
  expect(result.value.sourcePosition).toStrictEqual(fixture.source.position)
  for (const position of [
    { d1: '100', d2: '100001', appliedWatermark: '100' },
    { d1: '101', d2: '0', appliedWatermark: '100' },
  ]) {
    fixture.source.position = position
    expect(invoke(fixture).ok).toBe(false)
  }
})

// 新規期待はaccepted Source/独立ball手計算から形成し、runtime出力を採取しない。
const nonplayBridge = JSON.parse(
  readFileSync(
    resolve(
      '../contracts/state-transition/nonplay_prefix_bridge_cases_v1.json',
    ),
    'utf8',
  ),
) as {
  crossGenerationCase: { source: NonplaySource }
  steps: Array<{
    caseId: string
    source: NonplaySource
    event: {
      state_diff: { difference: { statFlags: Record<string, boolean> } }
    } | null
  }>
}
/** hashは数学実装ではなく、明示派生した試験Sourceのcontentだけを正規封印する。 */
function canonicalNonplayTest(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalNonplayTest)
  if (value !== null && typeof value === 'object') {
    const o = value as Record<string, unknown>
    return Object.fromEntries(
      Object.keys(o)
        .sort()
        .map((key) => [key, canonicalNonplayTest(o[key])]),
    )
  }
  return value
}
function sealNonplayTestContent(value: unknown): string {
  return createHash('sha256')
    .update(JSON.stringify(canonicalNonplayTest(value)), 'utf8')
    .digest('hex')
}
function nonplayRequest(
  index: number,
  linked = false,
): Mutable<NonplayRequest> {
  const source = structuredClone(
    linked
      ? nonplayBridge.crossGenerationCase.source
      : nonplayBridge.steps[index]!.source,
  ) as Mutable<NonplaySource>
  const validLineup = (
    vectors.cases[0]!.request as {
      source: { lineup: unknown; participants: unknown; rules: unknown }
    }
  ).source
  const replaceContext = (v: Mutable<RestoreContext>) => {
    v.rules = structuredClone(
      validLineup.rules,
    ) as Mutable<RestoreContext>['rules']
    v.lineup = structuredClone(
      validLineup.lineup,
    ) as Mutable<RestoreContext>['lineup']
    v.participants = structuredClone(
      validLineup.participants,
    ) as Mutable<RestoreContext>['participants']
    v.rulesDigest = sealNonplayTestContent(v.rules)
    v.layoutDigest = sealNonplayTestContent(v.lineup)
    v.rosterDigest = v.layoutDigest
  }
  replaceContext(source.checkpoint.content.restored)
  for (const frame of source.activeStack) {
    replaceContext(frame.beforeContext)
    replaceContext(frame.afterContext)
  }
  const content = source.checkpoint.content
  source.checkpoint.ref.digest = sealNonplayTestContent(content)
  return {
    version: 'nonplay-continuation-v1',
    prefixRef: structuredClone(source.checkpoint.ref),
    rules: structuredClone(content.restored.rules),
    t1: {
      eventKind: 'batting-result',
      resultId: 'batting-result.ball',
      pitchEventKind: 'pitch-event',
      before: structuredClone(content.restored.current),
    },
    source,
    playIdentity: {
      eventId: '00000000-0000-4000-8000-0000000008a1',
      d5: '00000000-0000-4000-8000-0000000008a2',
      playId: '00000000-0000-4000-8000-0000000008a3',
    },
    nextCheckpoint: {
      id: '00000000-0000-4000-8000-0000000008a4',
      revision: String(BigInt(source.checkpoint.ref.revision) + 1n),
      digest: 'f'.repeat(64),
    },
    sourcePosition: {
      d1: String(BigInt(content.d3) + 1n),
      d2: '3072',
      appliedWatermark: content.d3,
    },
  }
}
function nonplayBallExpected(
  request: Mutable<NonplayRequest>,
  called = false,
): unknown {
  const source = request.source.checkpoint.content.restored
  const before = source.current
  const after = structuredClone(before)
  const field = called ? 'state.count.strikes' : 'state.count.balls'
  const old = before.stateFields[field] as string
  const next: Record<string, string> = { '0': '1', '1': '2', '2': '3' }
  Object.assign(after.stateFields, { [field]: next[old] })
  const flags = structuredClone(
    nonplayBridge.steps[1]!.event!.state_diff.difference.statFlags,
  )
  const notApplicable = { modality: 'not-applicable', destination: null }
  return {
    ok: true,
    value: {
      t1: {
        countEffect: {
          strikes: called
            ? { kind: 'delta', value: '1' }
            : { kind: 'unchanged' },
          balls: called ? { kind: 'unchanged' } : { kind: 'delta', value: '1' },
        },
        plateAppearanceEnded: false,
        batterDestination: { kind: 'continue' },
        runnerDefaultAdvance: {
          first: notApplicable,
          second: notApplicable,
          third: notApplicable,
        },
        outEffect: { count: '0', targets: [] },
        statFlags: flags,
        after,
      },
      t2: {
        kind: 'evaluated-end-condition',
        scope: 'play-prefix-v3',
        evaluation_point: 'post-play',
        facts: {
          beforeInning: '1',
          beforeHalf: 'top',
          beforeOuts: '0',
          afterInning: '1',
          afterHalf: 'top',
          afterOuts: '0',
          halfCompleted: false,
          outsUnchanged: true,
          scoreUnchanged: true,
          priorOpen: true,
        },
        decision: {
          outcome: 'no-end',
          endConditionDetected: false,
          lockFurtherPlayInput: false,
          promptEndDeclaration: false,
          automaticallyEndsGame: false,
          xMark: 'recorded-score',
        },
        tiebreakStartRequired: false,
      },
      newHistoryEntry: {
        kind: 'confirmed-play',
        difference: {
          stateFields: {
            [field]: { before: old, after: next[old] },
          },
          scoreboard: {},
          statFlags: flags,
          battingOrderBySide: {},
        },
      },
      previousPrefixRef: request.prefixRef,
      nextPrefixRef: request.nextCheckpoint,
      runners: source.runners,
      beforeParticipants: source.participants,
      participants: source.participants,
      lineup: source.lineup,
      rosterDigest: source.rosterDigest,
      responsibility: source.responsibility,
      nextResponsibility: source.responsibility,
      playIdentity: request.playIdentity,
      sourcePosition: request.sourcePosition,
      executionArtifactSha256:
        request.source.checkpoint.content.executionArtifactSha256,
    },
  }
}
describe('真正nonplay Sourceを偽装しない次球提案', () => {
  it.each([0, 1, 2, 3, 4, 5])('三headの段階%sから独立全応答', (index) => {
    const r = nonplayRequest(index)
    const saved = structuredClone(r)
    expect(invoke(r)).toStrictEqual(nonplayBallExpected(r))
    expect(r).toStrictEqual(saved)
  })
  it('D3=4/active0/history44/epoch7/physical3を独立保持して実D2=3072を返す', () => {
    const r = nonplayRequest(4)
    expect(r.source.checkpoint.content.d3).toBe('4')
    expect(r.source.checkpoint.content.activeDepth).toBe('0')
    expect(r.source.checkpoint.content.historyVersion).toBe('44')
    expect(r.source.checkpoint.content.storageHistoryEpoch).toBe('7')
    expect(r.source.checkpoint.content.nextPhysicalPlayNumber).toBe('3')
    expect(invoke(r)).toStrictEqual(nonplayBallExpected(r))
  })
  it.each([
    'unknown-source',
    'unknown-content',
    'depth',
    'head',
    'context',
    'd3',
    'watermark',
    'd1',
    'd2',
    'ref',
    'next-revision',
    'old-version',
    'own-gen-empty',
    'fingerprint',
    'tail-missing',
    'tail-unknown',
    'typed-bool',
  ])('%sを閉拒否', (mutation) => {
    const r = nonplayRequest(2)
    const c = r.source.checkpoint.content
    if (mutation === 'unknown-source') Object.assign(r.source, { extra: true })
    if (mutation === 'unknown-content') Object.assign(c, { extra: true })
    if (mutation === 'depth') c.activeDepth = '1'
    if (mutation === 'head') c.activeHead = null
    if (mutation === 'context')
      c.restored.current.stateFields['state.count.balls'] = '0'
    if (mutation === 'd3') c.d3 = '3'
    if (mutation === 'watermark') r.sourcePosition.appliedWatermark = '0'
    if (mutation === 'd1') r.sourcePosition.d1 = '1'
    if (mutation === 'd2') r.sourcePosition.d2 = '0'
    if (mutation === 'ref') r.prefixRef.digest = '0'.repeat(64)
    if (mutation === 'next-revision') r.nextCheckpoint.revision = '1'
    if (mutation === 'old-version') Object.assign(r, { version: '3' })
    if (mutation === 'own-gen-empty') c.scope.generation = ''
    if (mutation === 'fingerprint')
      Object.assign(c.d1Head!.source, {
        fingerprint: 'wire-v1:' + '0'.repeat(63),
      })
    if (mutation === 'tail-missing') r.source.activeStack.pop()
    if (mutation === 'tail-unknown')
      Object.assign(r.source.activeStack[1]!.historyEntry, { unknown: true })
    if (mutation === 'typed-bool')
      Object.assign(c.restored.current.stateFields, { 'state.gameEnded': 0 })
    expect(invoke(r).ok).toBe(false)
  })
  it('真正連結を別層へ残し、own D3=0/世代2でもprior世代のactive2を保持する', () => {
    const r = nonplayRequest(2, true)
    expect(r.source.checkpoint.content.d3).toBe('0')
    expect(r.source.checkpoint.content.scope.generation).toBe('2')
    expect(r.source.checkpoint.content.activeDepth).toBe('2')
    expect(r.sourcePosition.d1).toBe('1')
    expect(invoke(r)).toStrictEqual(nonplayBallExpected(r))
  })
})

it('nonplayの5001桁D3/revisionへ新capを置かず全提案値を保持する', () => {
  const r = nonplayRequest(4)
  const big = '1' + '0'.repeat(5000)
  const plus = '1' + '0'.repeat(4999) + '1'
  const c = r.source.checkpoint.content
  c.d3 = big
  Object.assign(c.d1Head!.source, { d1: big })
  if (c.projectionHead.kind === 'd1-event')
    Object.assign(c.projectionHead.source, { d1: big })
  r.sourcePosition.d1 = plus
  r.sourcePosition.appliedWatermark = big
  c.historyVersion = big
  r.source.checkpoint.ref.revision = big
  r.prefixRef.revision = big
  r.nextCheckpoint.revision = plus
  r.source.checkpoint.ref.digest = sealNonplayTestContent(c)
  r.prefixRef.digest = r.source.checkpoint.ref.digest
  expect(invoke(r)).toStrictEqual(nonplayBallExpected(r))
})
it('有効shapeでも全tailの差分/前後観測不一致を拒否する', () => {
  const r = nonplayRequest(2)
  const span =
    r.source.activeStack[1]!.historyEntry.difference.stateFields[
      'state.count.balls'
    ]!
  Object.assign(span, { after: '2' })
  expect(invoke(r)).toStrictEqual({
    ok: false,
    error: { code: 'PREFIX_SOURCE_MISMATCH' },
  })
})

it('反映1: 跨世代の返却after/historyをそのまま次Sourceへ積み次々球も全値一致', () => {
  const r = nonplayRequest(2, true)
  const first = invoke(r)
  expect(first).toStrictEqual(nonplayBallExpected(r))
  const v = first.value as Mutable<NonplayValue>
  const content = r.source.checkpoint.content
  const before = structuredClone(content.restored)
  const after = structuredClone(before)
  after.current = structuredClone(
    v.t1.after,
  ) as Mutable<RestoreContext>['current']
  after.participants = structuredClone(v.participants)
  after.runners = structuredClone(v.runners)
  after.responsibility = structuredClone(v.nextResponsibility)
  after.lastPlayEvaluation = structuredClone(v.t2)
  const event = {
    eventId: r.playIdentity.eventId,
    gameId: content.scope.gameId,
    generation: content.scope.generation,
    d1: r.sourcePosition.d1,
    d5: r.playIdentity.d5,
    fingerprint: 'wire-v1:' + 'b'.repeat(64),
    eventKind: 'play_input' as const,
  }
  const play = {
    source: event,
    playId: r.playIdentity.playId,
    d2: r.sourcePosition.d2,
    physicalPlayNumber: content.nextPhysicalPlayNumber,
  }
  r.source.activeStack.unshift({
    play,
    historyEntry: structuredClone(v.newHistoryEntry),
    beforeContext: before,
    afterContext: after,
  })
  content.restored = after
  content.d3 = event.d1
  content.d1Head = { kind: 'accepted-event', source: structuredClone(event) }
  content.projectionHead = { kind: 'd1-event', source: structuredClone(event) }
  content.activeHead = structuredClone(play)
  content.activeDepth = '3'
  content.historyVersion = String(BigInt(content.historyVersion) + 1n)
  content.nextPhysicalPlayNumber = '4'
  r.source.checkpoint.ref = structuredClone(v.nextPrefixRef)
  r.source.checkpoint.ref.digest = sealNonplayTestContent(content)
  r.prefixRef = structuredClone(r.source.checkpoint.ref)
  r.t1.before = structuredClone(v.t1.after)
  r.t1.resultId = 'batting-result.called-pitch'
  r.sourcePosition = { d1: '2', d2: '4096', appliedWatermark: '1' }
  r.playIdentity = {
    eventId: '00000000-0000-4000-8000-0000000008b1',
    d5: '00000000-0000-4000-8000-0000000008b2',
    playId: '00000000-0000-4000-8000-0000000008b3',
  }
  r.nextCheckpoint = {
    id: '00000000-0000-4000-8000-0000000008b4',
    revision: '22',
    digest: 'a'.repeat(64),
  }
  expect(
    r.source.activeStack.map((x) => [
      x.play.source.generation,
      x.play.source.d1,
    ]),
  ).toStrictEqual([
    ['2', '1'],
    ['1', '2'],
    ['1', '1'],
  ])
  const saved = structuredClone(r)
  expect(invoke(r)).toStrictEqual(nonplayBallExpected(r, true))
  expect(r).toStrictEqual(saved)
  // 同じ状態を持っていても、同世代D1順が逆なら依然拒否する。
  const bad = structuredClone(r)
  Object.assign(bad.source.activeStack[2]!.play.source, { d1: '3' })
  bad.source.checkpoint.ref.digest = sealNonplayTestContent(
    bad.source.checkpoint.content,
  )
  bad.prefixRef = structuredClone(bad.source.checkpoint.ref)
  expect(invoke(bad)).toStrictEqual({
    ok: false,
    error: { code: 'PREFIX_SOURCE_MISMATCH' },
  })
})
