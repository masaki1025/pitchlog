/** 実IDBと単一書き手でP3原要求を保ち、HTTP応答だけを差し替える。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { IDBFactory, IDBKeyRange } from 'fake-indexeddb'
import fixture from '../api/fixtures/lineupPrefixGame.recorded.v3.json'
import * as currentRead from '../api/lineupPrefixGame'
import * as change from '../api/pastCorrectionProduct'
import * as stats from '../api/stats'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { P3AttemptPersistence } from '../lib/p3AttemptPersistence'
import type { FirstBallIdentity } from './GameScreenFirstBallController'
import type { SingleWriterInjections } from '../lib/sync/singleWriter'
import { GameScreenPastCorrectionProductController } from './GameScreenPastCorrectionProductController'

const original = structuredClone(
  fixture.value,
) as unknown as currentRead.LineupPrefixGame
const tenant = original.prefix_ref.tenantId
const gameId = original.id
const row = original.page.items[0]!.play_row
const offer: change.P3TargetOffer = {
  target_reference: { game: gameId, d4: original.current_d4, d1: 1 },
  expected_version: 1,
  expected_prefix_ref: original.prefix_ref,
  target_event_id: row.source_event_id,
  target_play_id: row.id,
  original_result_id: 'batting-result.called-pitch',
}
const observations = {
  pitchTypeKey: 'pitch-type.straight',
  course: { unit: '1/263' as const, x: '100', y: '150' },
  pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
  stance: null,
  battingSide: null,
}
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
  lockManager: { request: async (name, callback) => callback({ name }) },
}
let identity: FirstBallIdentity
let controllers: GameScreenPastCorrectionProductController[]
let server: typeof fixture.value

function controller() {
  const instance = new GameScreenPastCorrectionProductController(
    gameId,
    () => identity,
    writer,
  )
  controllers.push(instance)
  return instance
}

beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('IDBKeyRange', IDBKeyRange)
  vi.stubGlobal('isSecureContext', true)
  identity = { tenantId: tenant, epoch: 1, verified: true }
  controllers = []
  server = structuredClone(fixture.value)
  vi.spyOn(GameStartPersistence, 'open').mockResolvedValue({
    readDevice: async () => ({
      tenant_id: tenant,
      device_id: tenant,
      device_credential: 'unit-credential',
    }),
    readStart: async () => ({
      status: 'received',
      grant: {
        device_id: tenant,
        d4: original.current_d4,
        recovery_generation: original.recovery_generation,
        recording_right_proof: 'unit-proof',
      },
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
  vi.spyOn(currentRead, 'readLineupPrefixGame').mockImplementation(
    async () => ({
      kind: 'found',
      game: structuredClone(server) as unknown as currentRead.LineupPrefixGame,
    }),
  )
  vi.spyOn(change, 'readP3TargetOffer').mockResolvedValue(offer)
  vi.spyOn(stats, 'fetchGameStats').mockResolvedValue({
    game_id: gameId,
    mode: 'current',
    players: [],
    next_cursor: null,
  })
})

afterEach(() => {
  for (const instance of controllers) instance.dispose()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('結果不明の原要求を送信前に保存し、再起動後も同D5・本文・attemptだけ再送する', async () => {
  const submitted: Parameters<typeof change.postP3Change>[] = []
  const post = vi
    .spyOn(change, 'postP3Change')
    .mockImplementation(async (...args) => {
      submitted.push(structuredClone(args))
      const stored = await P3AttemptPersistence.open()
      try {
        expect(await stored.read(tenant, gameId)).not.toBeNull()
      } finally {
        stored.close()
      }
      throw new Error('応答不明')
    })
  const first = controller()
  expect(await first.inspectPending()).toBe('ready')
  expect(await first.inspect(1)).toEqual(offer)
  expect(await first.commit(offer, 'batting-result.ball', observations)).toBe(
    'pending',
  )
  expect(post).toHaveBeenCalledTimes(1)
  first.dispose()
  const second = controller()
  expect(await second.inspectPending()).toBe('pending')
  expect(await second.commit(offer, 'batting-result.ball', observations)).toBe(
    'pending',
  )
  expect(post).toHaveBeenCalledTimes(1)
  expect(await second.retry()).toBe('pending')
  expect(submitted).toHaveLength(2)
  expect(submitted[1]).toEqual(submitted[0])
})

it('別tenantの現行GETや認証世代変更を対象採用・送信成功へ上げない', async () => {
  const post = vi.spyOn(change, 'postP3Change')
  const instance = controller()
  server.prefix_ref.tenantId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  expect(await instance.inspect(1)).toBeNull()
  expect(
    await instance.commit(offer, 'batting-result.ball', observations),
  ).toBe('blocked')
  server.prefix_ref.tenantId = tenant
  identity = { ...identity, epoch: 2 }
  expect(
    await instance.commit(offer, 'batting-result.ball', observations),
  ).toBe('blocked')
  expect(post).not.toHaveBeenCalled()
})

it('受理I6後の再生成はHTTP再送せず同D5・slot2・現headを再照合する', async () => {
  let acceptedHead: typeof server.prefix_ref | null = null
  const post = vi.spyOn(change, 'postP3Change').mockImplementation(async (body) => {
    server.prefix_ref.checkpoint.id = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
    server.prefix_ref.checkpoint.digest = 'b'.repeat(64)
    server.page.items[0]!.play_row.id =
      'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
    server.page.items[0]!.play_row.source_event_id =
      'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
    server.page.items[0]!.play_row.batting_result_key = 'batting-result.ball'
    acceptedHead = structuredClone(server.prefix_ref)
    return {
      kind: 'accepted',
      targetReference: {
        試合: gameId,
        '対象の D4': original.current_d4,
        '対象の D1': 1,
      },
      expectedVersion: 1,
      d5: body.change.d5,
      confirmedContent: body.change.payload,
      acceptedAt: '2026-11-07T00:00:00+00:00',
    }
  })
  vi.spyOn(change, 'readP3ChangeConfirmation').mockImplementation(
    async (_game, _d1, receivedD5) => ({
      target_reference: offer.target_reference,
      confirmed_version: 2,
      d5: receivedD5,
      source_event_id: server.page.items[0]!.play_row.source_event_id,
      target_play_id: server.page.items[0]!.play_row.id,
      stats_version_id: 'ffffffff-ffff-4fff-8fff-ffffffffffff',
      current_prefix_ref: structuredClone(
        acceptedHead ?? server.prefix_ref,
      ) as currentRead.LineupPrefixGame['prefix_ref'],
      current_after: structuredClone(server.after),
    }),
  )
  const first = controller()
  expect(await first.inspectPending()).toBe('ready')
  expect(await first.inspect(1)).toEqual(offer)
  expect(await first.commit(offer, 'batting-result.ball', observations)).toBe(
    'saved',
  )
  expect(post).toHaveBeenCalledTimes(1)
  first.dispose()
  const reloaded = controller()
  expect(await reloaded.inspectPending()).toBe('saved')
  expect(post).toHaveBeenCalledTimes(1)
  server.prefix_ref.checkpoint.digest = 'c'.repeat(64)
  expect(await reloaded.inspectPending()).toBe('saved-awaiting-read')
  expect(post).toHaveBeenCalledTimes(1)
})
