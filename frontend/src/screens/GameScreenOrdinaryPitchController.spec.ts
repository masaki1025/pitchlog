import { canonicalAttemptEvents } from '../lib/firstBallAttemptPersistence'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { createPinia, setActivePinia, disposePinia } from 'pinia'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { useAuthStore } from '../stores/authStore'
import * as options from '../api/pitchTypeOptions'
import GameScreenOrdinaryPitch from './GameScreenOrdinaryPitch.vue'
import StrikeZone from '../components/zone/StrikeZone.vue'
import { GameScreenFirstBallController } from './GameScreenFirstBallController'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { IDBFactory, IDBKeyRange } from 'fake-indexeddb'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { ordinaryContextFromRead } from '../api/recordedPrefixGame'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { openDurableQueue } from '../lib/sync/durableQueue'
import { OrdinaryPitchAttemptPersistence } from '../lib/ordinaryPitchAttemptPersistence'
import * as transport from '../api/client.syncEvents'
import type { SingleWriterInjections } from '../lib/sync/singleWriter'
import type { OrdinaryScreenObservation } from './GameScreenOrdinaryPitchProvider'
import { GameScreenOrdinaryPitchController } from './GameScreenOrdinaryPitchController'
const raw = JSON.parse(
  readFileSync(
    resolve(process.cwd(), 'src/api/fixtures/recordedPrefixGame.v1.json'),
    'utf8',
  ),
).positive[0].value
const tenant = raw.prefix_ref.tenantId
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
let identity = { tenantId: tenant, epoch: 1, verified: true }
let controllers: GameScreenOrdinaryPitchController[] = []
const writer: SingleWriterInjections = {
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
function controller(injections = writer) {
  const value = new GameScreenOrdinaryPitchController(
    {
      ...ordinaryContextFromRead(raw, tenant),
      serverStamp: {
        recoveryGeneration: raw.recovery_generation,
        checkpointAnchor: raw.checkpoint_anchor,
        lastSavedAt: raw.last_saved_at,
      },
    },
    () => identity,
    injections,
  )
  controllers.push(value)
  return value
}
beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('IDBKeyRange', IDBKeyRange)
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
        d4: raw.current_d4,
        away_lineup_id: raw.lineups.away.lineup_id,
        home_lineup_id: raw.lineups.home.lineup_id,
        recording_right_proof: 'unit-only-proof',
        recovery_generation: raw.recovery_generation,
      },
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
})
afterEach(() => {
  controllers.forEach((c) => c.dispose())
  controllers = []
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
async function slots() {
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
      if (!('events' in body)) throw new Error('unit body invalid')
      const slot = request.slots[0]!
      return {
        sent: true,
        requestBody: body,
        response: {
          advancedD3: slot.d1,
          eventResults: [
            { d4: slot.d4, d1: slot.d1, d5: slot.d5, a5Result: '受理' },
          ],
        },
      }
    })
}
it('実artifact＋耐久queueでball/called/ballを通常appendし、mockACK成功とDB実証を混同しない', async () => {
  const post = accepted(),
    c = controller()
  expect(await c.inspect()).toBe('ready')
  for (const resultId of [
    'batting-result.ball',
    'batting-result.called-pitch',
    'batting-result.ball',
  ] as const)
    expect(await c.submit({ ...observation, resultId }, vocabulary)).toBe(
      'saved',
    )
  expect(await slots()).toBe(3)
  expect(post.mock.calls.map((call) => call[0].slots[0]!.d1)).toEqual([1, 2, 3])
  expect(
    post.mock.calls.map((call) => call[0].slots[0]!.event.fields.V6),
  ).toEqual([1, 1001, 2001])
  expect(c.context.after.stateFields['state.count.balls']).toBe('2')
  expect(c.context.after.stateFields['state.count.strikes']).toBe('1')
  expect(c.context.source).toBe('local-provisional')
  const store = await OrdinaryPitchAttemptPersistence.open()
  try {
    for (const call of post.mock.calls) {
      const request = call[0],
        slot = request.slots[0]!
      expect(
        (
          await store.read({
            tenantId: tenant,
            gameId: raw.id,
            d4: raw.current_d4,
            d1: slot.d1,
            d5: slot.d5 as string,
          })
        )?.attemptId,
      ).toBe(request.syncCredentials?.attempt)
    }
  } finally {
    store.close()
  }
})
it('offline中も次の独立操作をappendし、先行終結までHTTPは順序を守る', async () => {
  const post = vi
      .spyOn(transport, 'postSyncEvents')
      .mockResolvedValue({ sent: false, reason: 'no-response' }),
    c = controller()
  expect(await c.submit(observation, vocabulary)).toBe('pending')
  const first = post.mock.calls[0]![0]
  expect(
    await c.submit(
      { ...observation, resultId: 'batting-result.called-pitch' },
      vocabulary,
    ),
  ).toBe('pending')
  expect(await c.submit(observation, vocabulary)).toBe('pending')
  expect(post).toHaveBeenCalledOnce()
  expect(await slots()).toBe(3)
  c.dispose()
  const reloaded = controller()
  expect(await reloaded.inspect()).toBe('pending')
  expect(reloaded.context.prefixRef.length).toBe('3')
  expect(reloaded.context.source).toBe('local-provisional')
  expect(await reloaded.retry()).toBe('pending')
  const retry = post.mock.calls[1]![0]
  expect(retry.syncCredentials?.attempt).toBe(first.syncCredentials?.attempt)
  expect(transport.buildSyncEventRequestBody(retry)).toEqual(
    transport.buildSyncEventRequestBody(first),
  )
  expect(await slots()).toBe(3)
  post.mockRestore()
  const online = accepted()
  expect(await reloaded.retry()).toBe('saved')
  expect(await reloaded.retry()).toBe('saved')
  expect(await reloaded.retry()).toBe('saved')
  expect(online.mock.calls.map((call) => call[0].slots[0]!.d1)).toEqual([
    1, 2, 3,
  ])
  expect(await slots()).toBe(3)
})
it('未対応終端/権利欠落/auth世代/別tabでD1とHTTPを消費しない', async () => {
  const post = accepted(),
    denied = controller({})
  expect(await denied.submit(observation, vocabulary)).toBe('blocked')
  expect(await slots()).toBe(0)
  const c = controller()
  expect(await c.inspect()).toBe('ready')
  identity = { ...identity, epoch: 2 }
  expect(await c.submit(observation, vocabulary)).toBe('blocked')
  expect(await slots()).toBe(0)
  expect(post).not.toHaveBeenCalled()
  const other = controller({
    ...writer,
    lockManager: { request: async (_name, operation) => await operation(null) },
  })
  expect(await other.submit(observation, vocabulary)).toBe('blocked')
  expect(await slots()).toBe(0)
})
it('attempt保存失敗でも未送信slotを残し次独立記録を失わせない', async () => {
  const post = accepted(),
    c = controller()
  vi.spyOn(
    OrdinaryPitchAttemptPersistence.prototype,
    'prepare',
  ).mockRejectedValueOnce(new Error('unit storage failure'))
  expect(await c.submit(observation, vocabulary)).toBe('pending')
  expect(post).not.toHaveBeenCalled()
  expect(await slots()).toBe(1)
  expect(
    await c.submit(
      { ...observation, resultId: 'batting-result.called-pitch' },
      vocabulary,
    ),
  ).toBe('pending')
  expect(await slots()).toBe(2)
  expect(post).not.toHaveBeenCalled()
  expect(c.context.after.stateFields['state.count.strikes']).toBe('1')
})

