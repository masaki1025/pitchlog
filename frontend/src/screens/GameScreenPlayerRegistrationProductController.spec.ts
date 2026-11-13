/** 実 IDB/queue/attempt で断中登録の再起動・写像・順序を保つ。HTTP だけを差し替える。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { IDBFactory, IDBKeyRange } from 'fake-indexeddb'
import * as reads from '../api/substitutionRead'
import * as transport from '../api/playerRegistrationWire'
import {
  playerRegistrationBody,
  playerRegistrationEvent,
  playerRegistrationInput,
} from '../api/playerRegistrationWire'
import { NativeEnvelopePersistence } from '../api/nativeUndoWire'
import { readOrdinaryPitchAck } from '../api/ordinaryPitchAck'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { openDurableQueue, type DurableQueue } from '../lib/sync/durableQueue'
import { queueStateId } from '../lib/sync/queueState'
import { TemporaryPlayerMappingStore } from '../lib/sync/temporaryPlayerMappingStore'
import {
  GameScreenPlayerRegistrationProductController,
  registrationInputFromDraft,
} from './GameScreenPlayerRegistrationProductController'
import { applyAckToSlot } from './GameScreenAckApplication'
import { GameScreenSubstitutionProductController } from './GameScreenSubstitutionProductController'
import { substitutionContextKey } from './GameScreenSubstitutionProductProvider'
import type { RawSubstitutionDraft } from './GameScreenSubstitutionTypes'
import type { PlayerRegistrationDraft } from './GameScreenSubstitutionTypes'
import type { FirstBallIdentity } from './GameScreenFirstBallController'
import type { SingleWriterInjections } from '../lib/sync/singleWriter'

const tenant = '11111111-1111-4111-8111-111111111111'
const game = '22222222-2222-4222-8222-222222222222'
const awayTeam = '33333333-3333-4333-8333-333333333333'
const homeTeam = '44444444-4444-4444-8444-444444444444'
const d4 = 'grant-1'
const scope = { game, d4 }
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
    request: async (_name, callback) => callback({ name: _name }),
  },
}
let identity: FirstBallIdentity
let controllers: GameScreenPlayerRegistrationProductController[] = []
const registrationDraft: PlayerRegistrationDraft = {
  side: 'away',
  answers: {
    name: '断中登録選手',
    throws: 'right',
    bats: 'left',
    uniformNumber: '99',
  },
}

function context() {
  return {
    tenantId: tenant,
    gameId: game,
    generation: d4,
    recoveryGeneration: '1',
    awayLineupId: awayTeam,
    homeLineupId: homeTeam,
    checkpoint: { id: awayTeam, revision: '1', digest: 'a'.repeat(64) },
    nextD1: 1,
    nextD2: 1,
    currentCount: { strikes: '0', balls: '0' },
    state: {
      away: { teamId: awayTeam },
      home: { teamId: homeTeam },
      runners: [],
      exitedPlayerIds: [],
    },
    eligibleBySide: { away: [], home: [] },
    names: {},
    uniformNumbers: {},
  } as never
}

function controller() {
  const current = new GameScreenPlayerRegistrationProductController(
    game,
    () => identity,
    writer,
  )
  controllers.push(current)
  return current
}

async function queue(): Promise<DurableQueue> {
  return openDurableQueue({
    databaseName: 'pitchlog-first-ball-queue-' + tenant,
  })
}

async function appendUnsentSubstitution(q: DurableQueue) {
  const d5 = '55555555-5555-4555-8555-555555555555'
  return q.append(
    q.prepareAppend({
      scope,
      d5,
      version: 1,
      event: {
        fields: {
          V1: d5,
          V3: d4,
          V4: game,
          V5: '3',
          V6: 1,
          V7: { fixture: 'substitution' },
        },
      },
    }),
  )
}

beforeEach(async () => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('IDBKeyRange', IDBKeyRange)
  vi.stubGlobal('isSecureContext', true)
  identity = { tenantId: tenant, epoch: 1, verified: true }
  vi.spyOn(reads, 'readSubstitutionContext').mockImplementation(async () =>
    context(),
  )
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
        d4,
        recovery_generation: '1',
        away_lineup_id: awayTeam,
        home_lineup_id: homeTeam,
        recording_right_proof: 'unit-only-proof',
      },
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
})

afterEach(() => {
  for (const current of controllers) current.dispose()
  controllers = []
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('応答不明でも同じ一時IDの登録を端末に残し、再起動後に写像を確定する', async () => {
  const post = vi.spyOn(transport, 'postPlayerRegistration').mockResolvedValue({
    sent: false,
    reason: 'no-response',
    error: new Error('network'),
  } as never)
  const first = controller()
  expect(await first.load()).toBe('ready')
  expect(await first.register(registrationDraft)).toBe('pending')
  const q = await queue()
  const saved = await q.readSlot(scope, 1)
  expect(saved?.state).toBe(queueStateId('未送信'))
  const temporaryId = (saved?.event.fields.V7 as { temporaryId: string })
    .temporaryId
  expect(
    registrationInputFromDraft(registrationDraft, awayTeam, temporaryId),
  ).not.toBeNull()
  q.close()
  first.dispose()

  const second = controller()
  expect(await second.load()).toBe('pending')
  expect(second.registrations).toMatchObject([
    { temporaryId, state: 'unsent', name: '断中登録選手', side: 'away' },
  ])
  const officialId = '66666666-6666-4666-8666-666666666666'
  post.mockImplementation(async (slot) => ({
    sent: true,
    requestBody: transport.playerRegistrationBody(slot, 'unit-only-proof'),
    response: {
      advancedD3: slot.d1,
      eventResults: [
        { d1: slot.d1, d4: slot.d4, d5: slot.d5, a5Result: '重複' },
      ],
      playerIdMappings: [{ temporaryId, officialId }],
    },
  }))
  expect(await second.retry()).toBe('saved')
  expect(second.registrations).toMatchObject([
    { temporaryId, state: 'confirmed', officialId },
  ])
  const store = await TemporaryPlayerMappingStore.open()
  expect(await store.read(temporaryId)).toMatchObject({ officialId })
  store.close()
  const reopened = await queue()
  expect((await reopened.readSlot(scope, 1))?.state).toBe(
    queueStateId('同期済み'),
  )
  reopened.close()
})

it('写像のない受理 ACK では同期済みへ移さない', async () => {
  vi.spyOn(transport, 'postPlayerRegistration').mockImplementation(
    async (slot) => ({
      sent: true,
      requestBody: transport.playerRegistrationBody(slot, 'unit-only-proof'),
      response: {
        advancedD3: slot.d1,
        eventResults: [
          { d1: slot.d1, d4: slot.d4, d5: slot.d5, a5Result: '受理' },
        ],
      },
    }),
  )
  const current = controller()
  expect(await current.load()).toBe('ready')
  expect(await current.register(registrationDraft)).toBe('pending')
  const q = await queue()
  expect((await q.readSlot(scope, 1))?.state).toBe(queueStateId('未送信'))
  q.close()
})

it('同じ一時IDの再送では写像を重複作成しない', async () => {
  let calls = 0
  vi.spyOn(transport, 'postPlayerRegistration').mockImplementation(
    async (slot, proof) => {
      calls += 1
      const input = slot.event.fields.V7 as { temporaryId: string }
      return {
        sent: true,
        requestBody: transport.playerRegistrationBody(slot, proof),
        response: {
          advancedD3: slot.d1,
          eventResults: [
            { d1: slot.d1, d4: slot.d4, d5: slot.d5, a5Result: '受理' },
          ],
          playerIdMappings: [
            {
              temporaryId: input.temporaryId,
              officialId: '77777777-7777-4777-8777-777777777777',
            },
          ],
        },
      }
    },
  )
  const current = controller()
  expect(await current.load()).toBe('ready')
  expect(await current.register(registrationDraft)).toBe('saved')
  expect(await current.retry()).toBe('ready')
  expect(calls).toBe(1)
  const store = await TemporaryPlayerMappingStore.open()
  const temporaryId = current.registrations[0]!.temporaryId
  const records = await store.readGame(tenant, game)
  expect(
    records.filter((record) => record.temporaryId === temporaryId),
  ).toHaveLength(1)
  store.close()
})

it('古い未送信の交代がある間は登録を追い越して送らない', async () => {
  const q = await queue()
  await appendUnsentSubstitution(q)
  q.close()
  const post = vi.spyOn(transport, 'postPlayerRegistration')
  const current = controller()
  expect(await current.load()).toBe('ready')
  expect(await current.register(registrationDraft)).toBe('pending')
  expect(post).not.toHaveBeenCalled()

  const q2 = await queue()
  const registration = await q2.readSlot(scope, 2)
  expect(registration?.event.fields.V5).toBe('6')
  const substitution = await q2.readSlot(scope, 1)
  const ack = readOrdinaryPitchAck(
    {
      advancedD3: 1,
      eventResults: [{ d1: 1, d4, d5: substitution!.d5, a5Result: '受理' }],
    },
    { d4, d1: 1, d5: String(substitution!.d5) },
  )
  expect((await applyAckToSlot({ scope, d1: 1, ack }, q2)).outcome).toBe(
    'applied',
  )
  q2.close()

  post.mockImplementation(async (slot, proof) => ({
    sent: true,
    requestBody: transport.playerRegistrationBody(slot, proof),
    response: {
      advancedD3: slot.d1,
      eventResults: [
        { d1: slot.d1, d4: slot.d4, d5: slot.d5, a5Result: '受理' },
      ],
      playerIdMappings: [
        {
          temporaryId: (slot.event.fields.V7 as { temporaryId: string })
            .temporaryId,
          officialId: '88888888-8888-4888-8888-888888888888',
        },
      ],
    },
  }))
  expect(await current.retry()).toBe('saved')
  expect(post).toHaveBeenCalledTimes(1)
  expect(post.mock.calls[0]![0].d1).toBe(2)
})

it('未送信の登録がある間は交代の追記を保留する', async () => {
  vi.spyOn(transport, 'postPlayerRegistration').mockResolvedValue({
    sent: false,
    reason: 'no-response',
    error: new Error('network'),
  } as never)
  const registration = controller()
  expect(await registration.load()).toBe('ready')
  expect(await registration.register(registrationDraft)).toBe('pending')

  const substitution = new GameScreenSubstitutionProductController(
    game,
    () => identity,
    writer,
  )
  const c = context() as never
  // 交代の GET 文脈はこの試験では登録の保留判定にだけ使う。
  const draft: RawSubstitutionDraft = {
    identity: {
      contextKey: substitutionContextKey(c),
      uiInstanceId: 'screen-1',
      draftId: 1,
      operation: 'pitcher',
      targetId: awayTeam,
    },
    outgoingId: awayTeam,
    incomingMode: 'existing',
    incomingId: homeTeam,
    answers: { side: 'away', strikes: '0', balls: '0', dh: 'retain' },
  }
  vi.spyOn(reads, 'readSubstitutionContext').mockResolvedValue(c)
  expect(await substitution.load()).toBe('awaiting-registration')
  expect(await substitution.commit(draft)).toBe('awaiting-registration')
  substitution.dispose()
  const q = await queue()
  expect(await q.readSlot(scope, 2)).toBeUndefined()
  q.close()
})

it('恒久的な 4xx 応答では再送を続けずに顕在化する', async () => {
  vi.spyOn(transport, 'postPlayerRegistration').mockResolvedValue({
    sent: false,
    reason: 'response-not-interpreted',
    status: 422,
  } as never)
  const current = controller()
  expect(await current.load()).toBe('ready')
  expect(await current.register(registrationDraft)).toBe('blocked')
  const q = await queue()
  expect((await q.readSlot(scope, 1))?.state).toBe(queueStateId('未送信'))
  q.close()
})

it('キュー追記前の準備済み登録を再起動後に再開する', async () => {
  const temporaryId = '99999999-9999-4999-8999-999999999999'
  const d5 = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const input = playerRegistrationInput({
    temporaryId,
    teamRecordId: awayTeam,
    name: '準備済み選手',
    throws: null,
    bats: null,
    uniformNumber: null,
    rosterStatusKey: 'active',
  })
  const event = playerRegistrationEvent(game, d4, d5, input)
  const attempts = await NativeEnvelopePersistence.open()
  await attempts.prepare({
    tenantId: tenant,
    gameId: game,
    d4,
    d1: 1,
    d5,
    body: playerRegistrationBody(
      {
        game,
        d4,
        d1: 1,
        d5,
        version: 1,
        event,
        state: queueStateId('未送信'),
      },
      'unit-only-proof',
    ),
    event,
  })
  attempts.close()

  const post = vi
    .spyOn(transport, 'postPlayerRegistration')
    .mockImplementation(async (slot, proof) => ({
      sent: true,
      requestBody: transport.playerRegistrationBody(slot, proof),
      response: {
        advancedD3: slot.d1,
        eventResults: [
          { d1: slot.d1, d4: slot.d4, d5: slot.d5, a5Result: '受理' },
        ],
        playerIdMappings: [
          {
            temporaryId,
            officialId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
          },
        ],
      },
    }))
  const current = controller()
  expect(await current.load()).toBe('pending')
  expect(current.registrations).toMatchObject([
    { temporaryId, state: 'unsent', name: '準備済み選手' },
  ])
  expect(await current.retry()).toBe('saved')
  expect(post).toHaveBeenCalledTimes(1)
  const q = await queue()
  expect((await q.readSlot(scope, 1))?.d5).toBe(d5)
  q.close()
})

it('通信断の再起動では保存済み文脈から登録を端末へ積める', async () => {
  const first = controller()
  expect(await first.load()).toBe('ready')
  first.dispose()
  vi.mocked(reads.readSubstitutionContext).mockRejectedValue(
    new Error('offline'),
  )
  vi.spyOn(transport, 'postPlayerRegistration').mockResolvedValue({
    sent: false,
    reason: 'no-response',
    error: new Error('offline'),
  } as never)
  const reopened = controller()
  expect(await reopened.load()).toBe('ready')
  expect(await reopened.register(registrationDraft)).toBe('pending')
  expect(reopened.registrations).toMatchObject([
    { state: 'unsent', name: '断中登録選手', side: 'away' },
  ])
})

it('開始資格と現世代が食い違う文脈では登録しない', async () => {
  vi.mocked(reads.readSubstitutionContext).mockResolvedValue({
    ...(context() as unknown as Record<string, unknown>),
    generation: 'other-generation',
  } as never)
  const current = controller()
  expect(await current.load()).toBe('blocked')
  const q = await queue()
  expect(await q.readSlot(scope, 1)).toBeUndefined()
  q.close()
})
