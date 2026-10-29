import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type {
  Request,
  Response as RosterResponse,
} from '../../../contracts/state-transition/initial_game_roster_v1'
import { useAuthStore } from '../stores/authStore'
import { setVerifiedAuthForTest } from './auth.test-support'
import {
  ApiError,
  ApiSessionUnverifiedError,
  ApiTenantVerificationError,
} from './client'
import {
  isStartedGame,
  isStartedRecordedGame,
  readStartedGame,
} from './startedGame'

const tenant = '11111111-1111-4111-8111-111111111111'
const other = '33333333-3333-4333-8333-333333333333'
const id = '22222222-2222-4222-8222-222222222222'
const cases = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/initial_game_roster_cases_v1.json',
    ),
    'utf8',
  ),
).cases as { id: string; request: Request; expected: RosterResponse }[]
function fixture(dh = false) {
  const selected = cases.find((row) => row.id === `NORMAL-DH-${dh}`)!
  if (!selected.expected.ok) throw new Error('transport素材が成功形ではない')
  const side = (name: 'away' | 'home') => ({
    lineup_id: name === 'away' ? tenant : other,
    team_record_id: selected.request[name].team_id,
    entries: selected.request[name].entries.map((entry) => ({
      ...entry,
      uniform_number_snapshot: '<保存背番号>',
    })),
  })
  return {
    read_kind: 'initial',
    id,
    scheduled_at: '2026-10-28T10:00:00+09:00',
    game_type_key: 'game_open',
    tournament_key: '<svg onload=alert(1)>',
    away_team_record_id: selected.request.away.team_id,
    home_team_record_id: selected.request.home.team_id,
    plate_umpire: null,
    section_label: '<保存ラベル>',
    week_label: null,
    day_label: null,
    game_number_label: null,
    status: 'in_progress',
    started_at: '2026-10-28T01:00:00.123456Z',
    applied_rules: {
      ruleSetId: tenant,
      regulationInnings: 9,
      coldConditions: [{ pointDifference: 7, startInning: 5 }],
      extensionLimit: 12,
      tiebreak: {
        startInning: 10,
        runnerPlacement: 'no_out_first_second',
        leadoffRule: 'continue_lineup',
      },
      dh,
    },
    lineups: { away: side('away'), home: side('home') },
    roster: selected.expected.value,
    state: {
      stateFields: {
        'state.half': 'top',
        'state.count.strikes': '0',
        'state.count.balls': '0',
        'state.outs': '0',
        'state.runners': 'empty',
        'state.battingOrder': '1',
        'state.tiebreakActive': false,
        'state.gameEnded': false,
        'state.inning': '1',
        'state.score': { home: '0', away: '0' },
      },
      scoreboard: {
        inningScores: { home: '0', away: '0' },
        hits: '0',
        errors: '0',
        strikeouts: '0',
        walks: '0',
      },
    },
    current_d4: `d4.1.${'A'.repeat(55)}`,
  }
}

