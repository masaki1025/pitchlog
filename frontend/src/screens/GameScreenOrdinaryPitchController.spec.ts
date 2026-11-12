import type { LineupPlayPrefixV7 } from '../../../contracts/state-transition/lineup_play_prefix_payload_v1'
import * as domainWrapper from '../lib/generated/wrappers/domainArtifact'
import { queueStateId } from '../lib/sync/queueState'
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
import {
  OrdinaryPreparedEnvelopePersistence,
  type PreparedEnvelope,
} from '../lib/ordinaryPreparedEnvelopePersistence'
import * as transport from '../api/client.syncEvents'
import * as recovery from '../api/syncAttemptRecovery'
import { SyncAttemptBarrier } from '../lib/syncAttemptBarrier'
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
function accepted(a5Result = '受理') {
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
          eventResults: [{ d4: slot.d4, d1: slot.d1, d5: slot.d5, a5Result }],
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
  const online = accepted('重複')
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

it('commit後ACK喪失のreloadはserver1/未ACKslot1から元attemptで重複を終結し、追加計算・UUID・暫定加算をしない', async () => {
  const offline = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const first = controller()
  expect(await first.submit(observation, vocabulary)).toBe('pending')
  const original = offline.mock.calls[0]![0]
  const local = first.context
  const confirmed = structuredClone(
    JSON.parse(
      readFileSync(
        resolve(process.cwd(), 'src/api/fixtures/recordedPrefixGame.v1.json'),
        'utf8',
      ),
    ).positive[1].value,
  )
  confirmed.prefix_ref = local.prefixRef
  confirmed.after = local.after
  confirmed.t2 = local.t2
  confirmed.rules = local.rules
  confirmed.next_position = local.nextPosition
  confirmed.page = { items: [], next_cursor: null }
  confirmed.last_entry = (
    original.slots[0]!.event.fields.V7 as {
      calculation: { response: { value: { newHistoryEntry: unknown } } }
    }
  ).calculation.response.value.newHistoryEntry
  first.dispose()
  offline.mockRestore()
  const next = new GameScreenOrdinaryPitchController(
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
  controllers.push(next)
  const math = vi.spyOn(domainWrapper, 'invokeFirstBallDomain'),
    uuid = vi.spyOn(crypto, 'randomUUID')
  expect(await next.inspect()).toBe('pending')
  expect(next.context.after).toEqual(confirmed.after)
  expect(next.context.source).toBe('server-confirmed')
  const online = accepted('重複')
  expect(await next.retry()).toBe('saved')
  expect(online).toHaveBeenCalledOnce()
  const retried = online.mock.calls[0]![0]
  expect(retried.syncCredentials?.attempt).toBe(
    original.syncCredentials?.attempt,
  )
  expect(transport.buildSyncEventRequestBody(retried)).toEqual(
    transport.buildSyncEventRequestBody(original),
  )
  expect(math).not.toHaveBeenCalled()
  expect(uuid).not.toHaveBeenCalled()
  expect(next.context.after).toEqual(confirmed.after)
  expect(next.context.prefixRef.length).toBe('1')
  const queue = await openDurableQueue({
    databaseName: 'pitchlog-first-ball-queue-' + tenant,
  })
  try {
    expect(
      (await queue.readSlot({ game: raw.id, d4: raw.current_d4 }, 1))?.state,
    ).toBe(queueStateId('同期済み'))
    expect(await queue.countSlots()).toBe(1)
  } finally {
    queue.close()
  }
})

import {
  playContextFromRead,
  isPlayRecordingContext,
} from './GameScreenOrdinaryPitchProvider'
import type { PlayPrefixGame } from '../api/recordedPrefixGame'
async function playController() {
  const read: PlayPrefixGame = {
    ...structuredClone(raw),
    read_kind: 'play-prefix',
    last_source: null,
    prior_artifact_sha256:
      '052f5c0a61d861176a2de5ae06055e16c9a0b2a192cfdc861a740cde4d5bedc4',
    pa_start_source: { kind: 'started-game', id: raw.id },
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
  const c = new GameScreenOrdinaryPitchController(
    await playContextFromRead(read, tenant),
    () => identity,
    writer,
  )
  controllers.push(c)
  return c
}
function nextBatter() {
  const p = raw.roster.teams[0].participants.find(
    (p: { batting_slot: { kind: string; slot?: string } }) =>
      p.batting_slot.kind === 'slot' && p.batting_slot.slot === '2',
  )
  return { batterId: p.player.player_id, battingOrder: '2' as const }
}
it('v2初回HBP→次ordinaryを同耐久queueへ積み、reload/元D5/予約ID/attemptを変えず再送する', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const c = await playController()
  expect(await c.inspect()).toBe('ready')
  expect(
    await c.submit(
      {
        ...observation,
        resultId: 'batting-result.hit-by-pitch',
        nextBatter: nextBatter(),
      },
      vocabulary,
    ),
  ).toBe('pending')
  expect(await c.submit(observation, vocabulary)).toBe('pending')
  expect(await slots()).toBe(2)
  expect(post).toHaveBeenCalledOnce()
  expect(c.context.after.stateFields['state.battingOrder']).toBe('2')
  expect(c.context.after.stateFields['state.count.balls']).toBe('1')
  const first = post.mock.calls[0]![0],
    original = transport.buildSyncEventRequestBody(first)
  c.dispose()
  const restored = await playController()
  expect(await restored.inspect()).toBe('pending')
  expect(restored.context.prefixRef.length).toBe('2')
  expect(restored.canAppend).toBe(true)
  expect(isPlayRecordingContext(restored.context)).toBe(true)
  expect(await restored.retry()).toBe('pending')
  expect(transport.buildSyncEventRequestBody(post.mock.calls[1]![0])).toEqual(
    original,
  )
  expect(post.mock.calls[1]![0].syncCredentials?.attempt).toBe(
    first.syncCredentials?.attempt,
  )
  post.mockRestore()
  const online = accepted()
  expect(await restored.retry()).toBe('saved')
  expect(await restored.retry()).toBe('saved')
  expect(online.mock.calls.map((c) => c[0].slots[0]!.d1)).toEqual([1, 2])
})
it('v2四球B0/誤nextBatterはD1/HTTPを消費しない', async () => {
  const post = accepted(),
    c = await playController()
  expect(
    await c.submit(
      {
        ...observation,
        resultId: 'batting-result.walk',
        nextBatter: nextBatter(),
      },
      vocabulary,
    ),
  ).toBe('blocked')
  expect(
    await c.submit(
      {
        ...observation,
        resultId: 'batting-result.hit-by-pitch',
        nextBatter: { ...nextBatter(), batterId: tenant },
      },
      vocabulary,
    ),
  ).toBe('blocked')
  expect(await slots()).toBe(0)
  expect(post).not.toHaveBeenCalled()
})
it('未確認V1suffixは捏造v2bridgeせず元V1body/attemptの再送だけを保持する', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const legacy = controller()
  expect(await legacy.submit(observation, vocabulary)).toBe('pending')
  const original = post.mock.calls[0]![0]
  legacy.dispose()
  const c = await playController()
  expect(await c.inspect()).toBe('pending')
  expect(c.canAppend).toBe(false)
  expect(
    await c.submit(
      {
        ...observation,
        resultId: 'batting-result.hit-by-pitch',
        nextBatter: nextBatter(),
      },
      vocabulary,
    ),
  ).toBe('blocked')
  expect(await c.retry()).toBe('pending')
  expect(transport.buildSyncEventRequestBody(post.mock.calls[1]![0])).toEqual(
    transport.buildSyncEventRequestBody(original),
  )
  expect(post.mock.calls[1]![0].syncCredentials?.attempt).toBe(
    original.syncCredentials?.attempt,
  )
})

import type { PlayPrefixV7 } from '../api/terminalPitchWire'
it.each(['batting-result.walk', 'batting-result.hit-by-pitch'] as const)(
  '%s: 未確認終端→次ordinaryのsource全値はserverのeventId起点PAに一致する',
  async (resultId) => {
    vi.spyOn(transport, 'postSyncEvents').mockResolvedValue({
      sent: false,
      reason: 'no-response',
    })
    const c = await playController()
    const walk = resultId === 'batting-result.walk'
    if (walk)
      for (let i = 0; i < 3; i++)
        expect(await c.submit(observation, vocabulary)).toBe('pending')
    const d5 = '99999999-9999-4999-8999-000000000001',
      eventId = '99999999-9999-4999-8999-000000000002',
      playId = '99999999-9999-4999-8999-000000000003',
      checkpointId = '99999999-9999-4999-8999-000000000004'
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce(d5)
      .mockReturnValueOnce(eventId)
      .mockReturnValueOnce(playId)
      .mockReturnValueOnce(checkpointId)
    expect(eventId).not.toBe(playId)
    expect(
      await c.submit(
        { ...observation, resultId, nextBatter: nextBatter() },
        vocabulary,
      ),
    ).toBe('pending')
    expect(await c.submit(observation, vocabulary)).toBe('pending')
    const terminalD1 = walk ? 4 : 1
    const queue = await openDurableQueue({
      databaseName: 'pitchlog-first-ball-queue-' + tenant,
    })
    try {
      const terminal = await queue.readSlot(
        { game: raw.id, d4: raw.current_d4 },
        terminalD1,
      )
      const next = await queue.readSlot(
        { game: raw.id, d4: raw.current_d4 },
        terminalD1 + 1,
      )
      expect(terminal).not.toBeNull()
      expect(next).not.toBeNull()
      const first = terminal!.event.fields.V7 as PlayPrefixV7,
        second = next!.event.fields.V7 as PlayPrefixV7,
        q = first.calculation.request,
        r = first.calculation.response.value
      expect(q.playIdentity).toStrictEqual({ d5, eventId, playId })
      expect(q.nextCheckpoint.id).toBe(checkpointId)
      // server terminal_pitch_projection.pyはPA開始をOperationEvent IDへ束縛する。
      // 全Source比較を保ち、問題fieldだけの部分一致へ落とさない。
      expect(second.calculation.request.source).toStrictEqual({
        kind: 'evaluated-prefix-v2',
        prefixRef: r.nextPrefixRef,
        rules: q.rules,
        after: r.t1.after,
        t2: r.t2,
        historyDepth: String(terminalD1),
        playCount: String(terminalD1),
        lastSource: { d5, eventId, playId },
        position: {
          d1: String(terminalD1 + 1),
          d2: walk ? '4001' : '1001',
          appliedWatermark: String(terminalD1),
        },
        priorArtifactSha256: r.executionArtifactSha256,
        executionArtifactSha256: r.executionArtifactSha256,
        rulesDigest: q.source.rulesDigest,
        layoutDigest: q.source.layoutDigest,
        runners: r.runners,
        participants: r.participants,
        nextBatter: null,
        bridge: null,
        responsibility: {
          kind: 'no-change',
          paStartSource: { kind: 'confirmed-play', id: eventId },
          previousPitcherId: null,
          strikesAtChange: null,
          ballsAtChange: null,
        },
      })
    } finally {
      queue.close()
    }
  },
)

import lineupFixture from '../api/fixtures/lineupPrefixGame.v3.json'
import {
  lineupContextFromRead,
  isLineupRecordingContext,
} from './GameScreenOrdinaryPitchProvider'
import { isLineupPrefixGame } from '../api/lineupPrefixGame'
async function lineupController() {
  const raw = structuredClone(lineupFixture.value)
  if (!isLineupPrefixGame(raw)) throw new Error('独立DTO不正')
  const c = new GameScreenOrdinaryPitchController(
    await lineupContextFromRead(raw, tenant),
    () => identity,
    writer,
  )
  controllers.push(c)
  return c
}
async function localLineupController() {
  const raw = structuredClone(lineupFixture.value)
  if (!isLineupPrefixGame(raw)) throw new Error('独立DTO不正')
  identity = { tenantId: tenant, epoch: 1, verified: false }
  const boundary = {
    withinAcceptance: async <T>(
      held: { gameIdentifier: string; lockName: string; lock: unknown },
      operation: () => Promise<T>,
    ): Promise<T> => {
      expect(held.gameIdentifier).toBe(raw.id)
      expect(held.lockName).toContain(raw.id)
      return operation()
    },
  }
  const c = new GameScreenOrdinaryPitchController(
    await lineupContextFromRead(raw, tenant),
    () => identity,
    writer,
    boundary,
  )
  controllers.push(c)
  return c
}
it('断中の通常球は本文全体/attemptを先に固定してE0へ追記し、HTTPを呼ばない', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockRejectedValue(new Error('HTTP禁止'))
  const c = await localLineupController()
  const pitch = {
    ...observation,
    resultId: 'batting-result.called-pitch' as const,
  }
  expect(await c.localEnqueue(pitch, vocabulary)).toBe('queued-local')
  expect(
    await c.localEnqueue(
      { ...pitch, resultId: 'batting-result.ball' },
      vocabulary,
    ),
  ).toBe('queued-local')
  expect(post).not.toHaveBeenCalled()
  expect(await slots()).toBe(2)
  expect(c.context.source).toBe('local-provisional')
  const envelopeStore = await OrdinaryPreparedEnvelopePersistence.open()
  const attemptStore = await OrdinaryPitchAttemptPersistence.open()
  let savedEnvelope: PreparedEnvelope | null = null
  let savedAttemptId: string | null = null
  try {
    const envelope = await envelopeStore.read({
      tenantId: tenant,
      gameId: lineupFixture.value.id,
      d4: lineupFixture.value.current_d4,
      d1: 1,
    })
    expect(envelope).not.toBeNull()
    savedEnvelope = envelope
    expect(envelope!.requestBody.recording_right_proof).toBe('unit-only-proof')
    expect(envelope!.requestBody.events).toHaveLength(1)
    const attempt = await attemptStore.read({
      tenantId: tenant,
      gameId: lineupFixture.value.id,
      d4: lineupFixture.value.current_d4,
      d1: 1,
      d5: envelope!.d5,
    })
    expect(attempt?.attemptId).toBe(envelope!.attemptId)
    savedAttemptId = attempt?.attemptId ?? null
    expect(JSON.parse(attempt!.requestJson)).toEqual(
      envelope!.requestBody.events,
    )
  } finally {
    envelopeStore.close()
    attemptStore.close()
  }
  c.dispose()
  const reloaded = await localLineupController()
  expect(await reloaded.inspectLocal()).toBe('pending')
  expect(reloaded.context.prefixRef.length).toBe('2')
  expect(reloaded.context.source).toBe('local-provisional')
  expect(post).not.toHaveBeenCalled()
  reloaded.dispose()
  identity = { tenantId: tenant, epoch: 1, verified: true }
  const online = await lineupController()
  expect(await online.inspect()).toBe('pending')
  post.mockRestore()
  const sent = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  expect(await online.retry()).toBe('pending')
  expect(sent).toHaveBeenCalledOnce()
  expect(sent.mock.calls[0]![0].syncCredentials?.attempt).toBe(savedAttemptId)
  expect(transport.buildSyncEventRequestBody(sent.mock.calls[0]![0])).toEqual(
    savedEnvelope!.requestBody,
  )
})
it('準備済orphanから元ID/本文で再開し、新しいD5を作らない', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockRejectedValue(new Error('HTTP禁止'))
  const c = await localLineupController()
  const pitch = {
    ...observation,
    resultId: 'batting-result.called-pitch' as const,
  }
  const prepare = vi.spyOn(OrdinaryPitchAttemptPersistence.prototype, 'prepare')
  prepare.mockRejectedValueOnce(new Error('attemptを一時停止'))
  expect(await c.localEnqueue(pitch, vocabulary)).toBe('blocked')
  expect(await slots()).toBe(0)
  const store = await OrdinaryPreparedEnvelopePersistence.open()
  const first = await store.read({
    tenantId: tenant,
    gameId: lineupFixture.value.id,
    d4: lineupFixture.value.current_d4,
    d1: 1,
  })
  store.close()
  expect(first).not.toBeNull()
  c.dispose()
  const resumed = await localLineupController()
  const uuid = vi.spyOn(crypto, 'randomUUID')
  expect(await resumed.localEnqueue(pitch, vocabulary)).toBe('queued-local')
  expect(uuid).not.toHaveBeenCalled()
  expect(post).not.toHaveBeenCalled()
  const attemptStore = await OrdinaryPitchAttemptPersistence.open()
  try {
    const attempt = await attemptStore.read({
      tenantId: tenant,
      gameId: lineupFixture.value.id,
      d4: lineupFixture.value.current_d4,
      d1: 1,
      d5: first!.d5,
    })
    expect(attempt?.attemptId).toBe(first!.attemptId)
    expect(JSON.parse(attempt!.requestJson)).toEqual(first!.requestBody.events)
  } finally {
    attemptStore.close()
  }
})
it('準備済orphanのV12が変われば原文を置換せず追記を拒む', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockRejectedValue(new Error('HTTP禁止'))
  const c = await localLineupController()
  const pitch = {
    ...observation,
    resultId: 'batting-result.called-pitch' as const,
  }
  vi.spyOn(
    OrdinaryPitchAttemptPersistence.prototype,
    'prepare',
  ).mockRejectedValueOnce(new Error('attemptを一時停止'))
  expect(await c.localEnqueue(pitch, vocabulary)).toBe('blocked')
  c.dispose()
  vi.mocked(GameStartPersistence.open).mockResolvedValue({
    readDevice: async () => ({
      tenant_id: tenant,
      device_id: tenant,
      device_credential: 'unit-only-credential',
    }),
    readStart: async () => ({
      status: 'received',
      grant: {
        device_id: tenant,
        d4: lineupFixture.value.current_d4,
        away_lineup_id: lineupFixture.value.lineups.away.lineup_id,
        home_lineup_id: lineupFixture.value.lineups.home.lineup_id,
        recording_right_proof: 'changed-proof',
        recovery_generation: lineupFixture.value.recovery_generation,
      },
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
  const resumed = await localLineupController()
  const uuid = vi.spyOn(crypto, 'randomUUID')
  expect(await resumed.localEnqueue(pitch, vocabulary)).toBe('blocked')
  expect(uuid).not.toHaveBeenCalled()
  expect(post).not.toHaveBeenCalled()
  expect(await slots()).toBe(0)
})
it('local受理後にV12が変わればonline retryを送出前に拒む', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockRejectedValue(new Error('HTTP禁止'))
  const local = await localLineupController()
  expect(await local.localEnqueue(observation, vocabulary)).toBe('queued-local')
  local.dispose()
  vi.mocked(GameStartPersistence.open).mockResolvedValue({
    readDevice: async () => ({
      tenant_id: tenant,
      device_id: tenant,
      device_credential: 'unit-only-credential',
    }),
    readStart: async () => ({
      status: 'received',
      grant: {
        device_id: tenant,
        d4: lineupFixture.value.current_d4,
        away_lineup_id: lineupFixture.value.lineups.away.lineup_id,
        home_lineup_id: lineupFixture.value.lineups.home.lineup_id,
        recording_right_proof: 'changed-proof',
        recovery_generation: lineupFixture.value.recovery_generation,
      },
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
  identity = { tenantId: tenant, epoch: 1, verified: true }
  const online = await lineupController()
  expect(await online.inspect()).toBe('pending')
  expect(await online.retry()).toBe('blocked')
  expect(online.retryEvidenceUnavailable).toBe(true)
  expect(post).not.toHaveBeenCalled()
  expect(await slots()).toBe(1)
})
it('local envelopeだけ選択的に欠損しても旧online行へ読み替えずHTTP0で止める', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockRejectedValue(new Error('HTTP禁止'))
  const local = await localLineupController()
  expect(await local.localEnqueue(observation, vocabulary)).toBe('queued-local')
  local.dispose()
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase(
      'pitchlog-ordinary-prepared-envelope-v1',
    )
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
    request.onblocked = () =>
      reject(new Error('envelopeのhandleが残っています'))
  })
  identity = { tenantId: tenant, epoch: 1, verified: true }
  const online = await lineupController()
  expect(await online.inspect()).toBe('pending')
  expect(await online.retry()).toBe('blocked')
  expect(online.retryEvidenceUnavailable).toBe(true)
  expect(post).not.toHaveBeenCalled()
  expect(await slots()).toBe(1)
})
it('local envelope本文以外の元観測改変もdigest不一致でHTTP0に止める', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockRejectedValue(new Error('HTTP禁止'))
  const local = await localLineupController()
  expect(await local.localEnqueue(observation, vocabulary)).toBe('queued-local')
  local.dispose()
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('pitchlog-ordinary-prepared-envelope-v1')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction('prepared', 'readwrite')
      const store = tx.objectStore('prepared')
      tx.oncomplete = () => resolve()
      tx.onabort = () => reject(tx.error)
      const request = store.get([
        tenant,
        lineupFixture.value.id,
        lineupFixture.value.current_d4,
        1,
      ])
      request.onsuccess = () => {
        const row = request.result as { observation: { screenX: number } }
        row.observation.screenX += 1
        store.put(row)
      }
    })
  } finally {
    db.close()
  }
  identity = { tenantId: tenant, epoch: 1, verified: true }
  const online = await lineupController()
  expect(await online.inspect()).toBe('pending')
  expect(await online.retry()).toBe('blocked')
  expect(post).not.toHaveBeenCalled()
})
it('local attemptのorigin metadataが消えた行を旧onlineとして送らない', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockRejectedValue(new Error('HTTP禁止'))
  const local = await localLineupController()
  expect(await local.localEnqueue(observation, vocabulary)).toBe('queued-local')
  local.dispose()
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('pitchlog-ordinary-pitch-attempt')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction('attempts', 'readwrite')
      const store = tx.objectStore('attempts')
      tx.oncomplete = () => resolve()
      tx.onabort = () => reject(tx.error)
      const request = store.getAll()
      request.onsuccess = () => {
        const rows = request.result as { localOrigin?: unknown }[]
        expect(rows).toHaveLength(1)
        delete rows[0]!.localOrigin
        store.put(rows[0]!)
      }
    })
  } finally {
    db.close()
  }
  identity = { tenantId: tenant, epoch: 1, verified: true }
  const online = await lineupController()
  expect(await online.inspect()).toBe('pending')
  expect(await online.retry()).toBe('blocked')
  expect(post).not.toHaveBeenCalled()
})
it('既E0のattemptが欠けたらlocal次球を追記しない', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockRejectedValue(new Error('HTTP禁止'))
  const local = await localLineupController()
  expect(await local.localEnqueue(observation, vocabulary)).toBe('queued-local')
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('pitchlog-ordinary-pitch-attempt')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction('attempts', 'readwrite')
      tx.oncomplete = () => resolve()
      tx.onabort = () => reject(tx.error)
      tx.objectStore('attempts').clear()
    })
  } finally {
    db.close()
  }
  expect(await local.localEnqueue(observation, vocabulary)).toBe('blocked')
  expect(local.canAppendLocal).toBe(false)
  expect(await slots()).toBe(1)
  expect(post).not.toHaveBeenCalled()
})
it('local入力前にidentity epochが変われば準備/queue/HTTPを始めない', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockRejectedValue(new Error('HTTP禁止'))
  const c = await localLineupController()
  identity = { tenantId: tenant, epoch: 2, verified: false }
  expect(await c.inspectLocal()).toBe('blocked')
  expect(await c.localEnqueue(observation, vocabulary)).toBe('blocked')
  expect(post).not.toHaveBeenCalled()
  expect(await slots()).toBe(0)
  const store = await OrdinaryPreparedEnvelopePersistence.open()
  try {
    expect(
      await store.read({
        tenantId: tenant,
        gameId: lineupFixture.value.id,
        d4: lineupFixture.value.current_d4,
        d1: 1,
      }),
    ).toBeNull()
  } finally {
    store.close()
  }
})
it('同じ耐久経路で三振3PA→反対側球を唯一artifactから進める', async () => {
  const post = accepted(),
    c = await lineupController()
  expect(await c.inspect()).toBe('ready')
  for (const resultId of [
    'batting-result.called-pitch',
    'batting-result.called-pitch',
    'batting-result.called-strikeout',
    'batting-result.called-pitch',
    'batting-result.called-pitch',
    'batting-result.called-strikeout',
    'batting-result.called-pitch',
    'batting-result.called-pitch',
    'batting-result.called-strikeout',
    'batting-result.ball',
  ] as const)
    expect(await c.submit({ ...observation, resultId }, vocabulary)).toBe(
      'saved',
    )
  const now = c.context
  if (!isLineupRecordingContext(now)) throw new Error('記録variant消失')
  expect(now.after.stateFields['state.half']).toBe('bottom')
  expect(now.after.stateFields['state.outs']).toBe('0')
  expect(now.after.stateFields['state.count.balls']).toBe('1')
  expect(now.after.battingOrderBySide).toEqual({ away: '4', home: '1' })
  expect(now.lineupSource.participants).toEqual({
    batterId: lineupFixture.value.lineup.home.battingOrder['1'],
    pitcherId: lineupFixture.value.lineup.away.pitcherId,
    catcherId: lineupFixture.value.lineup.away.catcherId,
    battingOrder: '1',
  })
  expect(post).toHaveBeenCalledTimes(10)
  expect(await slots()).toBe(10)
})
it('ACK喪失・再起動でも元v3body/D5/attemptを変えず再送する', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const c = await lineupController()
  expect(await c.inspect()).toBe('ready')
  expect(
    await c.submit(
      { ...observation, resultId: 'batting-result.called-pitch' },
      vocabulary,
    ),
  ).toBe('pending')
  const first = post.mock.calls[0]![0],
    body = transport.buildSyncEventRequestBody(first)
  c.dispose()
  const restarted = await lineupController()
  expect(await restarted.inspect()).toBe('pending')
  expect(await restarted.retry()).toBe('pending')
  const repeated = post.mock.calls[1]![0]
  expect(transport.buildSyncEventRequestBody(repeated)).toEqual(body)
  expect(repeated.syncCredentials?.attempt).toBe(first.syncCredentials?.attempt)
  expect(repeated.slots[0]!.d5).toBe(first.slots[0]!.d5)
  expect(restarted.context.prefixRef.length).toBe('1')
  post.mockRestore()
  accepted('重複')
  expect(await restarted.retry()).toBe('saved')
  expect(await slots()).toBe(1)
})
it('新読取もauth epoch変更後の保存を許さない', async () => {
  const post = accepted(),
    c = await lineupController()
  expect(await c.inspect()).toBe('ready')
  identity = { ...identity, epoch: 2 }
  expect(await c.submit(observation, vocabulary)).toBe('blocked')
  expect(post).not.toHaveBeenCalled()
  expect(await slots()).toBe(0)
})