it('旧初球の未確認slotも旧attemptを保持し、普通2球目を独立して暫定記録できる', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const seed = ordinaryContextFromRead(raw, tenant)
  const legacy = new GameScreenFirstBallController(
    { ...seed.game, read_kind: 'initial' },
    () => identity,
    writer,
  )
  try {
    expect(
      await legacy.submit(
        { ...observation, resultId: 'batting-result.ball' },
        vocabulary,
      ),
    ).toBe('pending')
    const original = post.mock.calls[0]![0]
    legacy.dispose()
    const current = controller()
    expect(await current.inspect()).toBe('pending')
    expect(current.context.after.stateFields['state.count.balls']).toBe('1')
    expect(
      await current.submit(
        { ...observation, resultId: 'batting-result.called-pitch' },
        vocabulary,
      ),
    ).toBe('pending')
    expect(await slots()).toBe(2)
    expect(post).toHaveBeenCalledOnce()
    expect(await current.retry()).toBe('pending')
    expect(post.mock.calls[1]![0].syncCredentials?.attempt).toBe(
      original.syncCredentials?.attempt,
    )
    expect(transport.buildSyncEventRequestBody(post.mock.calls[1]![0])).toEqual(
      transport.buildSyncEventRequestBody(original),
    )
  } finally {
    legacy.dispose()
  }
})

