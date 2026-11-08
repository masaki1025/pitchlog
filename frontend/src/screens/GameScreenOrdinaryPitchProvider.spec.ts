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

import lineupFixture from '../api/fixtures/lineupPrefixGame.v3.json'
import {
  lineupContextFromRead,
  prepareLineupPrefix,
  prepareIntentionalWalk,
  type LineupRecordingContext,
  type PlayScreenObservation,
} from './GameScreenOrdinaryPitchProvider'
import { isLineupPrefixGame } from '../api/lineupPrefixGame'
import artifactIdentity from '../../public/domain/pitchlog-domain.json'

it('申告敬遠候補は投球観測なしで既v3封筒へ結ぶ', async () => {
  const raw = structuredClone(lineupFixture.value)
  if (!isLineupPrefixGame(raw)) throw new Error('構造fixture不正')
  const context = structuredClone(
    await lineupContextFromRead(raw, raw.prefix_ref.tenantId),
  ) as unknown as Record<string, unknown>
  const vectors = JSON.parse(
    readFileSync(
      resolve('../contracts/state-transition/lineup_play_prefix_cases_v1.json'),
      'utf8',
    ),
  ) as { cases: Array<{ caseId: string; request: Record<string, unknown> }> }
  const sourceCase = vectors.cases.find(
    (item) => item.caseId === 'V3-STRIKEOUT-1-B1-O2',
  )!
  const q = structuredClone(sourceCase.request)
  const t1 = q.t1 as Record<string, unknown>
  const source = q.source as Record<string, unknown>
  for (const state of [
    (t1.before as Record<string, unknown>).stateFields,
    (source.after as Record<string, unknown>).stateFields,
  ] as Array<Record<string, unknown>>) {
    state['state.count.strikes'] = '0'
    state['state.count.balls'] = '0'
    state['state.outs'] = '0'
  }
  ;((source.t2 as Record<string, unknown>).facts as Record<string, unknown>)[
    'afterOuts'
  ] = '0'
  source.executionArtifactSha256 = artifactIdentity.sha256
  context.prefixRef = q.prefixRef
  context.rules = q.rules
  context.after = t1.before
  context.lineupSource = source
  context.nextPosition = {
    d1: (source.position as Record<string, unknown>).d1,
    d2: (source.position as Record<string, unknown>).d2,
  }
  const prepared = await prepareIntentionalWalk(
    context as LineupRecordingContext,
    (q.prefixRef as Record<string, string>).tenantId,
    {
      eventId: crypto.randomUUID(),
      d5: crypto.randomUUID(),
      playId: crypto.randomUUID(),
    },
    crypto.randomUUID(),
  )
  expect(prepared.payload.observations).toEqual({ kind: 'intentional-walk' })
  expect(prepared.payload.calculation.response.value.t1.statFlags.投球数).toBe(
    false,
  )
  expect(
    prepared.payload.calculation.response.value.t1.after.stateFields[
      'state.runners'
    ],
  ).toBe('first-second-third')
})
it('両9枠と実投捕の読取を唯一artifactへ渡し、三振・攻守を計算しない', async () => {
  const value = lineupFixture.value
  if (!isLineupPrefixGame(value)) throw new Error('独立DTO不正')
  const context = await lineupContextFromRead(value, value.prefix_ref.tenantId)
  const observation: PlayScreenObservation = {
    resultId: 'batting-result.called-pitch',
    pitchTypeKey: 'tenant.pitch.straight',
    screenX: 131.5,
    screenY: 124,
    view: 'catcher',
    pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
    stance: null,
    battingSide: null,
  }
  const prepared = await prepareLineupPrefix(
    context,
    observation,
    {
      tenantId: value.prefix_ref.tenantId,
      pitchTypeKeys: ['tenant.pitch.straight'],
    },
    value.prefix_ref.tenantId,
    {
      d5: '44444444-4444-4444-8444-444444444444',
      eventId: '55555555-5555-4555-8555-555555555555',
      playId: '66666666-6666-4666-8666-666666666666',
    },
    '77777777-7777-4777-8777-777777777777',
  )
  expect(
    prepared.payload.calculation.response.value.t1.after.stateFields[
      'state.count.strikes'
    ],
  ).toBe('1')
  expect(
    prepared.payload.calculation.response.value.t1.after.battingOrderBySide,
  ).toEqual({ away: '1', home: '1' })
  expect(prepared.payload.participants).toEqual(value.participants)
  expect(context.after).toEqual(value.after)
})
it('別tenant・破損roster hashを真正sourceにしない', async () => {
  const value = structuredClone(lineupFixture.value)
  if (!isLineupPrefixGame(value)) throw new Error('独立DTO不正')
  await expect(
    lineupContextFromRead(value, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
  ).rejects.toThrow()
  await expect(
    lineupContextFromRead(
      { ...value, roster_digest: '0'.repeat(64) },
      value.prefix_ref.tenantId,
    ),
  ).rejects.toThrow()
})

it.each(['single', 'double', 'triple', 'home-run'] as const)(
  '画面で確認済み%sの全観測を既v3へ渡し次打者を唯一核から取得する',
  async (result) => {
    const value = lineupFixture.value
    if (!isLineupPrefixGame(value)) throw new Error('独立DTO不正')
    const context = await lineupContextFromRead(
      value,
      value.prefix_ref.tenantId,
    )
    const resultId = `batting-result.${result}` as const
    const battedHit = {
      resultId,
      battedBall: {
        typeKey: null,
        strengthKey: null,
        hitX: '0.25',
        hitY: '0.75',
        rawFielderPosition: null,
        resolvedFielderId: null,
      },
      officialScoringPayload: {
        kind: 'no-error' as const,
        errorCount: '0' as const,
        fielders: [] as const,
      },
      interferenceRuling: { kind: 'not-required' as const },
      runnerAdvanceOverridesByRunner: {
        kind: 'not-applied' as const,
        overrides: [] as const,
      },
      thirdOutObservation: { kind: 'none' as const },
      thirdOutTimingByRunner: {},
    }
    const observation: PlayScreenObservation = {
      resultId,
      battedHit,
      pitchTypeKey: 'tenant.pitch.straight',
      screenX: 131.5,
      screenY: 124,
      view: 'catcher',
      pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
      stance: null,
      battingSide: null,
    }
    const vocab = {
      tenantId: value.prefix_ref.tenantId,
      pitchTypeKeys: ['tenant.pitch.straight'],
    }
    const ids = {
      d5: '44444444-4444-4444-8444-444444444444',
      eventId: '55555555-5555-4555-8555-555555555555',
      playId: '66666666-6666-4666-8666-666666666666',
    }
    const wire = await prepareLineupPrefix(
      context,
      observation,
      vocab,
      value.prefix_ref.tenantId,
      ids,
      '77777777-7777-4777-8777-777777777777',
    )
    expect(wire.payload.observations).toEqual({
      ...battedHit,
      pitchTypeKey: observation.pitchTypeKey,
      course: { unit: '1/263', x: '132', y: '139' },
      pitchSpeed: observation.pitchSpeed,
      stance: null,
      battingSide: null,
    })
    const r = wire.payload.calculation.response.value
    expect(r.beforeParticipants).toEqual(context.lineupSource.participants)
    expect(r.t1.after.stateFields['state.battingOrder']).toBe('2')
    expect(r.t1.after.stateFields['state.runners']).toBe(
      {
        single: 'first',
        double: 'second',
        triple: 'third',
        'home-run': 'empty',
      }[result],
    )
    expect(r.t1.after.stateFields['state.score']).toEqual({
      home: '0',
      away: result === 'home-run' ? '1' : '0',
    })
    expect(r.t1.after.scoreboard.hits).toBe('1')
    for (const bad of [
      { ...observation, battedHit: null },
      {
        ...observation,
        battedHit: {
          ...battedHit,
          resultId:
            resultId === 'batting-result.single'
              ? ('batting-result.home-run' as const)
              : ('batting-result.single' as const),
        },
      },
      {
        ...observation,
        battedHit: {
          ...battedHit,
          battedBall: { ...battedHit.battedBall, hitX: '-0.0000001' },
        },
      },
      {
        ...observation,
        battedHit: {
          ...battedHit,
          battedBall: {
            ...battedHit.battedBall,
            resolvedFielderId: value.participants.batterId,
          },
        },
      },
      { ...observation, resultId: 'batting-result.ball' as const },
    ])
      await expect(
        prepareLineupPrefix(
          context,
          bad,
          vocab,
          value.prefix_ref.tenantId,
          ids,
          '77777777-7777-4777-8777-777777777777',
        ),
      ).rejects.toThrow()
  },
)
it('凡打死の全観測をv3へ渡し無走者の打者アウトを封印する', async () => {
  const value = lineupFixture.value
  if (!isLineupPrefixGame(value)) throw new Error('独立DTO不正')
  const context = await lineupContextFromRead(value, value.prefix_ref.tenantId)
  expect(context.after.stateFields['state.runners']).toBe('empty')
  expect(context.after.stateFields['state.outs']).toBe('0')
  const resultId = 'batting-result.batted-out'
  const observation: PlayScreenObservation = {
    resultId,
    battedHit: {
      resultId,
      battedBall: {
        typeKey: null,
        strengthKey: null,
        hitX: null,
        hitY: null,
        rawFielderPosition: null,
        resolvedFielderId: null,
      },
      officialScoringPayload: {
        kind: 'no-error',
        errorCount: '0',
        fielders: [],
      },
      interferenceRuling: { kind: 'not-required' },
      runnerAdvanceOverridesByRunner: { kind: 'not-applied', overrides: [] },
      thirdOutObservation: { kind: 'none' },
      thirdOutTimingByRunner: {},
    },
    pitchTypeKey: 'tenant.pitch.straight',
    screenX: 131.5,
    screenY: 124,
    view: 'catcher',
    pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
    stance: null,
    battingSide: null,
  }
  const wire = await prepareLineupPrefix(
    context,
    observation,
    {
      tenantId: value.prefix_ref.tenantId,
      pitchTypeKeys: ['tenant.pitch.straight'],
    },
    value.prefix_ref.tenantId,
    {
      d5: '44444444-4444-4444-8444-444444444444',
      eventId: '55555555-5555-4555-8555-555555555555',
      playId: '66666666-6666-4666-8666-666666666666',
    },
    '77777777-7777-4777-8777-777777777777',
  )
  expect(wire.payload.calculation.request.t1).toMatchObject({
    resultId,
    thirdOutObservation: 'none',
  })
  expect(wire.payload.calculation.response.value.t1).toMatchObject({
    batterDestination: { kind: 'out' },
    outEffect: { count: '1', targets: ['batter'] },
  })
})