it.each(['single', 'double', 'triple', 'home-run'] as const)(
  '%sの未確認12観測を耐久保存し、再起動後に元D5/body/attemptを保って再送する',
  async (result) => {
    const post = vi
      .spyOn(transport, 'postSyncEvents')
      .mockResolvedValue({ sent: false, reason: 'no-response' })
    const c = await lineupController()
    expect(await c.inspect()).toBe('ready')
    const resultId = `batting-result.${result}` as const
    const battedHit = {
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
    expect(
      await c.submit({ ...observation, resultId, battedHit }, vocabulary),
    ).toBe('pending')
    const original = post.mock.calls[0]![0]
    expect(
      (original.slots[0]!.event.fields.V7 as LineupPlayPrefixV7).observations,
    ).toEqual({
      ...battedHit,
      pitchTypeKey: observation.pitchTypeKey,
      course: { unit: '1/263', x: '132', y: '139' },
      pitchSpeed: observation.pitchSpeed,
      stance: null,
      battingSide: null,
    })
    c.dispose()
    const restarted = await lineupController()
    expect(await restarted.inspect()).toBe('pending')
    expect(await restarted.retry()).toBe('pending')
    const resent = post.mock.calls[1]![0]
    expect(transport.buildSyncEventRequestBody(resent)).toStrictEqual(
      transport.buildSyncEventRequestBody(original),
    )
    expect(resent.syncCredentials?.attempt).toBe(
      original.syncCredentials?.attempt,
    )
  },
)

it.each(['nonplay-prefix-calculation-v1', 'unknown-inner-v1'])(
  '%sを旧v3slotへ混入してもpublic inspectは数学/UUID/新要求を発行しない',
  async (inner) => {
    const post = vi
      .spyOn(transport, 'postSyncEvents')
      .mockResolvedValue({ sent: false, reason: 'no-response' })
    const original = await lineupController()
    expect(await original.submit(observation, vocabulary)).toBe('pending')
    const first = post.mock.calls[0]![0]
    original.dispose()
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('pitchlog-first-ball-queue-' + tenant)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    try {
      await new Promise<void>((resolve, reject) => {
        const tx = database.transaction('queue', 'readwrite'),
          store = tx.objectStore('queue')
        tx.oncomplete = () => resolve()
        tx.onabort = () => reject(tx.error)
        tx.onerror = () => reject(tx.error)
        const request = store.getAll()
        request.onsuccess = () => {
          const records = request.result as unknown[]
          expect(records).toHaveLength(1)
          const record = records[0]
          if (!record || typeof record !== 'object' || !('event' in record))
            throw new Error('試験slot不正')
          const event = record.event
          if (!event || typeof event !== 'object' || !('fields' in event))
            throw new Error('試験event不正')
          const fields = event.fields
          if (!fields || typeof fields !== 'object' || !('V7' in fields))
            throw new Error('試験fields不正')
          const payload = fields.V7
          if (
            !payload ||
            typeof payload !== 'object' ||
            !('calculation' in payload)
          )
            throw new Error('試験payload不正')
          if (!payload.calculation || typeof payload.calculation !== 'object')
            throw new Error('試験calculation不正')
          Object.defineProperty(payload.calculation, 'formatVersion', {
            value: inner,
            enumerable: true,
            writable: true,
          })
          store.put(record)
        }
        request.onerror = () => reject(request.error)
      })
    } finally {
      database.close()
    }
    const restarted = await lineupController()
    const math = vi.spyOn(domainWrapper, 'invokeFirstBallDomain')
    const uuid = vi.spyOn(crypto, 'randomUUID')
    expect(await restarted.inspect()).toBe('pending')
    expect(restarted.canAppend).toBe(false)
    expect(math).not.toHaveBeenCalled()
    expect(uuid).not.toHaveBeenCalled()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0]![0]).toBe(first)
    expect(await slots()).toBe(1)
  },
)

