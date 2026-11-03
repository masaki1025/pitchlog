import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { useAuthStore } from '../stores/authStore'
import * as options from '../api/pitchTypeOptions'
import GameScreenFirstBall from './GameScreenFirstBall.vue'
import StrikeZone from '../components/zone/StrikeZone.vue'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { IDBFactory } from 'fake-indexeddb'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import type { StartedGame, StartedGameRead } from '../api/startedGame'
import type { FirstBallScreenObservation } from './GameScreenFirstBallProvider'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { FirstBallAttemptPersistence } from '../lib/firstBallAttemptPersistence'
import { openDurableQueue } from '../lib/sync/durableQueue'
import * as transport from '../api/client.syncEvents'
import { GameScreenFirstBallController } from './GameScreenFirstBallController'
import type { SingleWriterInjections } from '../lib/sync/singleWriter'
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

let controllers: GameScreenFirstBallController[] = []
let identity = { tenantId: tenant, epoch: 1, verified: true }
const singleWriter: SingleWriterInjections = {
  resolvePreconditions: () => ({
    topLevelHttps: true,
    sameBrowserProfile: true,
    sameBrowsingMode: true,
    sameStorageBucket: true,
    siteStorageAvailable: true,
    lockdownModeNotApplied: true,
  }),
  revalidateSingleWriter: () => true,
  lockManager: {
    request: async (_name, operation) => await operation({ name: 'test-lock' }),
  },
}
function controller(injections = singleWriter) {
  const c = new GameScreenFirstBallController(
    game(),
    () => identity,
    injections,
  )
  controllers.push(c)
  return c
}
beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('isSecureContext', true)
  const context = createContext({})
  new Script(
    readFileSync(
      resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
      'utf8',
    ),
  ).runInContext(context)
  vi.stubGlobal(
    'PitchlogDomain',
    Object.getOwnPropertyDescriptor(context, 'PitchlogDomain')!.value,
  )
  identity = { tenantId: tenant, epoch: 1, verified: true }
  const g = game()
  vi.spyOn(GameStartPersistence, 'open').mockResolvedValue({
    readDevice: async () => ({
      tenant_id: tenant,
      device_id: tenant,
      device_credential: 'unit-only-credential',
    }),
    readStart: async () => ({
      status: 'received',
      grant: {
        device_id: tenant,
        d4: g.current_d4,
        away_lineup_id: g.lineups.away.lineup_id,
        home_lineup_id: g.lineups.home.lineup_id,
        recording_right_proof: 'unit-only-proof',
      },
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
})
afterEach(() => {
  for (const c of controllers) c.dispose()
  controllers = []
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
async function count() {
  const q = await openDurableQueue({
    databaseName: 'pitchlog-first-ball-queue-' + tenant,
  })
  try {
    return await q.countSlots()
  } finally {
    q.close()
  }
}
function accepted() {
  return vi
    .spyOn(transport, 'postSyncEvents')
    .mockImplementation(async (request) => {
      const body = transport.buildSyncEventRequestBody(request)
      if (!('events' in body)) throw new Error('test request invalid')
      const s = request.slots[0]!
      return {
        sent: true,
        requestBody: body,
        response: {
          advancedD3: s.d1,
          eventResults: [{ d4: s.d4, d1: s.d1, d5: s.d5, a5Result: '受理' }],
        },
      }
    })
}
it('初回は既queueへ1件だけ追記し、attempt耐久保存後に送る', async () => {
  const post = accepted(),
    c = controller()
  expect(await c.inspect()).toBe('ready')
  expect(await c.submit(observation, vocabulary)).toBe('saved')
  expect(post).toHaveBeenCalledOnce()
  expect(await count()).toBe(1)
  const store = await FirstBallAttemptPersistence.open()
  try {
    const record = await store.read(tenant, game().id)
    expect(record?.attemptId).toBe(
      post.mock.calls[0]![0].syncCredentials?.attempt,
    )
  } finally {
    store.close()
  }
})
it('未応答後の別controller新確定はappend0/HTTP0、再送は旧D5/attempt/本文を保持', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const first = controller()
  expect(await first.submit(observation, vocabulary)).toBe('pending')
  expect(await count()).toBe(1)
  const second = controller()
  expect(await second.inspect()).toBe('pending')
  expect(await second.submit(observation, vocabulary)).toBe('pending')
  expect(post).toHaveBeenCalledOnce()
  expect(await count()).toBe(1)
  const sentFirst = post.mock.calls[0]![0]
  expect(await second.retry()).toBe('pending')
  const sentRetry = post.mock.calls[1]![0]
  expect(sentRetry.syncCredentials?.attempt).toBe(
    sentFirst.syncCredentials?.attempt,
  )
  expect(transport.buildSyncEventRequestBody(sentRetry)).toEqual(
    transport.buildSyncEventRequestBody(sentFirst),
  )
  expect(await count()).toBe(1)
})
it('環境前提未確認・auth世代変更はqueue追記/HTTPを行わない', async () => {
  const post = accepted(),
    missing = controller({})
  expect(await missing.submit(observation, vocabulary)).toBe('blocked')
  expect(await count()).toBe(0)
  expect(post).not.toHaveBeenCalled()
  const changed = controller()
  expect(await changed.inspect()).toBe('ready')
  identity = { ...identity, epoch: 2 }
  expect(await changed.submit(observation, vocabulary)).toBe('blocked')
  expect(await count()).toBe(0)
  expect(post).not.toHaveBeenCalled()
})
it('別タブがlock所有中なら追記・送信をしない', async () => {
  const post = accepted(),
    c = controller({
      ...singleWriter,
      lockManager: {
        request: async (_name, operation) => await operation(null),
      },
    })
  expect(await c.submit(observation, vocabulary)).toBe('blocked')
  expect(await count()).toBe(0)
  expect(post).not.toHaveBeenCalled()
})

it('recorded取得後も旧未送信slotを再送し、新規確定とACK未適用の読み替えを拒否する', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const initial = controller()
  expect(await initial.submit(observation, vocabulary)).toBe('pending')
  const recorded = {
    ...game(),
    read_kind: 'recorded',
  } as unknown as StartedGameRead
  const restored = new GameScreenFirstBallController(
    recorded,
    () => identity,
    singleWriter,
  )
  controllers.push(restored)
  expect(await restored.inspect()).toBe('pending')
  expect(await restored.submit(observation, vocabulary)).toBe('blocked')
  expect(post).toHaveBeenCalledOnce()
  expect(await count()).toBe(1)
  post.mockImplementation(async (request) => {
    const body = transport.buildSyncEventRequestBody(request)
    if (!('events' in body)) throw new Error('bad request')
    const slot = request.slots[0]!
    return {
      sent: true,
      requestBody: body,
      response: {
        advancedD3: 1,
        eventResults: [
          { d4: slot.d4, d1: slot.d1, d5: slot.d5, a5Result: '受理' },
        ],
      },
    }
  })
  const first = post.mock.calls[0]![0]
  expect(await restored.retry()).toBe('saved')
  expect(post.mock.calls[1]![0].syncCredentials?.attempt).toBe(
    first.syncCredentials?.attempt,
  )
  expect(await count()).toBe(1)
})

it('Vue reactiveの実DTOを画面境界で固定snapshotへ変換し非同期例外を残さない', async () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), { teamId: tenant, teamName: 'A' })
  vi.spyOn(options, 'readPitchTypeOptions').mockResolvedValue({
    items: [{ key: 'tenant.pitch.straight', display_name: '直球' }],
    next_cursor: null,
  })
  const errors: unknown[] = []
  const wrapper = mount(GameScreenFirstBall, {
    props: { game: reactive(game()) },
    global: {
      plugins: [pinia],
      config: {
        errorHandler: (error) => {
          errors.push(error)
        },
      },
    },
  })
  try {
    await vi.waitFor(() =>
      expect(
        wrapper.find('[data-testid="first-ball-pitch-type"]').exists(),
      ).toBe(true),
    )
    expect(errors).toEqual([])
    expect(
      wrapper.get('[data-testid="first-ball-save"]').attributes('disabled'),
    ).toBeDefined()
    // loopbackのsecure contextだけで規範のHTTPSを成立扱いにしない。
    expect(window.location.protocol).toBe('http:')
    vi.stubGlobal('isSecureContext', true)
    for (const suffix of ['profile', 'mode', 'bucket', 'lockdown']) {
      await wrapper
        .get(`[data-testid="first-ball-env-${suffix}"]`)
        .setValue(true)
    }
    await wrapper
      .get('[data-testid="first-ball-pitch-type"]')
      .setValue('tenant.pitch.straight')
    wrapper.getComponent(StrikeZone).vm.$emit('tap', 131.5, 124)
    await wrapper.vm.$nextTick()
    const post = vi.spyOn(transport, 'postSyncEvents')
    expect(
      wrapper.get('[data-testid="first-ball-save"]').attributes('disabled'),
    ).toBeDefined()
    await wrapper.get('[data-testid="first-ball-save"]').trigger('click')
    expect(post).not.toHaveBeenCalled()
  } finally {
    wrapper.unmount()
  }
})

it('initialでも旧slotのattempt記録が欠落したら新IDを発行せず再送を閉じる', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const first = controller()
  expect(await first.submit(observation, vocabulary)).toBe('pending')
  first.dispose()
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('pitchlog-first-ball-attempt')
    request.onsuccess = () => resolve()
    request.onerror = () => reject(new Error('test cleanup failed'))
  })
  const restored = controller()
  expect(await restored.inspect()).toBe('pending')
  expect(await restored.retry()).toBe('blocked')
  expect(post).toHaveBeenCalledOnce()
  expect(await count()).toBe(1)
  const store = await FirstBallAttemptPersistence.open()
  try {
    expect(await store.read(tenant, game().id)).toBeNull()
  } finally {
    store.close()
  }
})
