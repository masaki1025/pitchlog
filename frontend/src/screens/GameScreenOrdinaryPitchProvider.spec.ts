import { ORDINARY_APPEND_POLICY } from '../api/ordinaryAppendPolicy'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { afterAll, beforeAll, expect, it } from 'vitest'
import type { StartedGame } from '../api/startedGame'
import {
  prepareOrdinaryPitch,
  ordinaryPitchEvent,
  type OrdinaryRecordingContext,
  type OrdinaryScreenObservation,
} from './GameScreenOrdinaryPitchProvider'
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

const observation: OrdinaryScreenObservation = {
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
function context(): OrdinaryRecordingContext {
  const initial = game()
  return {
    game: initial,
    prefixRef: {
      version: '1',
      tenantId: tenant,
      gameId: initial.id,
      generation: initial.current_d4,
      length: '0',
    },
    rules: combined.rules,
    after: initial.state,
    t2: null,
    priorKind: 'started-initial',
    nextPosition: { d1: '1', d2: '1' },
    source: 'server-confirmed',
    appendPolicy: ORDINARY_APPEND_POLICY,
  }
}
it('実artifactのball/called/ballを同prefixから合成し、provisionalを保存済みと称さない', () => {
  let current = context()
  for (const [resultId, balls, strikes] of [
    ['batting-result.ball', '1', '0'],
    ['batting-result.called-pitch', '1', '1'],
    ['batting-result.ball', '2', '1'],
  ] as const) {
    const prepared = prepareOrdinaryPitch(
      current,
      { ...observation, resultId },
      vocabulary,
      tenant,
    )
    const value = prepared.payload.calculation.response.value
    expect(value.t1.after.stateFields['state.count.balls']).toBe(balls)
    expect(value.t1.after.stateFields['state.count.strikes']).toBe(strikes)
    expect(prepared.stateDiff).toEqual(value.newHistoryEntry.difference)
    current = {
      ...current,
      prefixRef: value.nextPrefixRef,
      after: value.t1.after,
      t2: value.t2,
      priorKind: 'evaluated-prefix',
      source: 'local-provisional',
      nextPosition: {
        d1: String(BigInt(current.nextPosition.d1) + 1n),
        d2: String(BigInt(current.nextPosition.d2) + 1n),
      },
    }
  }
  expect(current.prefixRef.length).toBe('3')
  expect(current.source).toBe('local-provisional')
})
it('prefix水位とD1/D2を同値にせず、既スロット形へ運ぶ', () => {
  const seed = context()
  const prepared = prepareOrdinaryPitch(
    { ...seed, nextPosition: { d1: '21', d2: '101' } },
    observation,
    vocabulary,
    tenant,
  )
  const event = ordinaryPitchEvent(prepared, tenant)
  expect(prepared.payload.calculation.request.prefixRef.length).toBe('0')
  expect(event.fields.V6).toBe(101)
  expect(event.fields).not.toHaveProperty('V2')
  expect(event.fields.V1).toBe(tenant)
  expect(event.fields.V8).toEqual(prepared.stateDiff)
})
it('tenant/世代/語彙/名簿不一致と非有限座標を補修せず拒否する', () => {
  const seed = context()
  expect(() =>
    prepareOrdinaryPitch(
      seed,
      observation,
      { ...vocabulary, tenantId: seed.game.id },
      tenant,
    ),
  ).toThrow()
  expect(() =>
    prepareOrdinaryPitch(
      { ...seed, prefixRef: { ...seed.prefixRef, generation: 'other' } },
      observation,
      vocabulary,
      tenant,
    ),
  ).toThrow()
  expect(() =>
    prepareOrdinaryPitch(
      seed,
      { ...observation, screenX: NaN },
      vocabulary,
      tenant,
    ),
  ).toThrow()
  const bad = structuredClone(seed)
  Object.assign(bad.game.lineups.home, { entries: [] })
  expect(() =>
    prepareOrdinaryPitch(bad, observation, vocabulary, tenant),
  ).toThrow()
  expect(() =>
    ordinaryPitchEvent(
      prepareOrdinaryPitch(seed, observation, vocabulary, tenant),
      'new-not-uuid',
    ),
  ).toThrow()
})
it('支持37全入力を実artifactへ渡し、終端球は成功へ補完しない', () => {
  const rows = [
    ...JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          '../contracts/state-transition/ordinary_pitch_vectors_v1.json',
        ),
        'utf8',
      ),
    ).cases,
    ...JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          '../contracts/state-transition/ordinary_two_strike_foul_candidate_v1.json',
        ),
        'utf8',
      ),
    ).cases,
  ]
  expect(rows).toHaveLength(37)
  const first = prepareOrdinaryPitch(context(), observation, vocabulary, tenant)
    .payload.calculation.response.value
  for (const row of rows) {
    const seed = {
      ...context(),
      prefixRef: first.nextPrefixRef,
      after: row.request.before,
      t2: first.t2,
      priorKind: 'evaluated-prefix' as const,
    }
    const actual = prepareOrdinaryPitch(
      seed,
      { ...observation, resultId: row.request.resultId },
      vocabulary,
      tenant,
    )
    const { historyContext, ...expected } = row.expected.value
    expect(actual.payload.calculation.response.value.t1).toEqual(expected)
    expect(actual.stateDiff).toEqual(historyContext[0].difference)
  }
  const seed = {
    ...context(),
    prefixRef: first.nextPrefixRef,
    after: structuredClone(first.t1.after),
    t2: first.t2,
    priorKind: 'evaluated-prefix' as const,
  }
  Object.assign(seed.after.stateFields, { 'state.count.balls': '3' })
  expect(() =>
    prepareOrdinaryPitch(seed, observation, vocabulary, tenant),
  ).toThrow()
})

