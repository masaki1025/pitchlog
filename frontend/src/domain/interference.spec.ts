import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { isLineupDefinition, lineupWireHead } from '../api/lineupPrefixWire'
import type {
  Request,
  Success,
} from '../../../contracts/state-transition/lineup_play_prefix_v1'
import type { BattedHitObservation } from './battedHit'
import { domainOperations } from './publicApi'
import { deriveBattedHit } from './state'
import { deriveInterference } from './state'
import type { InterferenceObservation } from './interference'
import type { BattingOrderBySide, Scoreboard, StateFields } from './stateTypes'

const matrix = JSON.parse(
  readFileSync(
    resolve('../contracts/state-transition/state_transition_contract_v1.json'),
    'utf8',
  ),
) as {
  matrixRows: Array<{ resultId: string; statFlags: Record<string, boolean> }>
}
const board: Scoreboard = {
  home: 0n,
  away: 0n,
  hits: 0n,
  errors: 0n,
  strikeouts: 0n,
  walks: 0n,
}
const cursors: BattingOrderBySide = { away: 1n, home: 1n }
function before(runners: StateFields['runners']): StateFields {
  return {
    half: 'top',
    inning: 1n,
    outs: 0n,
    strikes: 0n,
    balls: 0n,
    runners,
    battingOrder: 1n,
    tiebreakActive: false,
    gameEnded: false,
    home: 0n,
    away: 0n,
  }
}
function penalty(runners: StateFields['runners']): BattedHitObservation {
  return {
    eventKind: 'secondary-result',
    resultId: 'secondary-result.batting-interference',
    pitchEventKind: 'pitch-event',
    officialScoringPayload: 'no-error',
    interferenceRuling: {
      kind: 'batting-interference',
      adopted: { kind: 'penalty-award' },
      third_base_scoring_attempt: [
        'third',
        'first-third',
        'second-third',
        'loaded',
      ].includes(runners)
        ? { kind: 'observed', value: 'none' }
        : { kind: 'not-required' },
    },
    runnerAdvanceOverrides: 'not-applied',
    thirdOutObservation: 'none',
  }
}
describe('INT-02 の罰則採用を唯一核へ渡す', () => {
  it('正本の一三塁代表行と23旗・強制進塁・無得点が全値一致する', () => {
    const result = deriveBattedHit(
      before('first-third'),
      board,
      penalty('first-third'),
      cursors,
    )!
    const official = matrix.matrixRows.find(
      (row) => row.resultId === 'secondary-result.batting-interference',
    )!
    expect(result.statFlags).toEqual(official.statFlags)
    expect(result.after.stateFields).toMatchObject({
      runners: 'loaded',
      outs: 0n,
      away: 0n,
    })
    expect(result.runnerDefaultAdvance.first).toEqual({
      modality: 'forced',
      destination: 2n,
    })
    expect(result.runnerDefaultAdvance.third).toEqual({
      modality: 'hold',
      destination: null,
    })
    expect(result.batterDestination).toEqual({ kind: 'reach', base: 1n })
  })
  it('満塁の押し出しだけRBI-07を算入する', () => {
    const result = deriveBattedHit(
      before('loaded'),
      board,
      penalty('loaded'),
      cursors,
    )!
    expect(result.after.stateFields).toMatchObject({
      runners: 'loaded',
      away: 1n,
    })
    expect(result.statFlags).toMatchObject({
      得点: true,
      打点: true,
      打数: false,
      打撃妨害出塁: true,
    })
    expect(result.runnerScoreEffects).toEqual([
      { base: 3n, validRun: true, rbiCredited: true },
    ])
  })
  it('未観測三塁得点試行・未採用側・失策/余剰を拒否する', () => {
    const base = penalty('first-third')
    for (const ruling of [
      {
        kind: 'batting-interference',
        adopted: { kind: 'penalty-award' },
        third_base_scoring_attempt: { kind: 'not-required' },
      },
      {
        kind: 'batting-interference',
        adopted: { kind: 'play-result', resultId: 'batting-result.single' },
        third_base_scoring_attempt: { kind: 'observed', value: 'none' },
      },
      {
        kind: 'batting-interference',
        adopted: { kind: 'penalty-award' },
        third_base_scoring_attempt: { kind: 'observed', value: 'none' },
        extra: true,
      },
    ])
      expect(
        deriveBattedHit(
          before('first-third'),
          board,
          { ...base, interferenceRuling: ruling } as BattedHitObservation,
          cursors,
        ),
      ).toBeNull()
    expect(
      deriveBattedHit(
        before('first-third'),
        board,
        { ...base, officialScoringPayload: 'error-recorded' },
        cursors,
      ),
    ).toBeNull()
    expect(
      deriveBattedHit(
        before('first-third'),
        board,
        {
          ...base,
          runnerAdvanceOverrides: {
            kind: 'applied',
            overrides: [{ runnerBase: '1', destination: '2' }],
          },
        },
        cursors,
      ),
    ).toBeNull()
  })
  it('三塁走者の明示スクイズ試行ではボーク進塁と非強制RBI0を区別する', () => {
    const observed: BattedHitObservation = {
      ...penalty('first-third'),
      interferenceRuling: {
        kind: 'batting-interference',
        adopted: { kind: 'penalty-award' },
        third_base_scoring_attempt: { kind: 'observed', value: 'squeeze' },
      },
    }
    const result = deriveBattedHit(
      before('first-third'),
      board,
      observed,
      cursors,
    )!
    expect(result.runnerDefaultAdvance.third).toEqual({
      modality: 'optional',
      destination: 4n,
    })
    expect(result.after.stateFields.away).toBe(1n)
    expect(result.statFlags.打点).toBe(false)
  })
})