it('実reactive DTOを画面snapshotへ変換し、四条件だけでHTTPをHTTPS扱いにしない', async () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), { teamId: tenant, teamName: 'A' })
  vi.spyOn(options, 'readPitchTypeOptions').mockResolvedValue({
    items: [{ key: 'tenant.pitch.straight', display_name: '直球' }],
    next_cursor: null,
  })
  const errors: unknown[] = []
  const wrapper = mount(GameScreenOrdinaryPitch, {
    props: {
      context: reactive({
        ...ordinaryContextFromRead(raw, tenant),
        serverStamp: {
          recoveryGeneration: raw.recovery_generation,
          checkpointAnchor: raw.checkpoint_anchor,
          lastSavedAt: raw.last_saved_at,
        },
      }),
    },
    global: {
      plugins: [pinia],
      config: { errorHandler: (error) => errors.push(error) },
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
      wrapper.get('[data-testid="ordinary-pitch-result"]').findAll('option'),
    ).toHaveLength(4)
    for (const suffix of ['profile', 'mode', 'bucket', 'lockdown'])
      await wrapper
        .get(`[data-testid="first-ball-env-${suffix}"]`)
        .setValue(true)
    await wrapper
      .get('[data-testid="first-ball-pitch-type"]')
      .setValue('tenant.pitch.straight')
    wrapper.getComponent(StrikeZone).vm.$emit('tap', 131.5, 124)
    await wrapper.vm.$nextTick()
    const post = vi.spyOn(transport, 'postSyncEvents')
    expect(window.location.protocol).toBe('http:')
    expect(
      wrapper.get('[data-testid="first-ball-save"]').attributes('disabled'),
    ).toBeDefined()
    await wrapper.get('[data-testid="first-ball-save"]').trigger('click')
    expect(post).not.toHaveBeenCalled()
    expect(await slots()).toBe(0)
  } finally {
    wrapper.unmount()
    disposePinia(pinia)
  }
})

it('late再掲ACKの高い水位で、応答に無い次slotを受理扱いにしない', async () => {
  const offline = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const c = controller()
  expect(await c.submit(observation, vocabulary)).toBe('pending')
  expect(
    await c.submit(
      { ...observation, resultId: 'batting-result.called-pitch' },
      vocabulary,
    ),
  ).toBe('pending')
  offline.mockRestore()
  vi.spyOn(transport, 'postSyncEvents').mockImplementation(async (request) => {
    const body = transport.buildSyncEventRequestBody(request)
    if (!('events' in body)) throw new Error('unit body invalid')
    const slot = request.slots[0]!
    return {
      sent: true,
      requestBody: body,
      response: {
        advancedD3: 2,
        eventResults: [
          { d4: slot.d4, d1: slot.d1, d5: slot.d5, a5Result: '受理' },
        ],
      },
    }
  })
  expect(await c.retry()).toBe('saved')
  const q = await openDurableQueue({
    databaseName: 'pitchlog-first-ball-queue-' + tenant,
  })
  try {
    const first = await q.readSlot({ game: raw.id, d4: raw.current_d4 }, 1),
      second = await q.readSlot({ game: raw.id, d4: raw.current_d4 }, 2)
    expect(first?.state).not.toBe(second?.state)
    expect(second?.state).toBe('未送信')
    expect(await q.readNextD1({ game: raw.id, d4: raw.current_d4 })).toBe(3)
  } finally {
    q.close()
  }
})

it('server readの復旧世代と開始grantが違えば、既queue/HTTPを触らない', async () => {
  const seed = ordinaryContextFromRead(raw, tenant)
  const c = new GameScreenOrdinaryPitchController(
    {
      ...seed,
      serverStamp: {
        recoveryGeneration: '2',
        checkpointAnchor: null,
        lastSavedAt: raw.last_saved_at,
      },
    },
    () => identity,
    writer,
  )
  controllers.push(c)
  const post = accepted()
  expect(await c.inspect()).toBe('blocked')
  expect(await c.submit(observation, vocabulary)).toBe('blocked')
  expect(await slots()).toBe(0)
  expect(post).not.toHaveBeenCalled()
})

