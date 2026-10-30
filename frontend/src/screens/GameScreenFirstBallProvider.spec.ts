import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { afterAll, beforeAll, expect, it } from 'vitest'
import type { StartedGame } from '../api/startedGame'
import {
  prepareFirstBall,
  firstBallEvent,
  type FirstBallScreenObservation,
} from './GameScreenFirstBallProvider'
const original = Object.getOwnPropertyDescriptor(globalThis, 'PitchlogDomain')
beforeAll(() => {
  const context = createContext({})
  new Script(
    readFileSync(
      resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
      'utf8',
    ),
  ).runInContext(context)
  Object.defineProperty(globalThis, 'PitchlogDomain', {
    configurable: true,
    value: Object.getOwnPropertyDescriptor(context, 'PitchlogDomain')!.value,
  })
})
afterAll(() => {
  if (original) Object.defineProperty(globalThis, 'PitchlogDomain', original)
  else Reflect.deleteProperty(globalThis, 'PitchlogDomain')
})
const tenant = '11111111-1111-4111-8111-111111111111'
const rows = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/initial_game_roster_cases_v1.json',
    ),
    'utf8',
  ),
).cases
const rosterCase = rows.find((r: { id: string }) => r.id === 'NORMAL-DH-true')
const combined = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/t2_first_pitch_continuation_cases_v1.json',
    ),
    'utf8',
  ),
).cases[0].request
function game(): StartedGame {
  const side = (name: 'away' | 'home') => ({
    lineup_id:
      name === 'away' ? tenant : '33333333-3333-4333-8333-333333333333',
    team_record_id: rosterCase.request[name].team_id,
    entries: rosterCase.request[name].entries.map((e: object) => ({
      ...e,
      uniform_number_snapshot: null,
    })),
  })
  return {
    read_kind: 'initial',
    id: '22222222-2222-4222-8222-222222222222',
    scheduled_at: '2026-10-30T10:00:00+09:00',
    game_type_key: 'game_open',
    tournament_key: 'practice',
    away_team_record_id: rosterCase.request.away.team_id,
    home_team_record_id: rosterCase.request.home.team_id,
    plate_umpire: null,
    section_label: null,
    week_label: null,
    day_label: null,
    game_number_label: null,
    status: 'in_progress',
    started_at: '2026-10-30T01:00:00Z',
    applied_rules: {
      ruleSetId: tenant,
      regulationInnings: 9,
      coldConditions: [],
      extensionLimit: 9,
      tiebreak: null,
      dh: true,
    },
    lineups: { away: side('away'), home: side('home') },
    roster: rosterCase.expected.value,
    state: structuredClone(combined.t1.before),
    current_d4: 'd4.1.' + 'A'.repeat(55),
  }
}
const observation: FirstBallScreenObservation = {
  resultId: 'batting-result.ball',
  pitchTypeKey: 'tenant.pitch.straight',
  screenX: 131.5,
  screenY: 124,
  view: 'catcher',
  pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
  stance: null,
  battingSide: null,
}
const vocabulary = {
  tenantId: tenant,
  pitchTypeKeys: ['tenant.pitch.straight'],
}
it('配布artifactの実計算から新初球のV7/V8を合成する', () => {
  const initial = game(),
    before = structuredClone(initial)
  const result = prepareFirstBall(initial, observation, vocabulary, tenant)
  expect(
    result.payload.calculation.response.value.t1.after.stateFields[
      'state.count.balls'
    ],
  ).toBe('1')
  expect(result.stateDiff).toEqual(
    result.payload.calculation.response.value.t1.historyContext[0].difference,
  )
  expect(result.payload.observations.course).toEqual({
    unit: '1/263',
    x: '132',
    y: '139',
  })
  expect(result.payload.participants.batterId).toBe(
    initial.lineups.away.entries.find((e) => e.batting_order === '1')!
      .player_id,
  )
  expect(initial).toEqual(before)
  const event = firstBallEvent(result, { d5: tenant, d2: 1 })
  expect(event.fields.V7).toEqual(result.payload)
  expect(event.fields.V8).toEqual(result.stateDiff)
  expect(event.fields.V6).toBe(1)
  expect(event.fields).not.toHaveProperty('V2')
})
it('視点を量子化後に一度だけ反転する', () => {
  const r = prepareFirstBall(
    game(),
    { ...observation, view: 'pitcher' },
    vocabulary,
    tenant,
  )
  expect(r.payload.observations.course).toEqual({
    unit: '1/263',
    x: '131',
    y: '139',
  })
})
it('他tenant語彙・未供給球種・未対応ルール・名簿不整合を閉拒否する', () => {
  expect(() =>
    prepareFirstBall(
      game(),
      observation,
      { ...vocabulary, tenantId: '33333333-3333-4333-8333-333333333333' },
      tenant,
    ),
  ).toThrow()
  expect(() =>
    prepareFirstBall(
      game(),
      observation,
      { ...vocabulary, pitchTypeKeys: [] },
      tenant,
    ),
  ).toThrow()
  const base = game()
  const rules = {
    ...base,
    applied_rules: {
      ...base.applied_rules,
      coldConditions: [{ pointDifference: 7, startInning: 5 }],
    },
  }
  expect(() =>
    prepareFirstBall(rules, observation, vocabulary, tenant),
  ).toThrow()
  const lineup = {
    ...base,
    lineups: {
      ...base.lineups,
      away: {
        ...base.lineups.away,
        entries: base.lineups.away.entries.map((e) =>
          e.batting_order === '1'
            ? { ...e, player_id: '55555555-5555-4555-8555-555555555555' }
            : e,
        ),
      },
    },
  }
  expect(() =>
    prepareFirstBall(lineup, observation, vocabulary, tenant),
  ).toThrow()
})
it('2球目・非有限タップ・不正D5を受理形へ補完しない', () => {
  const base = game()
  const second = {
    ...base,
    state: {
      ...base.state,
      stateFields: { ...base.state.stateFields, 'state.count.balls': '1' },
    },
  }
  expect(() =>
    prepareFirstBall(second, observation, vocabulary, tenant),
  ).toThrow()
  expect(() =>
    prepareFirstBall(
      game(),
      { ...observation, screenX: NaN },
      vocabulary,
      tenant,
    ),
  ).toThrow()
  expect(() =>
    firstBallEvent(prepareFirstBall(game(), observation, vocabulary, tenant), {
      d5: 'bad',
      d2: 1,
    }),
  ).toThrow()
})
