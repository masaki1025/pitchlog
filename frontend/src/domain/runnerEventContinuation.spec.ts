import { readFileSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { createContext, runInContext } from 'node:vm'
import { resolve } from 'node:path'
import { beforeAll, afterAll, describe, it, expect } from 'vitest'
import { domainOperations } from './publicApi'
import { readRunnerObservation } from './runnerEvent'

const cases = JSON.parse(
  readFileSync(
    resolve('../contracts/state-transition/batted_hit_prefix_cases_v1.json'),
    'utf8',
  ),
).cases
const runnerId = '10000000-0000-0000-0000-000000000299'
const ref = { kind: 'official', player_id: runnerId }
const rbi = {
  doublePlayRelayError: 'not-required',
  runnerContinuityByRunner: { kind: 'not-required' },
  wouldScoreWithoutErrorByRunner: { kind: 'not-required' },
  cause_by_runner: { kind: 'not-required' },
  restart_by_runner: { kind: 'not-required' },
}
function observation(
  resultId = 'pitcher-pickoff-destination.first',
  eventKind = 'runner-event',
  pitchEventKind = 'non-pitch-event',
) {
  return {
    primaryResultId: null,
    perPitch: {
      kind: eventKind,
      resultId,
      pitchEventKind,
      runnerEventPayload: {
        kind: 'runner-event',
        event_kind: resultId,
        by_runner: {
          first: {
            kind: 'out',
            runner: structuredClone(ref),
            attempted_base: 'first',
            out_kind: 'pitcher-pickoff-out',
          },
        },
      },
      runnerAdvanceOverridesByRunner: { kind: 'not-applied' },
      thirdOutObservation: { kind: 'not-required' },
      thirdOutTimingByRunner: {},
      officialScoringPayload: { kind: 'no-error' },
      interferenceRuling: { kind: 'not-required' },
      rbi: structuredClone(rbi),
      homeTouchOrder: { kind: 'not-required' },
    },
  }
}
function request(outs = '0') {
  const q = structuredClone(cases[0].request)
  const { before } = q.t1
  before.stateFields['state.runners'] = 'first'
  before.stateFields['state.outs'] = outs
  q.source.after = structuredClone(before)
  q.source.t2.facts.beforeOuts = outs
  q.source.t2.facts.afterOuts = outs
  q.source.runners = [
    {
      runnerId,
      responsiblePitcherId: q.source.participants.pitcherId,
      base: '1',
      status: '継続',
      statusSource: 'auto',
    },
  ]
  q.t1 = {
    eventKind: 'runner-event',
    resultId: 'pitcher-pickoff-destination.first',
    pitchEventKind: 'non-pitch-event',
    before,
    runnerObservation: observation(),
  }
  return q
}
const cacheRoot = join(
  homedir(),
  '.cache/pitchlog/runner-operations-author-20261107',
)
mkdirSync(cacheRoot, { recursive: true })
const cache = mkdtempSync(join(cacheRoot, 'artifact-'))
const context = createContext({})
const records: Array<{ request: unknown; expected: unknown }> = []
beforeAll(() => {
  execFileSync(
    process.execPath,
    [
      '--input-type=module',
      '-e',
      `import {buildDomain} from './scripts/domain-build/build.mjs'; await buildDomain({outputDirectory:${JSON.stringify(cache)}})`,
    ],
    { cwd: process.cwd(), stdio: 'pipe' },
  )
  runInContext(readFileSync(join(cache, 'pitchlog-domain.js'), 'utf8'), context)
}, 60000)
afterAll(() =>
  writeFileSync(
    join(cache, 'author-cases.json'),
    JSON.stringify(records, null, 2) + '\n',
  ),
)
const invoke = (q: unknown) => {
  const text = JSON.stringify(q)
  const source = JSON.parse(
    domainOperations.deriveLineupPlayPrefixWithContinuation(text),
  )
  const artifact = JSON.parse(
    runInContext(
      `PitchlogDomain.deriveLineupPlayPrefixWithContinuation(${JSON.stringify(text)})`,
      context,
    ),
  )
  expect(artifact).toEqual(source)
  records.push({
    request: structuredClone(q),
    expected: structuredClone(artifact),
  })
  return artifact
}
describe('原値perPitchをv3唯一核/生存IDへ接続', () => {
  it('牽制死のout IDを除去し、非終端PAの責任参照は保持する', () => {
    const q = request()
    const result = invoke(q)
    expect(result.ok).toBe(true)
    expect(result.value.t1.outEffect).toEqual({
      count: '1',
      targets: [{ runner: '1' }],
    })
    expect(result.value.t1.after.stateFields['state.outs']).toBe('1')
    expect(result.value.runners).toEqual([])
    expect(result.value.nextResponsibility).toEqual(q.source.responsibility)
    expect(result.value.t1.statFlags.投球数).toBe(false)
    expect(result.value.runnerScoreEffects).toEqual([])
    expect(result.value.t1.after.battingOrderBySide).toEqual(
      q.t1.before.battingOrderBySide,
    )
  })
  it('走者だけの第3アウトも次チームPAの責任sourceを更新する', () => {
    const q = request('2')
    const result = invoke(q)
    expect(result.ok).toBe(true)
    expect(result.value.t1.after.stateFields['state.half']).toBe('bottom')
    expect(result.value.t1.after.stateFields['state.count.strikes']).toBe('0')
    expect(result.value.nextResponsibility.paStartSource).toEqual({
      kind: 'confirmed-play',
      id: q.playIdentity.eventId,
    })
    expect(result.value.runners).toEqual([])
  })
  it('同じ正式SO05計算から打者と走者out、双方cursorと次IDを得る', () => {
    const q = request('1')
    q.t1.before.stateFields['state.count.balls'] = '0'
    q.source.after = structuredClone(q.t1.before)
    const perPitch = observation(
      'batting-result.strikeout-double-play',
      'batting-result',
      'pitch-event',
    ).perPitch as Record<string, unknown>
    perPitch.runnerEventPayload = { kind: 'not-applicable' }
    perPitch.runnerAdvanceOverridesByRunner = {
      kind: 'overridden',
      by_runner: {
        first: {
          kind: 'out',
          runner: ref,
          attempted_base: 'second',
          out_kind: 'caught-stealing',
        },
      },
    }
    q.t1 = {
      ...q.t1,
      eventKind: 'batting-result',
      resultId: 'batting-result.strikeout-double-play',
      pitchEventKind: 'pitch-event',
      runnerObservation: { primaryResultId: null, perPitch },
    }
    const result = invoke(q)
    expect(result.ok).toBe(true)
    expect(result.value.t1.outEffect).toEqual({
      count: '2',
      targets: ['batter', { runner: '1' }],
    })
    expect(result.value.runners).toEqual([])
    expect(result.value.t1.after.battingOrderBySide).toEqual({
      away: '2',
      home: '6',
    })
    expect(result.value.runnerScoreEffects).toEqual([])
  })
  it.each([
    'perPitch-extra',
    'wrong-id',
    'unobserved-error',
    'partial-rbi',
    'flat',
    'wrong-player',
    'temporary',
  ])('未知/改変%sを成功させない', (kind) => {
    const q = request()
    const o = q.t1.runnerObservation
    if (kind === 'perPitch-extra') o.perPitch.extra = true
    if (kind === 'wrong-id') o.perPitch.resultId = 'strategy-category.steal'
    if (kind === 'unobserved-error')
      o.perPitch.officialScoringPayload = { kind: 'error' }
    if (kind === 'partial-rbi') delete o.perPitch.rbi.cause_by_runner
    if (kind === 'flat') q.t1.runnerObservation = o.perPitch
    if (kind === 'wrong-player')
      o.perPitch.runnerEventPayload.by_runner.first.runner.player_id =
        '10000000-0000-0000-0000-000000000288'
    if (kind === 'temporary')
      o.perPitch.runnerEventPayload.by_runner.first.runner = {
        kind: 'temporary',
        temporary_id: runnerId,
      }
    expect(invoke(q).ok).toBe(false)
  })
  it('余剰原値は補修せず拒否し、原入力も変更しない', () => {
    const o = observation()
    const old = structuredClone(o)
    expect(
      readRunnerObservation(
        o,
        'runner-event',
        'pitcher-pickoff-destination.first',
        'non-pitch-event',
      ),
    ).not.toBeNull()
    expect(o).toEqual(old)
    expect(
      readRunnerObservation(
        { ...o, extra: true },
        'runner-event',
        'pitcher-pickoff-destination.first',
        'non-pitch-event',
      ),
    ).toBeNull()
  })
})

it.each([
  'secondary-result.wild-pitch',
  'secondary-result.passed-ball',
  'secondary-result.balk',
])('artifactまで%sの全走者実到達とRBI09を写す', (operationId) => {
  const q = request()
  const pitched = operationId !== 'secondary-result.balk'
  q.t1.before.stateFields['state.runners'] = 'first-second-third'
  q.t1.before.stateFields['state.count.balls'] = '1'
  q.source.after = structuredClone(q.t1.before)
  const ids = [
    runnerId,
    '10000000-0000-0000-0000-000000000298',
    '10000000-0000-0000-0000-000000000297',
  ]
  q.source.runners = ids.map((id, i) => ({
    ...q.source.runners[0],
    runnerId: id,
    base: String(i + 1),
  }))
  const o = observation(
    operationId,
    'secondary-result',
    pitched ? 'pitch-event' : 'non-pitch-event',
  ) as { primaryResultId: string | null; perPitch: Record<string, unknown> }
  o.primaryResultId = pitched ? 'batting-result.ball' : null
  o.perPitch.runnerEventPayload = { kind: 'not-applicable' }
  o.perPitch.runnerAdvanceOverridesByRunner = {
    kind: 'overridden',
    by_runner: {
      first: {
        kind: 'safe-advance',
        runner: { kind: 'official', player_id: ids[0] },
        destination: 'second',
      },
      second: {
        kind: 'safe-advance',
        runner: { kind: 'official', player_id: ids[1] },
        destination: 'third',
      },
      third: {
        kind: 'safe-advance',
        runner: { kind: 'official', player_id: ids[2] },
        destination: 'home',
      },
    },
  }
  q.t1 = {
    eventKind: 'secondary-result',
    resultId: operationId,
    pitchEventKind: o.perPitch.pitchEventKind,
    before: q.t1.before,
    runnerObservation: o,
  }
  const result = invoke(q)
  expect(result.ok).toBe(true)
  expect(result.value.t1.after.stateFields['state.score']).toEqual({
    home: '3',
    away: '6',
  })
  expect(result.value.t1.after.stateFields['state.count.balls']).toBe(
    pitched ? '2' : '1',
  )
  expect(result.value.t1.statFlags.投球数).toBe(pitched)
  expect(result.value.t1.statFlags.打点).toBe(false)
  expect(
    result.value.runners.map((r: { base: string; runnerId: string }) => [
      r.base,
      r.runnerId,
    ]),
  ).toEqual([
    ['2', ids[0]],
    ['3', ids[1]],
  ])
  expect(result.value.runnerScoreEffects).toEqual([
    { base: '3', validRun: true, rbiCredited: false },
  ])
})
it('artifactまで通常球＋盗塁を1投球に合成しID/責任を維持する', () => {
  const q = request()
  q.t1.before.stateFields['state.count.balls'] = '1'
  q.source.after = structuredClone(q.t1.before)
  const o = observation(
    'batting-result.ball',
    'batting-result',
    'pitch-event',
  ) as { primaryResultId: string | null; perPitch: Record<string, unknown> }
  o.primaryResultId = 'batting-result.ball'
  o.perPitch.runnerEventPayload = {
    kind: 'runner-event',
    event_kind: 'strategy-category.steal',
    by_runner: {
      first: { kind: 'safe-advance', runner: ref, destination: 'second' },
    },
  }
  q.t1 = {
    eventKind: 'batting-result',
    resultId: 'batting-result.ball',
    pitchEventKind: 'pitch-event',
    before: q.t1.before,
    runnerObservation: o,
  }
  const result = invoke(q)
  expect(result.ok).toBe(true)
  expect(result.value.t1.after.stateFields['state.count.balls']).toBe('2')
  expect(result.value.t1.statFlags.投球数).toBe(true)
  expect(result.value.runners).toEqual([{ ...q.source.runners[0], base: '2' }])
})

it.each(['safe-advance', 'out'])(
  '普通foul＋走者%sは単一artifactでも閉拒否する',
  (outcome) => {
    const q = request()
    const o = observation(
      'batting-result.foul',
      'batting-result',
      'pitch-event',
    ) as { primaryResultId: string | null; perPitch: Record<string, unknown> }
    o.primaryResultId = 'batting-result.foul'
    o.perPitch.runnerEventPayload = {
      kind: 'runner-event',
      event_kind: 'strategy-category.steal',
      by_runner: {
        first:
          outcome === 'out'
            ? {
                kind: 'out',
                runner: ref,
                attempted_base: 'second',
                out_kind: 'caught-stealing',
              }
            : { kind: 'safe-advance', runner: ref, destination: 'second' },
      },
    }
    q.t1 = {
      eventKind: 'batting-result',
      resultId: 'batting-result.foul',
      pitchEventKind: 'pitch-event',
      before: q.t1.before,
      runnerObservation: o,
    }
    expect(invoke(q)).toEqual({
      ok: false,
      error: { code: 'UNSUPPORTED_T1_SCOPE' },
    })
  },
)
it.each(['secondary-result.wild-pitch', 'secondary-result.passed-ball'])(
  '普通foulを%sのlive球へ変更しない',
  (operationId) => {
    const q = request()
    const o = observation(operationId, 'secondary-result', 'pitch-event') as {
      primaryResultId: string | null
      perPitch: Record<string, unknown>
    }
    o.primaryResultId = 'batting-result.foul'
    o.perPitch.runnerEventPayload = { kind: 'not-applicable' }
    o.perPitch.runnerAdvanceOverridesByRunner = {
      kind: 'overridden',
      by_runner: {
        first: { kind: 'safe-advance', runner: ref, destination: 'second' },
      },
    }
    q.t1 = {
      eventKind: 'secondary-result',
      resultId: operationId,
      pitchEventKind: 'pitch-event',
      before: q.t1.before,
      runnerObservation: o,
    }
    expect(invoke(q)).toEqual({
      ok: false,
      error: { code: 'UNSUPPORTED_T1_SCOPE' },
    })
  },
)