it('妨害headの原裁定とtyped効果をFE封印でも落とさない', () => {
  const cases = JSON.parse(
    readFileSync(
      resolve('../contracts/state-transition/batted_hit_prefix_cases_v1.json'),
      'utf8',
    ),
  ) as {
    cases: Array<{
      request: Record<string, unknown>
      expected: Record<string, unknown>
    }>
  }
  const request = structuredClone(cases.cases[0]!.request) as Record<
    string,
    unknown
  > & {
    t1: Record<string, unknown>
  }
  request.t1 = {
    ...request.t1,
    eventKind: 'secondary-result',
    resultId: 'secondary-result.batting-interference',
    interferenceRuling: {
      kind: 'batting-interference',
      adopted: { kind: 'penalty-award' },
      third_base_scoring_attempt: { kind: 'not-required' },
    },
  }
  const response = structuredClone(cases.cases[0]!.expected) as {
    ok: boolean
    value: Record<string, unknown>
  }
  response.value.runnerScoreEffects = []
  const head = lineupWireHead(
    request as unknown as Request,
    response as Success,
  )
  expect(head).toMatchObject({
    interferenceRuling: request.t1.interferenceRuling,
    runnerScoreEffects: [],
  })
  expect(isLineupDefinition(head, 'WireHead')).toBe(true)
  delete response.value.runnerScoreEffects
  expect(() =>
    lineupWireHead(request as unknown as Request, response as Success),
  ).toThrow('妨害裁定の算入根拠を確認できません')
})