it('結果不明後にattempt DBが欠落しても再送で新attempt/D5を発行しない', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const prepare = vi.spyOn(OrdinaryPitchAttemptPersistence.prototype, 'prepare')
  const first = controller()
  expect(await first.submit(observation, vocabulary)).toBe('pending')
  expect(prepare).toHaveBeenCalledTimes(1)
  first.dispose()
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('pitchlog-ordinary-pitch-attempt')
    request.onsuccess = () => resolve()
    request.onerror = () => reject(new Error('unit delete failed'))
    request.onblocked = () => reject(new Error('unit delete blocked'))
  })
  const reloaded = controller()
  expect(await reloaded.inspect()).toBe('pending')
  const uuid = vi.spyOn(crypto, 'randomUUID')
  expect(await reloaded.retry()).toBe('blocked')
  expect(reloaded.retryEvidenceUnavailable).toBe(true)
  expect(post).toHaveBeenCalledTimes(1)
  expect(prepare).toHaveBeenCalledTimes(1)
  expect(uuid).not.toHaveBeenCalled()
  expect(await slots()).toBe(1)
})
it('初回attempt保存失敗もdurable never-sent証拠なしで再送prepareへ回さない', async () => {
  const post = accepted(),
    prepare = vi
      .spyOn(OrdinaryPitchAttemptPersistence.prototype, 'prepare')
      .mockRejectedValueOnce(new Error('unit prepare failed'))
  const first = controller()
  expect(await first.submit(observation, vocabulary)).toBe('pending')
  expect(await first.retry()).toBe('blocked')
  expect(prepare).toHaveBeenCalledTimes(1)
  expect(post).not.toHaveBeenCalled()
  expect(await slots()).toBe(1)
})
it('server確定3/localACK1だけのrestartでslot2→3を原body/attemptのまま終結する', async () => {
  const offline = vi
      .spyOn(transport, 'postSyncEvents')
      .mockResolvedValue({ sent: false, reason: 'no-response' }),
    first = controller()
  for (const resultId of [
    'batting-result.ball',
    'batting-result.called-pitch',
    'batting-result.ball',
  ] as const)
    expect(await first.submit({ ...observation, resultId }, vocabulary)).toBe(
      'pending',
    )
  offline.mockRestore()
  const initialAck = vi
    .spyOn(transport, 'postSyncEvents')
    .mockImplementation(async (request) => {
      const body = transport.buildSyncEventRequestBody(request)
      if (!('events' in body)) throw new Error('unit body')
      const slot = request.slots[0]!
      return {
        sent: true,
        requestBody: body,
        response: {
          advancedD3: 3,
          eventResults: [
            { d4: slot.d4, d1: slot.d1, d5: slot.d5, a5Result: '受理' },
          ],
        },
      }
    })
  expect(await first.retry()).toBe('saved')
  const confirmed = structuredClone(
    JSON.parse(
      readFileSync(
        resolve(process.cwd(), 'src/api/fixtures/recordedPrefixGame.v1.json'),
        'utf8',
      ),
    ).positive[2].value,
  )
  const local = first.context
  confirmed.prefix_ref = local.prefixRef
  confirmed.after = local.after
  confirmed.t2 = local.t2
  confirmed.rules = local.rules
  confirmed.next_position = local.nextPosition
  confirmed.checkpoint_anchor.revision = '3'
  confirmed.page = { items: [], next_cursor: null }
  const q = await openDurableQueue({
      databaseName: 'pitchlog-first-ball-queue-' + tenant,
    }),
    oldBody = new Map<number, string>(),
    oldAttempts = new Map<number, string>()
  const attempts = await OrdinaryPitchAttemptPersistence.open()
  try {
    for (const d1 of [2, 3]) {
      const slot = (await q.readSlot({ game: raw.id, d4: raw.current_d4 }, d1))!
      const fixed = (await attempts.read({
        tenantId: tenant,
        gameId: raw.id,
        d4: raw.current_d4,
        d1,
        d5: slot.d5 as string,
      }))!
      oldBody.set(d1, fixed.requestJson)
      oldAttempts.set(d1, fixed.attemptId)
      if (d1 === 3)
        confirmed.last_entry = (
          slot.event.fields.V7 as {
            calculation: { response: { value: { newHistoryEntry: unknown } } }
          }
        ).calculation.response.value.newHistoryEntry
    }
  } finally {
    q.close()
    attempts.close()
  }
  first.dispose()
  initialAck.mockRestore()
  const reloaded = new GameScreenOrdinaryPitchController(
    {
      ...ordinaryContextFromRead(confirmed, tenant),
      serverStamp: {
        recoveryGeneration: confirmed.recovery_generation,
        checkpointAnchor: confirmed.checkpoint_anchor,
        lastSavedAt: confirmed.last_saved_at,
      },
    },
    () => identity,
    writer,
  )
  controllers.push(reloaded)
  expect(await reloaded.inspect()).toBe('pending')
  const online = accepted()
  expect(await reloaded.retry()).toBe('saved')
  expect(await reloaded.retry()).toBe('saved')
  expect(online.mock.calls.map((call) => call[0].slots[0]!.d1)).toEqual([2, 3])
  for (const call of online.mock.calls) {
    const request = call[0],
      slot = request.slots[0]!,
      body = transport.buildSyncEventRequestBody(request)
    expect(request.syncCredentials?.attempt).toBe(oldAttempts.get(slot.d1))
    expect('events' in body && sameCanonical(body.events)).toBe(
      oldBody.get(slot.d1),
    )
  }
  expect(await slots()).toBe(3)
  expect(reloaded.context.after).toEqual(confirmed.after)
  expect(reloaded.context.source).toBe('server-confirmed')
})
function sameCanonical(events: readonly unknown[]): string {
  // テスト側も既の正準化のみを使い、再送本文を補修しない。
  return canonicalAttemptEvents(events)
}