import {
  playContextFromRead,
  preparePlayPrefix,
  playPrefixEvent,
} from './GameScreenOrdinaryPitchProvider'
import {
  isPlayPrefixGame,
  type PlayPrefixGame,
} from '../api/recordedPrefixGame'
const prefixFixture = JSON.parse(
  readFileSync(
    resolve(process.cwd(), 'src/api/fixtures/recordedPrefixGame.v1.json'),
    'utf8',
  ),
).positive[0].value
function initialPlayRead(): PlayPrefixGame {
  const old = structuredClone(prefixFixture)
  return {
    ...old,
    read_kind: 'play-prefix',
    last_source: null,
    prior_artifact_sha256:
      '052f5c0a61d861176a2de5ae06055e16c9a0b2a192cfdc861a740cde4d5bedc4',
    pa_start_source: { kind: 'started-game', id: old.id },
    bridge_checkpoint: {
      id: '10000000-0000-4000-8000-000000000099',
      revision: '1',
      digest: 'a'.repeat(64),
    },
    storage_anchor: null,
    bridge_origin: null,
    runners: [],
    participants: null,
  }
}
it('開始直後0球の実GET形からHBPを唯一artifactへ渡し、元予約IDと次打者runnerを保持する', async () => {
  const read = initialPlayRead()
  expect(isPlayPrefixGame(read)).toBe(true)
  const c = await playContextFromRead(read, read.prefix_ref.tenantId)
  const team = read.roster.teams.find((t) => t.side === 'away')!
  const candidate = team.participants.find(
    (p) => p.batting_slot.kind === 'slot' && p.batting_slot.slot === '2',
  )!
  const nextBatter = {
    batterId: candidate.player.player_id,
    battingOrder: '2' as const,
  }
  const ids = {
    d5: crypto.randomUUID(),
    eventId: crypto.randomUUID(),
    playId: crypto.randomUUID(),
  }
  const wire = await preparePlayPrefix(
    c,
    { ...observation, resultId: 'batting-result.hit-by-pitch', nextBatter },
    {
      tenantId: read.prefix_ref.tenantId,
      pitchTypeKeys: [observation.pitchTypeKey],
    },
    read.prefix_ref.tenantId,
    ids,
    crypto.randomUUID(),
  )
  const q = wire.payload.calculation.request,
    r = wire.payload.calculation.response.value
  expect(q.source.bridge?.kind).toBe('started-initial')
  expect(q.source.lastSource).toBeNull()
  expect(q.source.position).toEqual({ d1: '1', d2: '1', appliedWatermark: '0' })
  expect(r.t1.after.stateFields['state.count.balls']).toBe('0')
  expect(r.t1.after.stateFields['state.battingOrder']).toBe('2')
  expect(r.t1.after.scoreboard.walks).toBe('0')
  expect(r.runners).toEqual([
    {
      runnerId: q.source.participants.batterId,
      responsiblePitcherId: q.source.participants.pitcherId,
      base: '1',
      status: '継続',
      statusSource: 'auto',
    },
  ])
  expect(playPrefixEvent(wire, ids.d5).fields.V1).toBe(ids.d5)
  expect(() => playPrefixEvent(wire, crypto.randomUUID())).toThrow()
  await expect(
    preparePlayPrefix(
      c,
      {
        ...observation,
        resultId: 'batting-result.hit-by-pitch',
        nextBatter: { ...nextBatter, battingOrder: '3' },
      },
      {
        tenantId: read.prefix_ref.tenantId,
        pitchTypeKeys: [observation.pitchTypeKey],
      },
      read.prefix_ref.tenantId,
      ids,
      crypto.randomUUID(),
    ),
  ).rejects.toThrow()
  await expect(
    preparePlayPrefix(
      c,
      { ...observation, resultId: 'batting-result.walk', nextBatter },
      {
        tenantId: read.prefix_ref.tenantId,
        pitchTypeKeys: [observation.pitchTypeKey],
      },
      read.prefix_ref.tenantId,
      ids,
      crypto.randomUUID(),
    ),
  ).rejects.toThrow()
})