describe('INT-01/03 の実プレイ採用', () => {
  it('採用された単打だけを既通常打球の同じ計算へ渡す', () => {
    const ordinary: BattedHitObservation = {
      eventKind: 'batting-result',
      resultId: 'batting-result.single',
      pitchEventKind: 'pitch-event',
      officialScoringPayload: 'no-error',
      interferenceRuling: 'not-required',
      runnerAdvanceOverrides: {
        kind: 'applied',
        overrides: [{ runnerBase: '1', destination: '2' }],
      },
      thirdOutObservation: 'none',
    }
    const adopted: BattedHitObservation = {
      ...ordinary,
      interferenceRuling: {
        kind: 'batting-interference',
        adopted: { kind: 'play-result', resultId: 'batting-result.single' },
        third_base_scoring_attempt: { kind: 'not-required' },
      },
    }
    const adoptedResult = deriveBattedHit(
      before('first'),
      board,
      adopted,
      cursors,
    )!
    const ordinaryResult = deriveBattedHit(
      before('first'),
      board,
      ordinary,
      cursors,
    )!
    expect(adoptedResult.runnerScoreEffects).toEqual([])
    expect({ ...adoptedResult, runnerScoreEffects: undefined }).toEqual({
      ...ordinaryResult,
      runnerScoreEffects: undefined,
    })
    expect(
      deriveBattedHit(
        before('first'),
        board,
        {
          ...adopted,
          interferenceRuling: {
            kind: 'batting-interference',
            adopted: { kind: 'play-result', resultId: 'batting-result.double' },
            third_base_scoring_attempt: { kind: 'not-required' },
          },
        },
        cursors,
      ),
    ).toBeNull()
  })
  it('採用された実プレイの生還をtyped効果として残す', () => {
    const adopted: BattedHitObservation = {
      eventKind: 'batting-result',
      resultId: 'batting-result.single',
      pitchEventKind: 'pitch-event',
      officialScoringPayload: 'no-error',
      interferenceRuling: {
        kind: 'batting-interference',
        adopted: { kind: 'play-result', resultId: 'batting-result.single' },
        third_base_scoring_attempt: { kind: 'observed', value: 'none' },
      },
      runnerAdvanceOverrides: {
        kind: 'applied',
        overrides: [
          { runnerBase: '1', destination: '2' },
          { runnerBase: '3', destination: '4' },
        ],
      },
      thirdOutObservation: 'none',
    }
    const result = deriveBattedHit(
      before('first-third'),
      board,
      adopted,
      cursors,
    )!
    expect(result.runnerScoreEffects).toEqual([
      { base: 3n, validRun: true, rbiCredited: true },
    ])
    expect(result.statFlags).toMatchObject({ 得点: true, 打点: true })
  })
  it('INT-03では三塁停止の実プレイを選んでも罰則出塁へ読み替えない', () => {
    const observed: BattedHitObservation = {
      eventKind: 'batting-result',
      resultId: 'batting-result.single',
      pitchEventKind: 'pitch-event',
      officialScoringPayload: 'no-error',
      interferenceRuling: {
        kind: 'batting-interference',
        adopted: { kind: 'play-result', resultId: 'batting-result.single' },
        third_base_scoring_attempt: { kind: 'observed', value: 'none' },
      },
      runnerAdvanceOverrides: {
        kind: 'applied',
        overrides: [
          { runnerBase: '1', destination: '2' },
          { runnerBase: '3', destination: '3' },
        ],
      },
      thirdOutObservation: 'none',
    }
    const result = deriveBattedHit(
      before('first-third'),
      board,
      observed,
      cursors,
    )!
    expect(result.after.stateFields.runners).toBe('loaded')
    expect(result.statFlags).toMatchObject({
      安打: true,
      打数: true,
      打撃妨害出塁: false,
    })
  })
})

it('公開T1でもINT-02の満塁を閉入力として受理し、別secondaryは拒否する', () => {
  const fixture = JSON.parse(
    readFileSync(
      resolve('../contracts/state-transition/batted_hit_cases_v1.json'),
      'utf8',
    ),
  ) as {
    cases: Array<{ request: Record<string, unknown> }>
  }
  const request = structuredClone(fixture.cases[0]!.request)
  const previous = request.before as {
    stateFields: Record<string, unknown>
    scoreboard: Record<string, unknown>
  }
  previous.stateFields['state.runners'] = 'loaded'
  request.eventKind = 'secondary-result'
  request.resultId = 'secondary-result.batting-interference'
  request.interferenceRuling = penalty('loaded').interferenceRuling
  const accepted = JSON.parse(
    domainOperations.deriveInterference(JSON.stringify(request)),
  ) as { ok: boolean; value?: { statFlags: Record<string, boolean> } }
  expect(accepted.ok).toBe(true)
  expect(accepted.value?.statFlags).toMatchObject({
    得点: true,
    打点: true,
    打撃妨害出塁: true,
  })
  request.resultId = 'secondary-result.obstruction'
  expect(
    JSON.parse(domainOperations.deriveInterference(JSON.stringify(request))),
  ).toMatchObject({ ok: false })
  request.resultId = 'secondary-result.batting-interference'
  expect(
    JSON.parse(domainOperations.deriveBattedHit(JSON.stringify(request))),
  ).toMatchObject({ ok: false })
})