it('0件の真正v3 seedから初球送信失敗後も2球目を耐久appendし原要求だけを再送する', async () => {
  const seed = structuredClone(lineupFixture.value)
  if (
    !isLineupPrefixGame(seed) ||
    seed.prefix_ref.length !== '0' ||
    seed.next_position.d1 !== '1'
  )
    throw new Error('0件の読取seedではありません')
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const c = await lineupController()
  expect(await c.inspect()).toBe('ready')
  const pitch = {
    ...observation,
    resultId: 'batting-result.called-pitch' as const,
  }
  expect(await c.submit(pitch, vocabulary)).toBe('pending')
  const first = post.mock.calls[0]![0]
  const original = transport.buildSyncEventRequestBody(first)
  expect(await c.submit(pitch, vocabulary)).toBe('pending')
  expect(post).toHaveBeenCalledOnce()
  expect(await slots()).toBe(2)
  expect(c.context.source).toBe('local-provisional')
  expect(c.context.prefixRef.length).toBe('2')
  expect(c.context.nextPosition.d1).toBe('3')
  c.dispose()
  const restored = await lineupController()
  expect(await restored.inspect()).toBe('pending')
  expect(restored.context.prefixRef.length).toBe('2')
  expect(await restored.retry()).toBe('pending')
  expect(transport.buildSyncEventRequestBody(post.mock.calls[1]![0])).toEqual(
    original,
  )
  expect(post.mock.calls[1]![0].syncCredentials?.attempt).toBe(
    first.syncCredentials?.attempt,
  )
  expect(post.mock.calls[1]![0].slots[0]!.d5).toBe(first.slots[0]!.d5)
})