function statFlags() {
  return Object.fromEntries(
    [
      '投球回算入アウト',
      '投球数',
      '奪三振',
      '与四球',
      '与死球',
      '被安打',
      '被本塁打',
      '失点',
      '失策',
      '打席',
      '打数',
      '安打',
      '本塁打',
      '塁打',
      '犠打',
      '犠飛',
      '四球',
      '死球',
      '三振',
      '打撃妨害出塁',
      '走塁妨害出塁',
      '得点',
      '打点',
    ].map((key) => [key, key === '投球数']),
  )
}
function recordedFixture() {
  const base = fixture()
  return {
    ...base,
    read_kind: 'recorded',
    after: {
      ...base.state,
      stateFields: { ...base.state.stateFields, 'state.count.balls': '1' },
    },
    history: [
      {
        kind: 'confirmed-play',
        difference: {
          stateFields: { 'state.count.balls': { before: '0', after: '1' } },
          scoreboard: {},
          statFlags: statFlags(),
        },
      },
    ],
    stat_flags: statFlags(),
    t2: {
      kind: 'evaluated-no-end-condition',
      evaluation_point: 'post-play',
      basis: {
        regulation: { kind: 'before-regulation-completion' },
        cold: { kind: 'no-configured-cold-condition' },
        extra_and_draw: { kind: 'before-extra-inning-boundary' },
        walk_off: { kind: 'top-half-without-score-change' },
      },
    },
    play_rows: [
      {
        id: other,
        game_id: id,
        source_event_id: tenant,
        play_number: 1,
        batting_order: 1,
        batter_id: tenant,
        pitcher_id: other,
        catcher_id: tenant,
        batting_side: null,
        stance: null,
        strategy_key: null,
        strategy_detail_key: null,
        strategy_result_key: null,
        batter_status: null,
        event_kind: 'pitch',
        course: { unit: '1/263', x: '132', y: '131' },
        pitch_type_key: 'u06-first-ball-fastball',
        batting_result_key: 'batting-result.ball',
        secondary_batting_result_key: null,
        raw_fielder_position: null,
        resolved_fielder_id: null,
        batted_ball_type: null,
        batted_ball_strength: null,
        hit_x: null,
        hit_y: null,
        pickoff_type: null,
        pickoff_detail: null,
        error_type: null,
        raw_error_position: null,
        resolved_error_player_id: null,
        pitch_speed: null,
        press: null,
        fake_run: null,
        comment: null,
        version: 1,
      },
    ],
  }
}
let pinia: Pinia
let body: unknown
let status: number
function reply(init?: RequestInit): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...(status === 200
        ? {
            'X-Pitchlog-Tenant-Match': '1',
            'X-Pitchlog-Tenant-Challenge': new Headers(init?.headers).get(
              'X-Pitchlog-Tenant-Challenge',
            )!,
          }
        : {}),
    },
  })
}
beforeEach(() => {
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), { teamId: tenant, teamName: 'A' })
  body = fixture()
  status = 200
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url, init) => reply(init)),
  )
})
afterEach(() => {
  disposePinia(pinia)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it.each([false, true])(
  'DH=%sの保存transportをGET・正規C2・Cookie・signalで取得する',
  async (dh) => {
    body = fixture(dh)
    const signal = new AbortController().signal
    expect(await readStartedGame(id, signal)).toEqual({
      kind: 'found',
      game: body,
    })
    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, init] = vi.mocked(fetch).mock.calls[0]!
    expect(url).toBe(`/api/games/${id}/started`)
    expect(init).toEqual({
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
      headers: {
        'X-Pitchlog-Expected-Tenant': tenant,
        'X-Pitchlog-Tenant-Challenge': expect.stringMatching(/^[0-9a-f-]{36}$/),
      },
      body: undefined,
      signal,
    })
  },
)
it.each([
  '../other',
  id.toUpperCase().replace('2', 'A'),
  `${id}/started`,
  `${id}\n`,
  '',
])('不正URL IDを通信前に拒否する: %s', async (invalid) => {
  await expect(readStartedGame(invalid)).rejects.toThrow('試合ID')
  expect(fetch).not.toHaveBeenCalled()
})
it.each([
  [404, 'not-found'],
  [409, 'recorded-unavailable'],
] as const)('HTTP%dだけを値なしの非成功へ写す', async (code, kind) => {
  status = code
  body = { error: { message: '固定エラー' }, holder_device: '非開示値' }
  expect(await readStartedGame(id)).toEqual({ kind })
  expect(fetch).toHaveBeenCalledTimes(1)
})
it.each([400, 401, 403, 500, 503])(
  'HTTP%dを非成功の例外として保持する',
  async (code) => {
    status = code
    body = { error: { message: '固定エラー' } }
    await expect(readStartedGame(id)).rejects.toBeInstanceOf(ApiError)
    expect(fetch).toHaveBeenCalledTimes(1)
  },
)
it('別試合の正常DTOを採用しない', async () => {
  body = { ...fixture(), id: other }
  await expect(readStartedGame(id)).rejects.toThrow('応答が不正')
})
it.each([
  null,
  {},
  { ...fixture(), read_kind: 'recorded' },
  { ...fixture(), read_kind: ['initial'] },
  { ...fixture(), holder_device: tenant },
  { ...fixture(), current_d4: null },
  { ...fixture(), current_d4: `d4.1.${'A'.repeat(55)}\n` },
  { ...fixture(), started_at: '2026-10-28T00:00:00Z\n' },
  { ...fixture(), current_d4: `d4.2.${'A'.repeat(55)}` },
  { ...fixture(), current_d4: `d4.1.${'A'.repeat(54)}` },
  { ...fixture(), current_d4: `d4.1.${'A'.repeat(54)}=` },
  { ...fixture(), id: [id] },
  { ...fixture(), game_type_key: ['game_open'] },
  { ...fixture(), game_type_key: 'unknown' },
  { ...fixture(), status: 'finished' },
  { ...fixture(), started_at: '2026-10-28T00:00:00' },
  { ...fixture(), tournament_key: '' },
])('不正transport/未対応scopeを採用しない %#', async (value) => {
  body = value
  await expect(readStartedGame(id)).rejects.toThrow('応答が不正')
})
function* objects(
  value: unknown,
  path: (string | number)[] = [],
): Generator<(string | number)[]> {
  if (Array.isArray(value)) {
    for (const [index, item] of value.entries())
      yield* objects(item, [...path, index])
  } else if (typeof value === 'object' && value !== null) {
    yield path
    for (const [key, item] of Object.entries(value))
      yield* objects(item, [...path, key])
  }
}
function at(
  value: unknown,
  path: (string | number)[],
): Record<string, unknown> {
  let item = value
  for (const key of path) item = (item as Record<string | number, unknown>)[key]
  return item as Record<string, unknown>
}
const paths = [...objects(fixture())]
it.each(paths.map((path) => [JSON.stringify(path), path] as const))(
  '全objectの未知keyと必須key欠落を拒否する: %s',
  async (_name, path) => {
    const extra = structuredClone(fixture())
    at(extra, path).recording_right_proof = '余剰値'
    expect(isStartedGame(extra)).toBe(false)
    const missing = structuredClone(fixture())
    delete at(missing, path)[Object.keys(at(missing, path))[0]!]
    expect(isStartedGame(missing)).toBe(false)
  },
)
it.each([
  ['lineups', 'away', 'lineup_id'],
  ['lineups', 'away', 'entries', 0, 'player_id'],
  ['lineups', 'away', 'entries', 0, 'batting_order'],
  ['roster', 'teams', 0, 'team_id'],
  ['roster', 'teams', 0, 'participants', 0, 'player', 'kind'],
  ['roster', 'teams', 0, 'participants', 0, 'roles', 0, 'position'],
  ['state', 'stateFields', 'state.count.balls'],
  ['state', 'stateFields', 'state.tiebreakActive'],
  ['state', 'stateFields', 'state.half'],
  ['state', 'stateFields', 'state.runners'],
  ['state', 'scoreboard', 'hits'],
  ['applied_rules', 'regulationInnings'],
  ['applied_rules', 'dh'],
])('入れ子のscalar不正を拒否する: %j', (...path) => {
  const invalid = structuredClone(fixture())
  at(invalid, path.slice(0, -1))[path.at(-1)!] = []
  expect(isStartedGame(invalid)).toBe(false)
})
it.each(['-1', '01', '1.0', '1e2', ' 0', '0\n', '0\r', '０', 0])(
  '非正準decimalを数値変換しない: %s',
  (value) => {
    const invalid = structuredClone(fixture())
    at(invalid.state, ['stateFields'])['state.count.balls'] = value
    expect(isStartedGame(invalid)).toBe(false)
  },
)
it('業務計算や初期値の推測をせずcanonical文字列を保つ', () => {
  const value = fixture()
  value.state.stateFields['state.count.balls'] =
    '123456789012345678901234567890'
  expect(isStartedGame(value)).toBe(true)
  expect(value.state.stateFields['state.count.balls']).toBe(
    '123456789012345678901234567890',
  )
})
it('C2 metadata欠落を正常bodyでも採用しない', async () => {
  vi.mocked(fetch).mockResolvedValue(
    new Response(JSON.stringify(body), {
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  await expect(readStartedGame(id)).rejects.toBeInstanceOf(
    ApiTenantVerificationError,
  )
})
it('未検証sessionは通信しない', async () => {
  useAuthStore().expireSession()
  await expect(readStartedGame(id)).rejects.toBeInstanceOf(
    ApiSessionUnverifiedError,
  )
  expect(fetch).not.toHaveBeenCalled()
})
it.each([
  [200, 'headers'],
  [200, 'body'],
  [404, 'headers'],
  [404, 'body'],
  [409, 'headers'],
  [409, 'body'],
] as const)(
  'HTTP%dの認証が%s待ち中に切り替われば古い結果を採用しない',
  async (code, point) => {
    status = code
    let finish!: () => void
    const wait = new Promise<void>((resolve) => {
      finish = resolve
    })
    let called!: () => void
    const entered = new Promise<void>((resolve) => {
      called = resolve
    })
    vi.mocked(fetch).mockImplementation(async (_url, init) => {
      if (point === 'headers') {
        called()
        await wait
      }
      const response = reply(init)
      if (point === 'body') {
        const raw = await response.text()
        vi.spyOn(response, 'text').mockImplementation(async () => {
          called()
          await wait
          return raw
        })
      }
      return response
    })
    const pending = readStartedGame(id)
    await entered
    setVerifiedAuthForTest(useAuthStore(), { teamId: other, teamName: 'B' })
    finish()
    await expect(pending).rejects.toBeInstanceOf(ApiTenantVerificationError)
    expect(fetch).toHaveBeenCalledTimes(1)
  },
)
it('abort/通信断は成功へ変換せず、既clientの不確実Cookie処理を維持する', async () => {
  const notice = vi.spyOn(useAuthStore(), 'invalidateUncertainCookie')
  vi.mocked(fetch).mockRejectedValue(new DOMException('中断', 'AbortError'))
  await expect(
    readStartedGame(id, new AbortController().signal),
  ).rejects.toThrow()
  expect(notice).toHaveBeenCalledTimes(1)
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('runtimeで配列IDを渡してもUUIDへ暗黙変換しない', async () => {
  await expect(readStartedGame([id] as unknown as string)).rejects.toThrow(
    '試合ID',
  )
  expect(fetch).not.toHaveBeenCalled()
})
it.each([
  ['lineups', 'away', 'entries'],
  ['roster', 'teams'],
  ['roster', 'teams', 0, 'participants'],
  ['roster', 'teams', 0, 'participants', 0, 'roles'],
])('固定長/9〜10要素の空配列を拒否する: %j', (...path) => {
  const invalid = structuredClone(fixture())
  at(invalid, path.slice(0, -1))[path.at(-1)!] = []
  expect(isStartedGame(invalid)).toBe(false)
})
it('cold/tiebreak無しの保存形も再計算せず受け取る', async () => {
  body = {
    ...fixture(),
    applied_rules: {
      ...fixture().applied_rules,
      coldConditions: [],
      extensionLimit: null,
      tiebreak: null,
    },
  }
  expect(await readStartedGame(id)).toEqual({ kind: 'found', game: body })
})

it('入れ子UUIDと守備位置の末尾改行を正準値として採用しない', () => {
  const invalid = structuredClone(fixture())
  invalid.lineups.away.entries[0]!.player_id += '\n'
  expect(isStartedGame(invalid)).toBe(false)
  const role = structuredClone(fixture())
  at(role, ['lineups', 'away', 'entries', 0, 'fielding_position']).position =
    '1\n'
  expect(isStartedGame(role)).toBe(false)
})

it('記録後200をfoundとして写し、initial検証器とは取り違えない', async () => {
  body = recordedFixture()
  expect(await readStartedGame(id)).toEqual({ kind: 'found', game: body })
  expect(isStartedGame(body)).toBe(false)
  expect(isStartedRecordedGame(body)).toBe(true)
})
it.each([
  [
    'after欠落',
    (value: Record<string, unknown>) => {
      delete value.after
    },
  ],
  [
    'history 2件',
    (value: Record<string, unknown>) => {
      ;(value.history as unknown[]).push((value.history as unknown[])[0])
    },
  ],
  [
    'history 0件',
    (value: Record<string, unknown>) => {
      value.history = []
    },
  ],
  [
    'play_rows 2件（2球目）',
    (value: Record<string, unknown>) => {
      const rows = value.play_rows as unknown[]
      rows.push(structuredClone(rows[0]))
    },
  ],
  [
    'stat_flagsのkey欠落',
    (value: Record<string, unknown>) => {
      delete (value.stat_flags as Record<string, unknown>)['打点']
    },
  ],
  [
    'stat_flagsの非bool',
    (value: Record<string, unknown>) => {
      ;(value.stat_flags as Record<string, unknown>)['打点'] = 'true'
    },
  ],
  [
    'play_rowsの除外列tenant_id',
    (value: Record<string, unknown>) => {
      ;(value.play_rows as Record<string, unknown>[])[0]!.tenant_id = value.id
    },
  ],
  [
    'play_rowsの物理座標',
    (value: Record<string, unknown>) => {
      ;(value.play_rows as Record<string, unknown>[])[0]!.course = {
        unit: '1/263',
        x: 132,
        y: '131',
      }
    },
  ],
  [
    'pressのbool化',
    (value: Record<string, unknown>) => {
      ;(value.play_rows as Record<string, unknown>[])[0]!.press = true
    },
  ],
  [
    'pressの閉集合外',
    (value: Record<string, unknown>) => {
      ;(value.play_rows as Record<string, unknown>[])[0]!.press = '2プレス'
    },
  ],
  [
    't2の未知kind',
    (value: Record<string, unknown>) => {
      ;(value.t2 as Record<string, unknown>).kind = 'unknown'
    },
  ],
  [
    'historyの未知key',
    (value: Record<string, unknown>) => {
      ;(value.history as Record<string, unknown>[])[0]!.extra = 1
    },
  ],
  [
    'topの未知key',
    (value: Record<string, unknown>) => {
      value.holder_device = value.id
    },
  ],
] as const)('記録後の不正transportを採用しない: %s', async (_name, change) => {
  const invalid = structuredClone(recordedFixture()) as Record<string, unknown>
  change(invalid)
  expect(isStartedRecordedGame(invalid)).toBe(false)
  body = invalid
  await expect(readStartedGame(id)).rejects.toThrow('応答が不正')
})
