/** transportと開始vaultだけを明示doubleにし、実IDB/queue/attempt/artifactを通す。 */
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { IDBFactory, IDBKeyRange, IDBObjectStore } from 'fake-indexeddb'
import {
  undoRead,
  undoObservation,
  installUndoArtifact,
} from './GameScreenUndoProduct.test-support'
import * as acceptance from './GameScreenPitchAcceptance'
import { completeUndoSource } from '../api/nativeUndoGame'
import * as reads from '../api/nativeUndoGame'
import * as transport from '../api/nativeUndoWire'
import * as ordinary from '../api/client.syncEvents'
import { GameScreenUndoProductController } from './GameScreenUndoProductController'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import {
  openDurableQueue,
  type DurableQueueSlot,
} from '../lib/sync/durableQueue'
import { applyAckToSlot } from './GameScreenAckApplication'
import { readOrdinaryPitchAck } from '../api/ordinaryPitchAck'
import type { FirstBallIdentity } from './GameScreenFirstBallController'
import type { SingleWriterInjections } from '../lib/sync/singleWriter'
import { NativeEnvelopePersistence } from '../api/nativeUndoWire'
let grantProof = 'unit-only-proof'
let restore: () => void,
  identity: FirstBallIdentity,
  server = 2
let controllers: GameScreenUndoProductController[] = []
const initial = undoRead(2),
  tenant = initial.checkpoint.content.scope.tenantId,
  scope = { game: initial.id, d4: initial.current_d4 }
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
function ack(
  s: Readonly<{ d1: number; d4: unknown; d5: unknown }>,
  result = '受理',
) {
  return {
    advancedD3: s.d1,
    eventResults: [{ d1: s.d1, d4: s.d4, d5: s.d5, a5Result: result }],
  }
}
async function queue() {
  return openDurableQueue({
    databaseName: 'pitchlog-first-ball-queue-' + tenant,
  })
}
async function count() {
  const q = await queue()
  try {
    return await q.countSlots()
  } finally {
    q.close()
  }
}
function controller() {
  const c = new GameScreenUndoProductController(
    initial.id,
    () => identity,
    writer,
  )
  controllers.push(c)
  return c
}
beforeEach(async () => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('IDBKeyRange', IDBKeyRange)
  vi.stubGlobal('isSecureContext', true)
  restore = installUndoArtifact()
  server = 2
  grantProof = 'unit-only-proof'
  identity = { tenantId: tenant, epoch: 1, verified: true }
  // 実認証やDB成功の代替でない、端末vaultとHTTPだけの試験double。
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
        d4: initial.current_d4,
        recovery_generation: '1',
        away_lineup_id: initial.lineups.away.lineup_id,
        home_lineup_id: initial.lineups.home.lineup_id,
        recording_right_proof: grantProof,
      },
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
  vi.spyOn(reads, 'readCompleteUndoGame').mockImplementation(async () => {
    const game = undoRead(server)
    return {
      game,
      source: await completeUndoSource(game, tenant),
      storedNative: server !== 2,
    }
  })
  // 既同期済み2slotを実queueへ作る。これはサーバー保存資格のfixtureではない。
  const q = await queue()
  try {
    for (let i = 1; i <= 2; i++) {
      const d5 = `00000000-0000-4000-8000-${String(900 + i).padStart(12, '0')}`,
        s = await q.append(
          q.prepareAppend({
            scope,
            d5,
            version: 1,
            event: {
              fields: {
                V1: d5,
                V3: scope.d4,
                V4: scope.game,
                V5: '1',
                V7: { fixture: 'already-synced' },
              },
            },
          }),
        )
      const a = readOrdinaryPitchAck(ack(s), {
        d4: initial.current_d4,
        d1: s.d1,
        d5,
      })
      expect(
        (await applyAckToSlot({ scope, d1: s.d1, ack: a }, q)).outcome,
      ).toBe('applied')
    }
  } finally {
    q.close()
  }
})
afterEach(() => {
  for (const c of controllers) c.dispose()
  controllers = []
  restore()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('ACK喪失・再起動でも元D5/全body/attemptを保持し、新規操作を飛越さない', async () => {
  const post = vi
    .spyOn(transport, 'postNativeUndo')
    .mockRejectedValue(new Error('ACK lost'))
  await expect(
    reads.readCompleteUndoGame(initial.id, tenant),
  ).resolves.toBeDefined()
  const first = controller()
  const loaded = await first.load()
  expect(first.context).not.toBeNull()
  expect(loaded).toBe('ready')
  expect(await first.undo()).toBe('pending')
  expect(await count()).toBe(3)
  const original = structuredClone(post.mock.calls[0]!)
  first.dispose()
  server = 3
  const second = controller()
  expect(await second.load()).toBe('pending')
  expect(await second.undo()).toBe('pending')
  expect(await count()).toBe(3)
  expect(post).toHaveBeenCalledTimes(1)
  post.mockImplementation(async (_game, body) =>
    ack(
      {
        d1: body.events[0]!.d1,
        d4: body.events[0]!.d4,
        d5: body.events[0]!.d5,
      },
      '重複',
    ),
  )
  expect(await second.retry()).toBe('saved')
  expect(post.mock.calls[1]).toEqual(original)
  expect(await count()).toBe(3)
  expect(second.context?.source.activeStack).toHaveLength(1)
})
it('2取消→空でevent無し→真正CPを再取得してSource6次球を実queueへ積む', async () => {
  vi.spyOn(transport, 'postNativeUndo').mockImplementation(
    async (_game, body) => {
      server = server === 2 ? 3 : 4
      return ack({
        d1: body.events[0]!.d1,
        d4: body.events[0]!.d4,
        d5: body.events[0]!.d5,
      })
    },
  )
  const c = controller()
  expect(await c.load()).toBe('ready')
  expect(await c.undo()).toBe('saved')
  expect(await c.undo()).toBe('saved')
  expect(c.context?.source.activeStack).toHaveLength(0)
  expect(await count()).toBe(4)
  expect(await c.undo()).toBe('empty')
  expect(await count()).toBe(4)
  vi.spyOn(ordinary, 'postSyncEvents').mockImplementation(async (request) => {
    const body = ordinary.buildSyncEventRequestBody(request)
    if (!('events' in body)) throw new Error('invalid wire')
    server = 5
    return { sent: true, requestBody: body, response: ack(request.slots[0]!) }
  })
  expect(await c.ball(undoObservation())).toBe('saved')
  expect(await count()).toBe(5)
  expect(
    c.context?.source.checkpoint.content.restored.current.stateFields[
      'state.count.balls'
    ],
  ).toBe('1')
})
it('初回取消前の派生CPを、通常球の実保存NP CPと偽らない', async () => {
  const post = vi.spyOn(ordinary, 'postSyncEvents')
  const c = controller()
  expect(await c.load()).toBe('ready')
  expect(await c.ball(undoObservation())).toBe('blocked')
  expect(await count()).toBe(2)
  expect(post).not.toHaveBeenCalled()
})
it('tenant/epoch変更後は追記も送信もしない', async () => {
  const post = vi.spyOn(transport, 'postNativeUndo')
  const c = controller()
  expect(await c.load()).toBe('ready')
  identity = { ...identity, epoch: 2 }
  expect(await c.undo()).toBe('blocked')
  expect(await count()).toBe(2)
  expect(post).not.toHaveBeenCalled()
})
it('503を保存成功へせず元slotを残す', async () => {
  vi.spyOn(transport, 'postNativeUndo').mockRejectedValue(new Error('503'))
  const c = controller()
  await c.load()
  expect(await c.undo()).toBe('pending')
  const q = await queue()
  try {
    const slot: DurableQueueSlot | undefined = await q.readSlot(scope, 3)
    expect(slot?.state).toBe('未送信')
  } finally {
    q.close()
  }
})

it('ACKのD5違いを保存完了へ読み替えない', async () => {
  vi.spyOn(transport, 'postNativeUndo').mockImplementation(async (_id, body) =>
    ack({
      d1: body.events[0]!.d1,
      d4: body.events[0]!.d4,
      d5: '00000000-0000-4000-8000-000000000999',
    }),
  )
  const c = controller()
  await c.load()
  expect(await c.undo()).toBe('pending')
  const q = await queue()
  try {
    expect((await q.readSlot(scope, 3))?.state).toBe('未送信')
  } finally {
    q.close()
  }
})
it('サーバー原本が確認できない時は新D5/追記/送信しない', async () => {
  const c = controller()
  await c.load()
  vi.mocked(reads.readCompleteUndoGame).mockRejectedValue(new Error('503'))
  const post = vi.spyOn(transport, 'postNativeUndo')
  expect(await c.undo()).toBe('blocked')
  expect(await count()).toBe(2)
  expect(post).not.toHaveBeenCalled()
})
it('確定済みサーバー原本を閲覧するだけなら端末vault欠落を前倒し条件にしない', async () => {
  vi.mocked(GameStartPersistence.open).mockRejectedValue(
    new Error('no recording vault'),
  )
  const c = controller()
  expect(await c.load()).toBe('blocked')
  expect(c.context?.source.checkpoint).toEqual(undoRead(2).checkpoint)
  expect(await c.undo()).toBe('blocked')
  expect(await count()).toBe(2)
})

it('実IDB envelope addがcommit前に失敗したらqueue受理/D1前進/HTTPは無い', async () => {
  const add = IDBObjectStore.prototype.add
  const broken = vi
    .spyOn(IDBObjectStore.prototype, 'add')
    .mockImplementation(function (this: IDBObjectStore, value, key) {
      if (this.transaction.db.name === 'pitchlog-native-product-envelope')
        throw new DOMException(
          'injected before envelope commit',
          'QuotaExceededError',
        )
      return add.call(this, value, key)
    })
  const post = vi.spyOn(transport, 'postNativeUndo')
  const c = controller()
  expect(await c.load()).toBe('ready')
  expect(await c.undo()).toBe('blocked')
  expect(await count()).toBe(2)
  const q = await queue()
  expect(await q.readNextD1(scope)).toBe(3)
  q.close()
  expect(post).not.toHaveBeenCalled()
  broken.mockRestore()
  c.dispose()
  const recovered = controller()
  expect(await recovered.load()).toBe('ready')
  expect(await recovered.retry()).toBe('ready')
  expect(await count()).toBe(2)
})
it('queue受理後HTTP前の停止はcommit済み元封筒から再起動後に復旧する', async () => {
  const stopped = vi
    .spyOn(NativeEnvelopePersistence.prototype, 'read')
    .mockRejectedValueOnce(new Error('crash after queue accept, before HTTP'))
  const post = vi
    .spyOn(transport, 'postNativeUndo')
    .mockImplementation(async (_game, body) =>
      ack({
        d1: body.events[0]!.d1,
        d4: body.events[0]!.d4,
        d5: body.events[0]!.d5,
      }),
    )
  const c = controller()
  await c.load()
  expect(await c.undo()).toBe('pending')
  expect(await count()).toBe(3)
  expect(post).not.toHaveBeenCalled()
  c.dispose()
  stopped.mockRestore()
  const next = controller()
  expect(await next.load()).toBe('pending')
  expect(await next.retry()).toBe('saved')
  expect(post).toHaveBeenCalledTimes(1)
  expect(await count()).toBe(3)
})
it('ACK喪失後にstart grant V12が変わっても最初の全body/attemptを一字も置換しない', async () => {
  const post = vi
    .spyOn(transport, 'postNativeUndo')
    .mockRejectedValue(new Error('ACK lost'))
  const c = controller()
  await c.load()
  expect(await c.undo()).toBe('pending')
  const original = structuredClone(post.mock.calls[0])
  c.dispose()
  grantProof = 'different-current-grant'
  const next = controller()
  expect(await next.load()).toBe('pending')
  post.mockImplementation(async (_game, body) =>
    ack(
      {
        d1: body.events[0]!.d1,
        d4: body.events[0]!.d4,
        d5: body.events[0]!.d5,
      },
      '重複',
    ),
  )
  expect(await next.retry()).toBe('saved')
  expect(post.mock.calls[1]).toEqual(original)
  expect(post.mock.calls[1]?.[1].recording_right_proof).toBe('unit-only-proof')
})
it('保存済みslotの原封筒欠落をretry prepareや新要求で補わない', async () => {
  const post = vi
    .spyOn(transport, 'postNativeUndo')
    .mockRejectedValue(new Error('ACK lost'))
  const c = controller()
  await c.load()
  expect(await c.undo()).toBe('pending')
  c.dispose()
  vi.spyOn(NativeEnvelopePersistence.prototype, 'read').mockResolvedValue(null)
  const prepare = vi.spyOn(NativeEnvelopePersistence.prototype, 'prepare')
  const next = controller()
  await next.load()
  expect(await next.retry()).toBe('blocked')
  expect(prepare).not.toHaveBeenCalled()
  expect(post).toHaveBeenCalledTimes(1)
  expect(await count()).toBe(3)
})

it.each(['before-return', 'after-return'])(
  '封筒commit済み/queue未受理で停止(%s)しても元封筒だけを回収する',
  async (boundary) => {
    const originalPrepare = NativeEnvelopePersistence.prototype.prepare
    let saved: Awaited<ReturnType<typeof originalPrepare>> | undefined
    const prepare = vi
      .spyOn(NativeEnvelopePersistence.prototype, 'prepare')
      .mockImplementationOnce(async function (
        this: NativeEnvelopePersistence,
        input,
      ) {
        saved = await originalPrepare.call(this, input)
        if (boundary === 'before-return')
          throw new Error('commit succeeded but response lost')
        return saved
      })
    const append =
      boundary === 'after-return'
        ? vi
            .spyOn(acceptance, 'appendPitchEventUnderLock')
            .mockRejectedValueOnce(new Error('stopped before append'))
        : null
    const post = vi
      .spyOn(transport, 'postNativeUndo')
      .mockImplementation(async (_game, body) =>
        ack({
          d1: body.events[0]!.d1,
          d4: body.events[0]!.d4,
          d5: body.events[0]!.d5,
        }),
      )
    const first = controller()
    expect(await first.load()).toBe('ready')
    expect(await first.undo()).toBe('blocked')
    expect(await count()).toBe(2)
    expect(post).not.toHaveBeenCalled()
    expect(saved).toBeDefined()
    first.dispose()
    prepare.mockRestore()
    append?.mockRestore()
    const next = controller()
    expect(await next.load()).toBe('pending')
    expect(await next.undo()).toBe('pending')
    expect(await next.retry()).toBe('saved')
    expect(await count()).toBe(3)
    expect(post.mock.calls[0]?.[1]).toEqual(JSON.parse(saved!.requestJson))
    expect(post.mock.calls[0]?.[2].attempt).toBe(saved!.attemptId)
  },
)
it.each(['source', 'grant', 'read-failure'])(
  '孤児封筒の回収で%sが変わったら原本を置換せず閉じる',
  async (fault) => {
    vi.spyOn(acceptance, 'appendPitchEventUnderLock').mockRejectedValueOnce(
      new Error('before append'),
    )
    const post = vi.spyOn(transport, 'postNativeUndo')
    const first = controller()
    await first.load()
    expect(await first.undo()).toBe('blocked')
    first.dispose()
    if (fault === 'source') server = 3
    if (fault === 'grant') grantProof = 'changed-grant'
    const next = controller()
    expect(await next.load()).toBe('pending')
    if (fault === 'read-failure')
      vi.mocked(reads.readCompleteUndoGame).mockRejectedValue(new Error('503'))
    const prepare = vi.spyOn(NativeEnvelopePersistence.prototype, 'prepare')
    expect(['blocked', 'pending']).toContain(await next.retry())
    expect(await count()).toBe(2)
    expect(post).not.toHaveBeenCalled()
    expect(prepare).not.toHaveBeenCalled()
  },
)
it('通常球も封筒commit後queue前停止から同body/attemptだけを復旧する', async () => {
  server = 3
  const prepareOriginal = NativeEnvelopePersistence.prototype.prepare
  let saved: Awaited<ReturnType<typeof prepareOriginal>> | undefined
  vi.spyOn(NativeEnvelopePersistence.prototype, 'prepare').mockImplementation(
    async function (this: NativeEnvelopePersistence, input) {
      saved = await prepareOriginal.call(this, input)
      return saved
    },
  )
  // fixtureのserver D1=4へ飛ばさず、先行取消slotを実受理/ACKしてから通常球を用意する。
  server = 2
  vi.spyOn(transport, 'postNativeUndo').mockImplementation(
    async (_game, body) => {
      server = 3
      return ack({
        d1: body.events[0]!.d1,
        d4: body.events[0]!.d4,
        d5: body.events[0]!.d5,
      })
    },
  )
  const first = controller()
  await first.load()
  expect(await first.undo()).toBe('saved')
  vi.spyOn(acceptance, 'appendPitchEventUnderLock').mockRejectedValueOnce(
    new Error('before append'),
  )
  const post = vi
    .spyOn(ordinary, 'postSyncEvents')
    .mockImplementation(async (request) => {
      const body = ordinary.buildSyncEventRequestBody(request)
      if (!('events' in body)) throw new Error('invalid wire')
      return { sent: true, requestBody: body, response: ack(request.slots[0]!) }
    })
  expect(await first.ball(undoObservation())).toBe('blocked')
  expect(await count()).toBe(3)
  expect(post).not.toHaveBeenCalled()
  const body = saved!.requestJson,
    attempt = saved!.attemptId
  first.dispose()
  const next = controller()
  expect(await next.load()).toBe('pending')
  expect(await next.retry()).toBe('saved')
  expect(ordinary.buildSyncEventRequestBody(post.mock.calls[0]![0])).toEqual(
    JSON.parse(body),
  )
  expect(post.mock.calls[0]?.[0].syncCredentials?.attempt).toBe(attempt)
  expect(await count()).toBe(4)
})
it('実queue受理後戻り値だけが失われても再起動で同封筒から送れる', async () => {
  const original = acceptance.appendPitchEventUnderLock
  vi.spyOn(acceptance, 'appendPitchEventUnderLock').mockImplementationOnce(
    async (...args) => {
      await original(...args)
      throw new Error('after append committed, before append return')
    },
  )
  const post = vi
    .spyOn(transport, 'postNativeUndo')
    .mockImplementation(async (_game, body) =>
      ack({
        d1: body.events[0]!.d1,
        d4: body.events[0]!.d4,
        d5: body.events[0]!.d5,
      }),
    )
  const first = controller()
  await first.load()
  expect(await first.undo()).toBe('blocked')
  expect(await count()).toBe(3)
  expect(post).not.toHaveBeenCalled()
  first.dispose()
  const next = controller()
  expect(await next.load()).toBe('pending')
  expect(await next.retry()).toBe('saved')
  expect(post).toHaveBeenCalledTimes(1)
})
it('受理戻りslotが準備した全wireと異なればHTTPへ渡さない', async () => {
  const original = acceptance.appendPitchEventUnderLock
  vi.spyOn(acceptance, 'appendPitchEventUnderLock').mockImplementationOnce(
    async (...args) => {
      const result = await original(...args)
      if (result.outcome !== 'accepted') return result
      return { ...result, slot: { ...result.slot, d1: result.slot.d1 + 1 } }
    },
  )
  const post = vi.spyOn(transport, 'postNativeUndo')
  const first = controller()
  await first.load()
  expect(await first.undo()).toBe('pending')
  expect(await count()).toBe(3)
  expect(post).not.toHaveBeenCalled()
})