const batterId = '11111111-1111-4111-8111-111111111111'
const firstId = '22222222-2222-4222-8222-222222222222'
const thirdId = '33333333-3333-4333-8333-333333333333'
const pitcherId = '44444444-4444-4444-8444-444444444444'
const batterRef = {
  kind: 'batter',
  batter_id: { kind: 'official', player_id: batterId },
}
const firstRef = {
  kind: 'runner',
  runner_id: { kind: 'official', player_id: firstId },
}
const thirdRef = {
  kind: 'runner',
  runner_id: { kind: 'official', player_id: thirdId },
}
const live = [
  { base: '1' as const, runnerId: firstId, responsiblePitcherId: pitcherId },
  { base: '3' as const, runnerId: thirdId, responsiblePitcherId: pitcherId },
]
function interference(
  resultId: InterferenceObservation['resultId'],
  ruling: unknown,
): InterferenceObservation {
  return {
    eventKind: 'secondary-result',
    resultId,
    pitchEventKind: 'pitch-event',
    interferenceRuling: ruling,
    batterId,
    liveRunners: live,
  }
}
describe('INT-04〜07 の実参照つき裁定', () => {
  it('INT-04は授与塁を使用し、正本代表行の23旗・強制とholdに一致する', () => {
    const observed = interference('secondary-result.obstruction', {
      kind: 'obstruction',
      play_kind: 'play-on-obstructed-runner',
      obstructed: firstRef,
      awarded_destinations: [
        { person: batterRef, destination: 'first' },
        { person: firstRef, destination: 'second' },
        { person: thirdRef, destination: 'third' },
      ],
      out_targets: [],
      batter_before_first: 'not-required',
    })
    const result = deriveInterference(
      before('first-third'),
      board,
      observed,
      cursors,
    )!
    const official = matrix.matrixRows.find(
      (row) => row.resultId === observed.resultId,
    )!
    expect(result.statFlags).toEqual(official.statFlags)
    expect(result.runnerDefaultAdvance.first).toEqual({
      modality: 'forced',
      destination: 2n,
    })
    expect(result.runnerDefaultAdvance.third).toEqual({
      modality: 'hold',
      destination: null,
    })
    expect(result.after.stateFields.runners).toBe('loaded')
    expect(
      deriveInterference(
        before('first-third'),
        board,
        {
          ...observed,
          interferenceRuling: {
            ...(observed.interferenceRuling as object),
            out_targets: [firstRef],
          },
        },
        cursors,
      ),
    ).toBeNull()
    expect(
      deriveInterference(
        before('first-third'),
        board,
        {
          ...observed,
          interferenceRuling: {
            ...(observed.interferenceRuling as object),
            awarded_destinations: [
              { person: batterRef, destination: 'second' },
              { person: firstRef, destination: 'first' },
              { person: thirdRef, destination: 'third' },
            ],
          },
        },
        cursors,
      ),
    ).toBeNull()
    expect(
      deriveInterference(
        before('first-third'),
        board,
        {
          ...observed,
          liveRunners: [
            { ...live[0]!, runnerId: '55555555-5555-4555-8555-555555555555' },
            live[1]!,
          ],
        },
        cursors,
      ),
    ).toBeNull()
  })
  it('INT-06の打者アウトとINT-07の走者のみアウトを分ける', () => {
    const withBatter = interference('secondary-result.offensive-interference', {
      kind: 'offensive-interference',
      out_targets: [batterRef],
      return_bases: [
        { person: firstRef, destination: 'first' },
        { person: thirdRef, destination: 'third' },
      ],
    })
    const result = deriveInterference(
      before('first-third'),
      board,
      withBatter,
      cursors,
    )!
    const official = matrix.matrixRows.find(
      (row) => row.resultId === withBatter.resultId,
    )!
    expect(result.statFlags).toEqual(official.statFlags)
    expect(result.batterDestination).toEqual({ kind: 'out' })
    expect(result.outEffect.targets).toEqual([{ kind: 'batter' }])
    const runnerOnly = interference('secondary-result.offensive-interference', {
      kind: 'offensive-interference',
      out_targets: [firstRef],
      return_bases: [{ person: thirdRef, destination: 'third' }],
    })
    const continued = deriveInterference(
      before('first-third'),
      board,
      runnerOnly,
      cursors,
    )!
    expect(continued.batterDestination).toEqual({ kind: 'continue' })
    expect(continued.plateAppearanceEnded).toBe(false)
    expect(continued.outEffect.targets).toEqual([{ kind: 'runner', base: 1n }])
    expect(continued.statFlags.打数).toBe(false)
  })
  it('公開閉T1は実IDを受け、欠落/別IDの裁定を成功させない', () => {
    const fixture = JSON.parse(
      readFileSync(
        resolve('../contracts/state-transition/batted_hit_cases_v1.json'),
        'utf8',
      ),
    ) as { cases: Array<{ request: Record<string, unknown> }> }
    const request = structuredClone(fixture.cases[0]!.request)
    const beforeWire = request.before as {
      stateFields: Record<string, unknown>
    }
    beforeWire.stateFields['state.runners'] = 'first-third'
    delete request.officialScoringPayload
    delete request.runnerAdvanceOverrides
    delete request.thirdOutObservation
    request.eventKind = 'secondary-result'
    request.resultId = 'secondary-result.obstruction'
    request.batterId = batterId
    request.liveRunners = live
    request.interferenceRuling = {
      kind: 'obstruction',
      play_kind: 'play-on-obstructed-runner',
      obstructed: firstRef,
      awarded_destinations: [
        { person: batterRef, destination: 'first' },
        { person: firstRef, destination: 'second' },
        { person: thirdRef, destination: 'third' },
      ],
      out_targets: [],
      batter_before_first: 'not-required',
    }
    const accepted = JSON.parse(
      domainOperations.deriveInterference(JSON.stringify(request)),
    ) as { ok: boolean }
    expect(accepted.ok).toBe(true)
    request.liveRunners = [live[0]]
    expect(
      JSON.parse(domainOperations.deriveInterference(JSON.stringify(request))),
    ).toMatchObject({ ok: false })
  })
  it('INT-05は実プレイ後の被妨害走者アウト裁定だけを採用する', () => {
    const observed = interference('secondary-result.obstruction', {
      kind: 'obstruction',
      play_kind: 'no-play-on-obstructed-runner',
      obstructed: firstRef,
      awarded_destinations: [{ person: thirdRef, destination: 'third' }],
      out_targets: [firstRef],
      batter_before_first: 'not-required',
    })
    const result = deriveInterference(
      before('first-third'),
      board,
      observed,
      cursors,
    )!
    expect(result.outEffect.targets).toEqual([{ kind: 'runner', base: 1n }])
    expect(result.after.stateFields).toMatchObject({
      runners: 'third',
      outs: 1n,
    })
    expect(result.statFlags.走塁妨害出塁).toBe(false)
  })
  it('INT-04はno-play表記でも一塁前の打者への実授与を要求しアウトを拒否する', () => {
    const ruling = {
      kind: 'obstruction',
      play_kind: 'no-play-on-obstructed-runner',
      obstructed: batterRef,
      awarded_destinations: [
        { person: batterRef, destination: 'first' },
        { person: firstRef, destination: 'second' },
        { person: thirdRef, destination: 'third' },
      ],
      out_targets: [],
      batter_before_first: true,
    }
    const input = interference('secondary-result.obstruction', ruling)
    const accepted = deriveInterference(
      before('first-third'),
      board,
      input,
      cursors,
    )!
    expect(accepted.outEffect.count).toBe(0n)
    expect(accepted.batterDestination).toEqual({ kind: 'reach', base: 1n })
    expect(accepted.after.stateFields.outs).toBe(0n)
    const withoutBatterAward = ruling.awarded_destinations.slice(1)
    for (const outTargets of [[batterRef], []]) {
      expect(
        deriveInterference(
          before('first-third'),
          board,
          {
            ...input,
            interferenceRuling: {
              ...ruling,
              awarded_destinations: withoutBatterAward,
              out_targets: outTargets,
            },
          },
          cursors,
        ),
      ).toBeNull()
    }
  })
})