it('照会は保存要求を送らず、旧attemptの終結後だけ同じ本文を次attemptで再送する', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const c = controller()
  expect(await c.inspect()).toBe('ready')
  expect(await c.submit(observation, vocabulary)).toBe('pending')
  const first = post.mock.calls[0]![0]
  const body = transport.buildSyncEventRequestBody(first)
  if (!('events' in body)) throw new Error('単一要求不正')
  const origin = first.syncCredentials!.attempt
  const barrier = await SyncAttemptBarrier.open()
  let advanced: string
  try {
    const prepared = await barrier.prepare(tenant, raw.id, body, tenant, origin)
    expect(prepared.created).toBe(true)
  } finally {
    barrier.close()
  }
  const recover = vi
    .spyOn(recovery, 'recoverSyncAttempt')
    .mockResolvedValue('retry_allowed')
  // 照会だけでは保存POSTを増やさない。
  expect(await c.inspectAttempt()).toBe('retry_allowed')
  expect(post).toHaveBeenCalledOnce()
  expect(recover).toHaveBeenCalledOnce()
  expect(recover.mock.calls[0]![2].attempt).toBe(origin)
  const afterInspect = await SyncAttemptBarrier.open()
  try {
    const prepared = await afterInspect.prepare(
      tenant,
      raw.id,
      body,
      tenant,
      origin,
    )
    advanced = prepared.barrier.currentAttemptId
    expect(advanced).not.toBe(origin)
  } finally {
    afterInspect.close()
  }
  const acceptedPost = accepted()
  acceptedPost.mockClear()
  expect(await c.retry()).toBe('saved')
  expect(acceptedPost).toHaveBeenCalledOnce()
  const retried = acceptedPost.mock.calls[0]![0]
  expect(acceptedPost.mock.calls[0]![1]).toMatchObject({ skipRecovery: true })
  expect(transport.buildSyncEventRequestBody(retried)).toEqual(body)
  expect(retried.slots[0]!.d5).toBe(first.slots[0]!.d5)
})

it('照会unresolvedでは再送せず、結果確認中を維持する', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const c = controller()
  expect(await c.inspect()).toBe('ready')
  expect(await c.submit(observation, vocabulary)).toBe('pending')
  const first = post.mock.calls[0]![0]
  const body = transport.buildSyncEventRequestBody(first)
  if (!('events' in body)) throw new Error('単一要求不正')
  const origin = first.syncCredentials!.attempt
  const barrier = await SyncAttemptBarrier.open()
  try {
    await barrier.prepare(tenant, raw.id, body, tenant, origin)
  } finally {
    barrier.close()
  }
  vi.spyOn(recovery, 'recoverSyncAttempt').mockResolvedValue('unresolved')
  expect(await c.inspectAttempt()).toBe('unresolved')
  expect(post).toHaveBeenCalledOnce()
  expect(await c.retry()).toBe('pending')
  expect(post).toHaveBeenCalledOnce()
  const after = await SyncAttemptBarrier.open()
  try {
    const prepared = await after.prepare(tenant, raw.id, body, tenant, origin)
    expect(prepared.barrier.currentAttemptId).toBe(origin)
  } finally {
    after.close()
  }
})

it('未送信バリアが無いpendingは照会でretry_allowedとし、保存POSTを送らない', async () => {
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockResolvedValue({ sent: false, reason: 'no-response' })
  const c = controller()
  expect(await c.inspect()).toBe('ready')
  expect(await c.submit(observation, vocabulary)).toBe('pending')
  expect(post).toHaveBeenCalledOnce()
  expect(await c.inspectAttempt()).toBe('retry_allowed')
  expect(post).toHaveBeenCalledOnce()
})