it('v3継続は打撃妨害の真正sourceを独立T1入口へ渡す', () => {
  const vectors = JSON.parse(
    readFileSync(
      resolve('../contracts/state-transition/batted_hit_prefix_cases_v1.json'),
      'utf8',
    ),
  ) as { cases: Array<{ request: { t1: Record<string, unknown> } }> }
  const request = structuredClone(vectors.cases[0]!.request)
  request.t1.eventKind = 'secondary-result'
  request.t1.resultId = 'secondary-result.batting-interference'
  request.t1.interferenceRuling = {
    kind: 'batting-interference',
    adopted: { kind: 'penalty-award' },
    third_base_scoring_attempt: { kind: 'not-required' },
  }
  const result = JSON.parse(
    domainOperations.deriveLineupPlayPrefixWithContinuation(
      JSON.stringify(request),
    ),
  ) as {
    ok: boolean
    value?: {
      t1: { statFlags: Record<string, boolean> }
      runnerScoreEffects: unknown[]
    }
    error?: unknown
  }
  expect(result.ok).toBe(true)
  expect(result.value?.t1.statFlags.打撃妨害出塁).toBe(true)
  expect(result.value?.runnerScoreEffects).toEqual([])
})

it('v3継続は走塁妨害の打者実IDをsourceから束縛する', () => {
  const vectors = JSON.parse(
    readFileSync(
      resolve('../contracts/state-transition/batted_hit_prefix_cases_v1.json'),
      'utf8',
    ),
  ) as {
    cases: Array<{
      request: {
        t1: Record<string, unknown>
        source: { participants: { batterId: string } }
      }
    }>
  }
  const request = structuredClone(vectors.cases[0]!.request)
  const actualBatter = request.source.participants.batterId
  request.t1 = {
    eventKind: 'secondary-result',
    resultId: 'secondary-result.obstruction',
    pitchEventKind: 'pitch-event',
    before: request.t1.before,
    interferenceRuling: {
      kind: 'obstruction',
      play_kind: 'play-on-obstructed-runner',
      obstructed: {
        kind: 'batter',
        batter_id: { kind: 'official', player_id: actualBatter },
      },
      awarded_destinations: [
        {
          person: {
            kind: 'batter',
            batter_id: { kind: 'official', player_id: actualBatter },
          },
          destination: 'first',
        },
      ],
      out_targets: [],
      batter_before_first: true,
    },
  }
  const result = JSON.parse(
    domainOperations.deriveLineupPlayPrefixWithContinuation(
      JSON.stringify(request),
    ),
  ) as {
    ok: boolean
    value?: {
      t1: { statFlags: Record<string, boolean> }
      runnerScoreEffects: unknown[]
    }
    error?: unknown
  }
  expect(result.ok).toBe(true)
  expect(result.value?.t1.statFlags.走塁妨害出塁).toBe(true)
  expect(result.value?.runnerScoreEffects).toEqual([])
  const original = request.t1.interferenceRuling as Record<string, unknown>
  request.t1.interferenceRuling = {
    ...original,
    play_kind: 'no-play-on-obstructed-runner',
    awarded_destinations: [],
    out_targets: [original.obstructed],
  }
  expect(
    JSON.parse(
      domainOperations.deriveLineupPlayPrefixWithContinuation(
        JSON.stringify(request),
      ),
    ),
  ).toMatchObject({ ok: false })
  request.t1.interferenceRuling = {
    ...original,
    play_kind: 'no-play-on-obstructed-runner',
    awarded_destinations: [
      { person: original.obstructed, destination: 'first' },
    ],
    out_targets: [],
  }
  expect(
    JSON.parse(
      domainOperations.deriveLineupPlayPrefixWithContinuation(
        JSON.stringify(request),
      ),
    ),
  ).toMatchObject({ ok: true })
})
