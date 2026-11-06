// @vitest-environment-options {"url":"https://pitchlog.test"}
//
// この spec は保存呼出順・耐久・ACK 分岐・再取得分岐・断中chainを検査する。
// mock の ACK 成功は実認可/実DB/PG の成功証拠ではない（root の隔離PG実画面で
// 実測するまで未成立）。再開種別は正本の写しに未裁定のため、順序検査に限り
// 構造だけを差し込む（正式裁定後に実在する予定の種別）。
import { IDBFactory, IDBKeyRange } from 'fake-indexeddb'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import {
  GAME_LIFECYCLE_READ_FORMAT,
  isGameLifecycleGame,
  type GameLifecycleGame,
  type GameLifecycleReadResult,
  type GameLifecycleRequestBody,
} from '../api/gameLifecycle'
import * as lifecycle from '../api/gameLifecycle'
import { NativeEnvelopePersistence } from '../api/nativeUndoWire'
import { readCanonBoundaryResults } from '../lib/sync/canonOracle'
import { EVENT_KIND_RULES, type EventKind } from '../lib/sync/eventKinds'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { openDurableQueue } from '../lib/sync/durableQueue'
import type { SingleWriterInjections } from '../lib/sync/singleWriter'
import { applyAckToSlot } from './GameScreenAckApplication'
import GameScreenLifecyclePanel from './GameScreenLifecyclePanel.vue'
import {
  GAME_LIFECYCLE_REASON,
  GameLifecycleController,
  createGameLifecycleWriter,
  type GameLifecycleView,
} from './gameLifecycleController'
import { undoRead } from './GameScreenUndoProduct.test-support'

const fixture = undoRead()
const tenant = fixture.checkpoint.content.scope.tenantId
const gameId = fixture.id
const d4 = fixture.current_d4
const baseD2 = fixture.next_position.d2
const deviceId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

type WirePayload = Readonly<{
  formatVersion: string
  action: 'end' | 'reopen'
  checkpointRef: Record<string, unknown>
  target: Record<string, unknown> | null
  event: Readonly<{ eventId: string; receiptId: string }>
}>

type WireEvent = Readonly<{
  d5: string
  d1: number
  d4: string
  game_id: string
  event_kind: string
  d2: number
  payload: WirePayload
}>

type Server = {
  status: 'in_progress' | 'finished'
  lastVersion: string
  active: { version: string; eventId: string; receiptId: string } | null
  statsId: string | null
}

let server: Server
let serverD3: number
let serverNextD2: number
let applied: Set<string>
let posts: { body: GameLifecycleRequestBody; attempt: string }[]
let readFails: boolean
let forcedRead: GameLifecycleGame | null
let postMode: 'ok' | 'lost-ack' | 'http-409' | 'http-503'
let identity = { tenantId: tenant, epoch: 1, verified: true }
let controllers: GameLifecycleController[] = []

function wireEvent(body: GameLifecycleRequestBody): WireEvent {
  return body.events[0] as unknown as WireEvent
}

function resetServer(): void {
  server = {
    status: 'in_progress',
    lastVersion: '0',
    active: null,
    statsId: null,
  }
  serverD3 = 0
  serverNextD2 = Number(baseD2)
  applied = new Set()
  posts = []
  readFails = false
  forcedRead = null
  postMode = 'ok'
}

/** 実GETのfixture。適用済みD1/D2を反映し、baseのd3とnext_positionを進める。 */
function currentRead(): GameLifecycleGame {
  const value: unknown = {
    ...fixture,
    checkpoint: {
      ...fixture.checkpoint,
      content: {
        ...fixture.checkpoint.content,
        d3: String(serverD3),
        activeDepth: String(serverD3),
        activeHead: null,
      },
    },
    next_position: { d1: String(serverD3 + 1), d2: String(serverNextD2) },
    page: { items: [], next_cursor: null },
    status: server.status,
    lifecycle: {
      formatVersion: GAME_LIFECYCLE_READ_FORMAT,
      status: server.status,
      lastVersion: server.lastVersion,
      active: server.active === null ? null : { ...server.active },
      activeStatsVersionId: server.statsId,
    },
  }
  if (!isGameLifecycleGame(value)) throw new Error('lifecycle fixture invalid')
  return value
}

function ackFor(event: WireEvent, result: string) {
  return {
    advancedD3: event.d1,
    eventResults: [
      { d4: event.d4, d1: event.d1, d5: event.d5, a5Result: result },
    ],
  }
}

function applyBody(body: GameLifecycleRequestBody): string {
  const event = wireEvent(body)
  if (applied.has(event.d5)) return '重複'
  applied.add(event.d5)
  serverD3 = Math.max(serverD3, event.d1)
  serverNextD2 = Math.max(serverNextD2, event.d2 + 1000)
  if (event.event_kind === 'game_end_declaration') {
    const version = (BigInt(server.lastVersion) + 1n).toString()
    server = {
      status: 'finished',
      lastVersion: version,
      active: {
        version,
        eventId: event.payload.event.eventId,
        receiptId: event.payload.event.receiptId,
      },
      statsId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    }
  } else if (event.event_kind === 'game_reopen') {
    server = {
      ...server,
      status: 'in_progress',
      active: null,
      statsId: null,
    }
  } else {
    throw new Error('unknown wire kind')
  }
  return '受理'
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
  lockManager: {
    request: async (_name, operation) => await operation({ name: 'test-lock' }),
  },
}

/**
 * 正本の写しに再開種別が無い間の順序検査だけに使う構造。
 * 製品codeはこれを既知種別と偽装しない。共有queueの遷移表も同じ表を読むため、
 * 「正式裁定patchが入った後」の遷移だけをこの spec 内で再現する。
 */
const pendingReopenKind = {
  id: '13',
  name: '試合再開',
  participation: '論理位置を持つ',
  hasRevisionOrder: false,
  group: 'A',
} as unknown as EventKind

let installedReopenKind = false

function installPendingReopenKind(): void {
  if (installedReopenKind) return
  ;(EVENT_KIND_RULES as unknown as EventKind[]).push(pendingReopenKind)
  installedReopenKind = true
}

function restoreEventKindTable(): void {
  if (!installedReopenKind) return
  const table = EVENT_KIND_RULES as unknown as EventKind[]
  const index = table.findIndex((kind) => kind.id === pendingReopenKind.id)
  if (index >= 0) table.splice(index, 1)
  installedReopenKind = false
}

function controller(
  options: {
    writer?: SingleWriterInjections
    resolveEventKind?: (action: 'end' | 'reopen') => EventKind | undefined
  } = {},
) {
  const value = new GameLifecycleController(gameId, () => identity, {
    writer: options.writer ?? writer,
    resolveEventKind:
      options.resolveEventKind ??
      ((action) =>
        action === 'end'
          ? lifecycle.gameLifecycleEventKind('end')
          : pendingReopenKind),
  })
  controllers.push(value)
  return value
}

async function scopeQueue() {
  return openDurableQueue({
    databaseName: 'pitchlog-first-ball-queue-' + tenant,
  })
}

async function queueSlots() {
  const queue = await scopeQueue()
  try {
    const page = await queue.readSlotsPage({ game: gameId, d4 }, null, 100)
    return page.items
  } finally {
    queue.close()
  }
}

/** 既通常/NP入力の代わりに「同じqueueの球」だけを積む。計算は実装しない。 */
async function appendOrdinaryMarkers(
  count: number,
  firstD2 = Number(baseD2),
): Promise<void> {
  const queue = await scopeQueue()
  try {
    for (let index = 0; index < count; index += 1) {
      const d5 = crypto.randomUUID()
      const prepared = queue.prepareAppend({
        scope: { game: gameId, d4 },
        d5,
        version: 1,
        event: {
          fields: {
            V1: d5,
            V3: d4,
            V4: gameId,
            V5: '1',
            V6: firstD2 + index * 1000,
            V7: { formatVersion: 'unit-order-marker-v1' },
          },
        },
      })
      await queue.append(prepared)
    }
  } finally {
    queue.close()
  }
}

async function markUnsentSynced(
  beforeD1: number = Number.MAX_SAFE_INTEGER,
): Promise<void> {
  const queue = await scopeQueue()
  try {
    const terminal = readCanonBoundaryResults().find(
      (row) => row.name === '要求終端',
    )!.id
    for (let d1 = 1; d1 < beforeD1; d1 += 1) {
      const slot = await queue.readSlot({ game: gameId, d4 }, d1)
      if (!slot) break
      if (slot.state !== '未送信') continue
      const appliedResult = await applyAckToSlot(
        {
          scope: { game: gameId, d4 },
          d1,
          ack: {
            envelope: {
              advancedD3: d1,
              eventResults: [{ d4, d1, d5: slot.d5, a5Result: '重複' }],
            },
            boundaryResult: terminal,
          },
        },
        queue,
      )
      if (appliedResult.outcome !== 'applied')
        throw new Error('marker slot was not synced')
    }
  } finally {
    queue.close()
  }
}

function lifecycleSlots(slots: Awaited<ReturnType<typeof queueSlots>>) {
  return slots.filter(
    (slot) =>
      (slot.event.fields.V7 as { formatVersion?: string } | undefined)
        ?.formatVersion === 'native-game-lifecycle-v1',
  )
}

beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('IDBKeyRange', IDBKeyRange)
  vi.stubGlobal('isSecureContext', true)
  resetServer()
  identity = { tenantId: tenant, epoch: 1, verified: true }
  vi.spyOn(GameStartPersistence, 'open').mockResolvedValue({
    readDevice: async () => ({
      tenant_id: tenant,
      device_id: deviceId,
      device_credential: 'unit-only-credential',
    }),
    readStart: async () => ({
      status: 'received',
      grant: {
        device_id: deviceId,
        d4,
        away_lineup_id: fixture.lineups.away.lineup_id,
        home_lineup_id: fixture.lineups.home.lineup_id,
        recording_right_proof: 'unit-only-proof',
        recovery_generation: fixture.recovery_generation,
      },
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
  vi.spyOn(lifecycle, 'readGameLifecycle').mockImplementation(
    async (): Promise<GameLifecycleReadResult> => {
      if (readFails) throw new Error('read failed')
      return { kind: 'found', game: forcedRead ?? currentRead() }
    },
  )
  vi.spyOn(lifecycle, 'postGameLifecycleRequestBody').mockImplementation(
    async (_id, body, credentials) => {
      posts.push({
        body: structuredClone(body),
        attempt: credentials!.attempt,
      })
      if (postMode === 'http-409')
        return { sent: false, reason: 'response-not-interpreted', status: 409 }
      if (postMode === 'http-503')
        return { sent: false, reason: 'response-not-interpreted', status: 503 }
      const result = applyBody(body)
      if (postMode === 'lost-ack') return { sent: false, reason: 'no-response' }
      return {
        sent: true,
        requestBody: body,
        response: ackFor(wireEvent(body), result),
      }
    },
  )
})

afterEach(() => {
  restoreEventKindTable()
  controllers.forEach((value) => value.dispose())
  controllers = []
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('実writer接続', () => {
  it('既存環境確認からpreconditions/revalidateを組み立て、偽のtrueを作らない', async () => {
    const environment = {
      topLevelHttps: () => true,
      sameBrowserProfile: () => true,
      sameBrowsingMode: () => true,
      sameStorageBucket: () => true,
      siteStorageAvailable: () => true,
      lockdownModeNotApplied: () => false,
      identityVerified: () => true,
    }
    const built = createGameLifecycleWriter(environment)
    expect(built.resolvePreconditions?.()).toMatchObject({
      topLevelHttps: true,
      lockdownModeNotApplied: false,
    })
    expect(
      built.revalidateSingleWriter?.({
        gameIdentifier: gameId,
        lockName: '',
        lock: {},
      }),
    ).toBe(false)
    const c = controller({
      writer: { ...built, lockManager: writer.lockManager },
    })
    await c.refresh()
    expect(await c.end()).toEqual({
      outcome: 'blocked',
      reason: GAME_LIFECYCLE_REASON.LOCK_UNAVAILABLE,
    })
    expect(await queueSlots()).toHaveLength(0)
  })

  it('すべての実前提が揃えば同じhelperで操作できる', async () => {
    const built = createGameLifecycleWriter({
      topLevelHttps: () => true,
      sameBrowserProfile: () => true,
      sameBrowsingMode: () => true,
      sameStorageBucket: () => true,
      siteStorageAvailable: () => true,
      lockdownModeNotApplied: () => true,
      identityVerified: () => true,
    })
    expect(
      built.revalidateSingleWriter?.({
        gameIdentifier: gameId,
        lockName: '',
        lock: {},
      }),
    ).toBe(true)
    const c = controller({
      writer: { ...built, lockManager: writer.lockManager },
      resolveEventKind: undefined,
    })
    await c.refresh()
    expect((await c.end()).outcome).toBe('acked')
  })
})

describe('オンラインの終了から再終了まで', () => {
  it('終了v1→再開→2球→再終了v2→reloadを、同queue/閉union/実GET復元で接続する', async () => {
    // 再開種別の正式裁定patchが入った後の遷移を、表への一時追加で再現する。
    installPendingReopenKind()
    const c = controller()
    const first = await c.refresh()
    expect(first.status).toBe('in_progress')
    expect(first.confirmedStatus).toBe('in_progress')
    expect(first.canEnd).toBe(true)
    expect(first.canReopen).toBe(false)

    const end1 = await c.end()
    expect(end1).toEqual({ outcome: 'acked', ack: 'accepted', refresh: 'done' })
    let slots = await queueSlots()
    expect(slots).toHaveLength(1)
    expect(slots[0]).toMatchObject({ d1: 1, state: '同期済み' })
    expect(slots[0]!.event.fields.V5).toBe('5')
    expect(posts).toHaveLength(1)
    expect(wireEvent(posts[0]!.body)).toMatchObject({
      d1: 1,
      d4,
      game_id: gameId,
      event_kind: 'game_end_declaration',
      d2: Number(baseD2),
    })
    expect(wireEvent(posts[0]!.body).payload).toMatchObject({
      formatVersion: 'native-game-lifecycle-v1',
      action: 'end',
      checkpointRef: { kind: 'confirmed', id: fixture.checkpoint.ref.id },
      target: null,
    })
    expect(posts[0]!.body.recording_right_proof).toBe('unit-only-proof')
    const view1 = c.view
    expect(view1.status).toBe('finished')
    expect(view1.confirmedStatus).toBe('finished')
    expect(view1.lastVersion).toBe('1')
    expect(view1.active?.version).toBe('1')
    expect(view1.saveAck).toBe('accepted')
    expect(view1.refresh).toBe('done')
    expect(view1.canReopen).toBe(true)

    const target = { ...view1.active! }
    const reopen = await c.reopen()
    expect(reopen).toEqual({
      outcome: 'acked',
      ack: 'accepted',
      refresh: 'done',
    })
    slots = await queueSlots()
    expect(slots).toHaveLength(2)
    expect(slots[1]!.event.fields.V5).toBe('13')
    expect(wireEvent(posts[1]!.body)).toMatchObject({
      d1: 2,
      event_kind: 'game_reopen',
    })
    expect(wireEvent(posts[1]!.body).payload).toMatchObject({
      action: 'reopen',
      checkpointRef: { kind: 'confirmed', id: fixture.checkpoint.ref.id },
      target: { kind: 'confirmed', ...target },
    })
    const view2 = c.view
    expect(view2.status).toBe('in_progress')
    expect(view2.confirmedStatus).toBe('in_progress')
    expect(view2.active).toBeNull()
    expect(view2.lastVersion).toBe('1')

    // 既通常/NP入力controllerが積む2球分。計算はここで実装しない。
    await appendOrdinaryMarkers(2, Number(baseD2) + 1000)
    const deferred = await c.end()
    expect(deferred.outcome).toBe('pending')
    if (deferred.outcome !== 'pending') return
    expect(deferred.reason).toBe(
      GAME_LIFECYCLE_REASON.QUEUED_AWAITING_PREDECESSOR,
    )
    expect(await queueSlots()).toHaveLength(5)
    expect(posts).toHaveLength(2)
    expect(c.view.preparedCount).toBe(1)

    await markUnsentSynced(5)
    const end2 = await c.retry()
    expect(end2).toEqual({ outcome: 'acked', ack: 'accepted', refresh: 'done' })
    expect(posts).toHaveLength(3)
    expect(wireEvent(posts[2]!.body)).toMatchObject({
      d1: 5,
      event_kind: 'game_end_declaration',
    })
    const view3 = c.view
    expect(view3.status).toBe('finished')
    expect(view3.confirmedStatus).toBe('finished')
    expect(view3.lastVersion).toBe('2')
    expect(view3.active?.version).toBe('2')

    // reload: 新しいcontrollerが実GETからだけ復元する。
    const reloaded = controller()
    const restored = await reloaded.refresh()
    expect(restored.status).toBe('finished')
    expect(restored.confirmedStatus).toBe('finished')
    expect(restored.lastVersion).toBe('2')
    expect(restored.active?.version).toBe('2')
    expect(restored.saveAck).toBeNull()
    expect(restored.unknownCount).toBe(0)
  }, 20_000)

  it('再開種別が未裁定なら追記再開を閉拒否する', async () => {
    const c = controller({
      resolveEventKind: (action) =>
        action === 'end' ? lifecycle.gameLifecycleEventKind('end') : undefined,
    })
    await c.refresh()
    expect((await c.end()).outcome).toBe('acked')
    const before = await queueSlots()
    const reopen = await c.reopen()
    expect(reopen).toEqual({
      outcome: 'blocked',
      reason: GAME_LIFECYCLE_REASON.REOPEN_KIND_UNAVAILABLE,
    })
    expect(await queueSlots()).toHaveLength(before.length)
    expect(posts).toHaveLength(1)
    expect(c.view.reopenBlocked).toBe(true)
    expect(c.view.canReopen).toBe(false)
  })

  it('サーバー確定済みの終了は、端末に終了slotが無くてもconfirmed targetで再開できる', async () => {
    installPendingReopenKind()
    server = {
      status: 'finished',
      lastVersion: '1',
      active: {
        version: '1',
        eventId: 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        receiptId: 'bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb',
      },
      statsId: 'cccccccc-1111-4111-8111-cccccccccccc',
    }
    const c = controller()
    const view = await c.refresh()
    expect(view.status).toBe('finished')
    expect(view.canReopen).toBe(true)
    const reopened = await c.reopen()
    expect(reopened).toEqual({
      outcome: 'acked',
      ack: 'accepted',
      refresh: 'done',
    })
    expect(wireEvent(posts[0]!.body).payload).toMatchObject({
      action: 'reopen',
      checkpointRef: { kind: 'confirmed' },
      target: {
        kind: 'confirmed',
        version: '1',
        eventId: 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        receiptId: 'bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb',
      },
    })
    expect(c.view.status).toBe('in_progress')
    expect(c.view.confirmedStatus).toBe('in_progress')
  })

  it('ACK後のGETが古い間はconfirmed_prefix/queued_endで次の再開を表現する', async () => {
    installPendingReopenKind()
    const c = controller()
    await c.refresh()
    const stale = currentRead()
    forcedRead = stale
    const ended = await c.end()
    expect(ended).toEqual({
      outcome: 'acked',
      ack: 'accepted',
      refresh: 'pending',
    })
    const endBody = wireEvent(posts[0]!.body)
    const reopened = await c.reopen()
    expect(reopened).toEqual({
      outcome: 'acked',
      ack: 'accepted',
      refresh: 'pending',
    })
    expect(posts).toHaveLength(2)
    expect(wireEvent(posts[1]!.body).payload).toMatchObject({
      action: 'reopen',
      checkpointRef: {
        kind: 'confirmed_prefix',
        d4,
        d1: '1',
        d5: endBody.d5,
      },
      target: {
        kind: 'queued_end',
        d4,
        d1: '1',
        d5: endBody.d5,
        eventId: endBody.payload.event.eventId,
        receiptId: endBody.payload.event.receiptId,
      },
    })
    expect(reopened.outcome).toBe('acked')
  })
})

describe('通信断中の終了・再開', () => {
  it('実GET不能でも未送信プレイ→終了→再開→再終了を順序どおり耐久保存する', async () => {
    installPendingReopenKind()
    const c = controller()
    await c.refresh()
    const baseD2Value = Number(baseD2)

    // 断中: 既通常入力が2球を未送信で積んだ状態。
    await appendOrdinaryMarkers(2, baseD2Value)
    readFails = true

    const end1 = await c.end()
    expect(end1).toEqual({
      outcome: 'pending',
      reason: GAME_LIFECYCLE_REASON.QUEUED_AWAITING_PREDECESSOR,
    })
    const reopen = await c.reopen()
    expect(reopen).toEqual({
      outcome: 'pending',
      reason: GAME_LIFECYCLE_REASON.QUEUED_AWAITING_PREDECESSOR,
    })
    const end2 = await c.end()
    expect(end2).toEqual({
      outcome: 'pending',
      reason: GAME_LIFECYCLE_REASON.QUEUED_AWAITING_PREDECESSOR,
    })
    expect(posts).toHaveLength(0)
    const slots = await queueSlots()
    expect(slots).toHaveLength(5)
    const chain = lifecycleSlots(slots)
    expect(chain.map((slot) => slot.d1)).toEqual([3, 4, 5])
    expect(chain.map((slot) => slot.event.fields.V6)).toEqual([
      baseD2Value + 2000,
      baseD2Value + 3000,
      baseD2Value + 4000,
    ])

    const end1Body = wireEvent(
      JSON.parse(
        (await (
          await NativeEnvelopePersistence.open()
        ).read({
          tenantId: tenant,
          gameId,
          d4,
          d1: 3,
          d5: String(chain[0]!.d5),
        }))!.requestJson,
      ) as GameLifecycleRequestBody,
    )
    expect(end1Body.payload).toMatchObject({
      action: 'end',
      checkpointRef: {
        kind: 'queued_predecessor',
        d4,
        d1: '2',
        d5: String(slots[1]!.d5),
      },
      target: null,
    })
    const reopenBody = wireEvent(
      JSON.parse(
        (await (
          await NativeEnvelopePersistence.open()
        ).read({
          tenantId: tenant,
          gameId,
          d4,
          d1: 4,
          d5: String(chain[1]!.d5),
        }))!.requestJson,
      ) as GameLifecycleRequestBody,
    )
    expect(reopenBody.payload).toMatchObject({
      action: 'reopen',
      checkpointRef: {
        kind: 'queued_predecessor',
        d1: '3',
        d5: String(chain[0]!.d5),
      },
      target: {
        kind: 'queued_end',
        d1: '3',
        d5: String(chain[0]!.d5),
        eventId: end1Body.payload.event.eventId,
        receiptId: end1Body.payload.event.receiptId,
      },
    })

    const view = c.view
    expect(view.status).toBe('finished')
    expect(view.confirmedStatus).toBe('in_progress')
    expect(view.pendingLifecycleCount).toBe(3)
    expect(view.preparedCount).toBe(3)
    expect(view.canEnd).toBe(false)
    expect(view.canReopen).toBe(true)

    // reload: baseは実GET成功時に耐久保存されている。
    c.dispose()
    const reloaded = controller()
    const restored = await reloaded.refresh()
    expect(restored.status).toBe('finished')
    expect(restored.confirmedStatus).toBe('in_progress')
    expect(restored.pendingLifecycleCount).toBe(3)
    expect(restored.canReopen).toBe(true)

    // 復帰: 先行の通常球が同期された後、lifecycle chainを同本文で順に送る。
    await markUnsentSynced(3)
    readFails = false
    const retried = await reloaded.retry()
    expect(retried).toEqual({
      outcome: 'acked',
      ack: 'accepted',
      refresh: 'done',
    })
    expect(posts).toHaveLength(3)
    expect(posts.map((post) => wireEvent(post.body).d1)).toEqual([3, 4, 5])
    expect(posts.map((post) => wireEvent(post.body).payload.action)).toEqual([
      'end',
      'reopen',
      'end',
    ])
    expect(new Set(posts.map((post) => wireEvent(post.body).d5)).size).toBe(3)
    expect(posts[1]!.body).not.toEqual(posts[0]!.body)
    expect(posts.map((post) => post.attempt)).toEqual([
      posts[0]!.attempt,
      posts[1]!.attempt,
      posts[2]!.attempt,
    ])
    const final = reloaded.view
    expect(final.status).toBe('finished')
    expect(final.confirmedStatus).toBe('finished')
    expect(final.lastVersion).toBe('2')
    expect(final.active?.version).toBe('2')
    expect(final.pendingLifecycleCount).toBe(0)
  }, 20_000)

  it('先行の結果が未確定なら送信を待ち、本文・D5・attemptを変えない', async () => {
    const c = controller()
    await c.refresh()
    await appendOrdinaryMarkers(1)
    const queued = await c.end()
    expect(queued.outcome).toBe('pending')
    if (queued.outcome !== 'pending') return
    expect(queued.reason).toBe(
      GAME_LIFECYCLE_REASON.QUEUED_AWAITING_PREDECESSOR,
    )
    expect(posts).toHaveLength(0)
    const before = await queueSlots()
    const lifecycleBefore = lifecycleSlots(before)[0]!
    const store = await NativeEnvelopePersistence.open()
    const storedBefore = await store.read({
      tenantId: tenant,
      gameId,
      d4,
      d1: lifecycleBefore.d1,
      d5: String(lifecycleBefore.d5),
    })
    store.close()
    expect(storedBefore).not.toBeNull()

    const waiting = await c.retry()
    expect(waiting).toEqual({
      outcome: 'pending',
      reason: GAME_LIFECYCLE_REASON.PENDING_PREDECESSOR,
    })
    expect(posts).toHaveLength(0)
    const after = await queueSlots()
    expect(lifecycleSlots(after)[0]!.d5).toBe(lifecycleBefore.d5)
    const store2 = await NativeEnvelopePersistence.open()
    const storedAfter = await store2.read({
      tenantId: tenant,
      gameId,
      d4,
      d1: lifecycleBefore.d1,
      d5: String(lifecycleBefore.d5),
    })
    store2.close()
    expect(storedAfter).toEqual(storedBefore)
  })
})

describe('非成功と結果不明', () => {
  it('独立反例: baseだけ失ったreloadでもACK済みqueueより古いGETを採用しない', async () => {
    const c = controller()
    await c.refresh()
    forcedRead = currentRead()
    expect(await c.end()).toMatchObject({
      outcome: 'acked',
      refresh: 'pending',
    })
    expect(lifecycleSlots(await queueSlots())[0]).toMatchObject({
      d1: 1,
      state: '同期済み',
    })
    c.dispose()
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.deleteDatabase('pitchlog-game-lifecycle-base')
      request.onsuccess = () => resolve()
      request.onerror = () => reject(new Error('base deletion failed'))
      request.onblocked = () => reject(new Error('base deletion blocked'))
    })
    const restored = controller()
    const view = await restored.refresh()
    expect(view.refresh).toBe('failed')
    expect(view.lastFailure).toBe(GAME_LIFECYCLE_REASON.STALE_READ)
  })

  it('独立対向: base欠落で同D1の別receiptを拒否する', async () => {
    const c = controller()
    await c.refresh()
    await c.end()
    const endRead = currentRead()
    const differentReceipt =
      endRead.lifecycle.active?.receiptId ===
      'bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb'
        ? 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'
        : 'bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb'
    forcedRead = {
      ...endRead,
      lifecycle: {
        ...endRead.lifecycle,
        active: { ...endRead.lifecycle.active!, receiptId: differentReceipt },
      },
    }
    expect(isGameLifecycleGame(forcedRead)).toBe(true)
    c.dispose()
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.deleteDatabase('pitchlog-game-lifecycle-base')
      request.onsuccess = () => resolve()
      request.onerror = () => reject(new Error('base deletion failed'))
      request.onblocked = () => reject(new Error('base deletion blocked'))
    })
    const restored = controller()
    const view = await restored.refresh()
    expect(view.refresh).toBe('failed')
    expect(view.lastFailure).toBe(GAME_LIFECYCLE_REASON.STALE_READ)
  })

  it('baseと版基点が共に欠けたendは同receiptのGETでも確定扱いしない', async () => {
    const c = controller()
    await c.refresh()
    await c.end()
    const expected = currentRead()
    expect(expected.lifecycle.lastVersion).toBe('1')
    c.dispose()
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.deleteDatabase('pitchlog-game-lifecycle-base')
      request.onsuccess = () => resolve()
      request.onerror = () => reject(new Error('base deletion failed'))
      request.onblocked = () => reject(new Error('base deletion blocked'))
    })
    const restored = controller()
    const view = await restored.refresh()
    expect(view.refresh).toBe('failed')
    expect(view.lastFailure).toBe(GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE)
    expect(view.resumeHandoff).toBeNull()
  })

  it('独立対向: 壊れたbaseの読取は閉じ、資源を開き直せる', async () => {
    const c = controller()
    await c.refresh()
    c.dispose()
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('pitchlog-game-lifecycle-base')
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(new Error('base open failed'))
    })
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction('bases', 'readwrite')
      transaction.objectStore('bases').put({
        tenantId: tenant,
        gameId,
        d4,
        status: 'corrupt',
      })
      transaction.oncomplete = () => resolve()
      transaction.onabort = () => reject(new Error('base corruption failed'))
    })
    database.close()
    const restored = controller()
    const failed = await restored.refresh()
    expect(failed.refresh).toBe('failed')
    expect(failed.lastFailure).toBe(GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE)
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.deleteDatabase('pitchlog-game-lifecycle-base')
      request.onsuccess = () => resolve()
      request.onerror = () => reject(new Error('base deletion failed'))
      request.onblocked = () => reject(new Error('base deletion blocked'))
    })
    const fresh = await restored.refresh()
    expect(fresh.refresh).toBe('done')
  })

  it('独立反例: base欠落の再開ACK後に確定版0のGETを採用しない', async () => {
    installPendingReopenKind()
    const c = controller()
    await c.refresh()
    expect(await c.end()).toMatchObject({ outcome: 'acked', refresh: 'done' })
    expect(await c.reopen()).toMatchObject({
      outcome: 'acked',
      refresh: 'done',
    })
    const after = currentRead()
    expect(after.lifecycle.lastVersion).toBe('1')
    forcedRead = {
      ...after,
      lifecycle: { ...after.lifecycle, lastVersion: '0' },
    }
    expect(isGameLifecycleGame(forcedRead)).toBe(true)
    c.dispose()
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.deleteDatabase('pitchlog-game-lifecycle-base')
      request.onsuccess = () => resolve()
      request.onerror = () => reject(new Error('base deletion failed'))
      request.onblocked = () => reject(new Error('base deletion blocked'))
    })
    const restored = controller()
    const view = await restored.refresh()
    expect(view.resumeHandoff).toBeNull()
    expect(view.refresh).toBe('failed')
    expect(view.lastFailure).toBe(GAME_LIFECYCLE_REASON.STALE_READ)
    forcedRead = null
    const recovered = await restored.refresh()
    expect(recovered.refresh).toBe('done')
    expect(recovered.lastVersion).toBe('1')
    expect(recovered.resumeHandoff?.nextPosition.d1).toBe('3')
  })

  it('queued_endの初期版根拠を失った場合はGETを確定扱いしない', async () => {
    installPendingReopenKind()
    server.lastVersion = '7'
    const c = controller()
    await c.refresh()
    forcedRead = currentRead()
    expect(await c.end()).toMatchObject({
      outcome: 'acked',
      refresh: 'pending',
    })
    expect(await c.reopen()).toMatchObject({
      outcome: 'acked',
      refresh: 'pending',
    })
    expect(wireEvent(posts[1]!.body).payload.target).toMatchObject({
      kind: 'queued_end',
      d1: '1',
    })
    expect(currentRead().lifecycle.lastVersion).toBe('8')
    forcedRead = null
    c.dispose()
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.deleteDatabase('pitchlog-game-lifecycle-base')
      request.onsuccess = () => resolve()
      request.onerror = () => reject(new Error('base deletion failed'))
      request.onblocked = () => reject(new Error('base deletion blocked'))
    })
    const restored = controller()
    const view = await restored.refresh()
    expect(view.refresh).toBe('failed')
    expect(view.lastFailure).toBe(GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE)
    expect(view.resumeHandoff).toBeNull()
  })

  it('confirmed版基点から後続queued_endの正確な版を復元する', async () => {
    installPendingReopenKind()
    const c = controller()
    await c.refresh()
    expect(await c.end()).toMatchObject({ outcome: 'acked', refresh: 'done' })
    expect(await c.reopen()).toMatchObject({
      outcome: 'acked',
      refresh: 'done',
    })
    forcedRead = currentRead()
    expect(await c.end()).toMatchObject({
      outcome: 'acked',
      refresh: 'pending',
    })
    expect(await c.reopen()).toMatchObject({
      outcome: 'acked',
      refresh: 'pending',
    })
    expect(wireEvent(posts[3]!.body).payload.target).toMatchObject({
      kind: 'queued_end',
      d1: '3',
    })
    const actual = currentRead()
    expect(actual.lifecycle.lastVersion).toBe('2')
    forcedRead = {
      ...actual,
      lifecycle: { ...actual.lifecycle, lastVersion: '1' },
    }
    expect(isGameLifecycleGame(forcedRead)).toBe(true)
    c.dispose()
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.deleteDatabase('pitchlog-game-lifecycle-base')
      request.onsuccess = () => resolve()
      request.onerror = () => reject(new Error('base deletion failed'))
      request.onblocked = () => reject(new Error('base deletion blocked'))
    })
    const restored = controller()
    const stale = await restored.refresh()
    expect(stale.lastFailure).toBe(GAME_LIFECYCLE_REASON.STALE_READ)
    expect(stale.resumeHandoff).toBeNull()
    forcedRead = null
    const fresh = await restored.refresh()
    expect(fresh.refresh).toBe('done')
    expect(fresh.lastVersion).toBe('2')
    expect(fresh.resumeHandoff?.nextPosition.d1).toBe('5')
  })

  it('ACK済み要求の再確認でも古いGETを採用せず新たに送信しない', async () => {
    const c = controller()
    await c.refresh()
    forcedRead = currentRead()
    await c.end()
    expect(await c.retry()).toEqual({
      outcome: 'pending',
      reason: GAME_LIFECYCLE_REASON.STALE_READ,
    })
    expect(posts).toHaveLength(1)
    expect(c.view.refresh).toBe('failed')
  })

  it('reload後に同版の真正な再開GETが追いついたら次位置を渡す', async () => {
    installPendingReopenKind()
    const c = controller()
    await c.refresh()
    await c.end()
    forcedRead = currentRead()
    await c.reopen()
    c.dispose()
    const restored = controller()
    expect((await restored.refresh()).resumeHandoff).toBeNull()
    forcedRead = null
    const fresh = await restored.refresh()
    expect(fresh.refresh).toBe('done')
    expect(fresh.resumeHandoff?.nextPosition.d1).toBe('3')
    expect(fresh.lastVersion).toBe('1')
  })

  it('再開ACKより新しい真正な終了版は後続結果として採用する', async () => {
    installPendingReopenKind()
    const c = controller()
    await c.refresh()
    await c.end()
    forcedRead = currentRead()
    await c.reopen()
    // 別の正当な後続終了を返すGET fixture。実DBの成立証拠ではない。
    serverD3 = 3
    server = {
      status: 'finished',
      lastVersion: '2',
      active: {
        version: '2',
        eventId: 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
        receiptId: 'bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb',
      },
      statsId: 'cccccccc-1111-4111-8111-cccccccccccc',
    }
    forcedRead = null
    const fresh = await c.refresh()
    expect(fresh.refresh).toBe('done')
    expect(fresh.lastVersion).toBe('2')
    expect(fresh.confirmedStatus).toBe('finished')
    expect(fresh.resumeHandoff).toBeNull()
  })

  it('同版でもACK水位未満のGETや別receiptを採用しない', async () => {
    const c = controller()
    await c.refresh()
    forcedRead = currentRead()
    await c.end()
    const ended = currentRead()
    forcedRead = {
      ...ended,
      checkpoint: {
        ...ended.checkpoint,
        content: { ...ended.checkpoint.content, d3: '0' },
      },
      next_position: { ...ended.next_position, d1: '1' },
    }
    expect((await c.refresh()).lastFailure).toBe(
      GAME_LIFECYCLE_REASON.STALE_READ,
    )
    forcedRead = {
      ...ended,
      lifecycle: {
        ...ended.lifecycle,
        active: {
          ...ended.lifecycle.active!,
          receiptId: 'bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb',
        },
      },
    }
    expect((await c.refresh()).lastFailure).toBe(
      GAME_LIFECYCLE_REASON.STALE_READ,
    )
  })

  it('独立対向: ACK後のstale GETは次の手動refreshでも取得済みにしない', async () => {
    const c = controller()
    await c.refresh()
    forcedRead = currentRead()
    expect(await c.end()).toMatchObject({
      outcome: 'acked',
      refresh: 'pending',
    })
    const retried = await c.refresh()
    expect(retried.refresh).toBe('failed')
    expect(retried.lastFailure).toBe(GAME_LIFECYCLE_REASON.STALE_READ)
    expect(retried.confirmedStatus).toBe('in_progress')
  })

  it('独立対向: 再開ACK後のstale GETで通常入力へhandoffしない', async () => {
    installPendingReopenKind()
    const c = controller()
    await c.refresh()
    expect(await c.end()).toMatchObject({ outcome: 'acked', refresh: 'done' })
    forcedRead = currentRead()
    expect(await c.reopen()).toMatchObject({
      outcome: 'acked',
      refresh: 'pending',
    })
    const retried = await c.refresh()
    expect(retried.resumeHandoff).toBeNull()
  })

  it('独立対向: 再開ACK後のreloadでもstale GETをhandoffへ昇格しない', async () => {
    installPendingReopenKind()
    const c = controller()
    await c.refresh()
    expect(await c.end()).toMatchObject({ outcome: 'acked', refresh: 'done' })
    forcedRead = currentRead()
    expect(await c.reopen()).toMatchObject({
      outcome: 'acked',
      refresh: 'pending',
    })
    c.dispose()
    const reloaded = controller()
    const restored = await reloaded.refresh()
    expect(restored.resumeHandoff).toBeNull()
    expect(restored.refresh).toBe('failed')
  })

  it('ACK喪失は保存成功にせず、同D5/同本文/同attemptだけで再送する', async () => {
    const c = controller()
    await c.refresh()
    postMode = 'lost-ack'
    const lost = await c.end()
    expect(lost.outcome).toBe('pending')
    expect(c.view.saveAck).toBeNull()
    expect(c.view.unknownCount).toBe(1)
    expect(await queueSlots()).toHaveLength(1)
    expect(posts).toHaveLength(1)

    const c2 = controller()
    await c2.refresh()
    postMode = 'ok'
    const retried = await c2.retry()
    expect(retried).toEqual({
      outcome: 'acked',
      ack: 'duplicate',
      refresh: 'done',
    })
    expect(posts).toHaveLength(2)
    expect(posts[1]!.body).toEqual(posts[0]!.body)
    expect(posts[1]!.attempt).toBe(posts[0]!.attempt)
    expect(await queueSlots()).toHaveLength(1)
    expect(c2.view.status).toBe('finished')
    expect(c2.view.unknownCount).toBe(0)
  })

  it.each(['http-409', 'http-503'] as const)(
    '%sは保存成功にせず、slotを未送信のまま残す',
    async (mode) => {
      const c = controller()
      await c.refresh()
      postMode = mode
      const result = await c.end()
      expect(result.outcome).toBe('pending')
      expect(c.view.saveAck).toBeNull()
      expect((await queueSlots())[0]?.state).toBe('未送信')
      expect(c.view.lastFailure).toBe(GAME_LIFECYCLE_REASON.SEND_NOT_ACCEPTED)
    },
  )

  it('ACK後に古いGETが返ったら再取得完了にしない', async () => {
    const c = controller()
    await c.refresh()
    // 操作前のin_progressを、ACK後のGETとして返させる。
    forcedRead = currentRead()
    const result = await c.end()
    expect(result).toEqual({
      outcome: 'acked',
      ack: 'accepted',
      refresh: 'pending',
    })
    expect(c.view.refresh).toBe('failed')
    expect(c.view.lastFailure).toBe(GAME_LIFECYCLE_REASON.STALE_READ)
    expect(c.view.confirmedStatus).toBe('in_progress')
    expect(c.view.status).toBe('finished')
    expect(c.view.stale).toBe(true)

    forcedRead = null
    const refreshed = await c.refresh()
    expect(refreshed.refresh).toBe('done')
    expect(refreshed.confirmedStatus).toBe('finished')
    expect(refreshed.status).toBe('finished')
    expect(refreshed.lastVersion).toBe('1')
  })

  it('保存ACKと実GET不能を区別し、成功を装わない', async () => {
    const c = controller()
    await c.refresh()
    readFails = true
    const result = await c.end()
    expect(result.outcome).toBe('acked')
    if (result.outcome !== 'acked') return
    expect(result.refresh).toBe('pending')
    expect(c.view.saveAck).toBe('accepted')
    expect(c.view.refresh).toBe('failed')
    expect(c.view.stale).toBe(true)
    expect(c.view.status).toBe('finished')
    expect(c.view.confirmedStatus).toBe('in_progress')
    expect(c.view.lastFailure).toBe(GAME_LIFECYCLE_REASON.READ_FAILED)
  })

  it('旧server/旧projectionは成功にしない', async () => {
    vi.mocked(lifecycle.readGameLifecycle).mockResolvedValue({
      kind: 'unsupported',
    })
    const c = controller()
    const view = await c.refresh()
    expect(view.status).toBeNull()
    expect(view.confirmedStatus).toBeNull()
    expect(view.lastFailure).toBe(GAME_LIFECYCLE_REASON.READ_UNSUPPORTED)
    expect(view.canEnd).toBe(false)
    expect(await c.end()).toEqual({
      outcome: 'blocked',
      reason: GAME_LIFECYCLE_REASON.READ_UNSUPPORTED,
    })
    expect(posts).toHaveLength(0)
  })
})

describe('書込前提', () => {
  it('二重タブ（鍵なし）は追記せず、blockedを返す', async () => {
    const c = controller({
      writer: {
        ...writer,
        lockManager: {
          request: async (_name, operation) => await operation(null),
        },
      },
    })
    await c.refresh()
    expect(await c.end()).toEqual({
      outcome: 'blocked',
      reason: GAME_LIFECYCLE_REASON.LOCK_UNAVAILABLE,
    })
    expect(await queueSlots()).toHaveLength(0)
    expect(posts).toHaveLength(0)
  })

  it('認証epoch/tenantの変更は追記しない', async () => {
    const c = controller()
    await c.refresh()
    identity = { tenantId: tenant, epoch: 2, verified: true }
    expect(await c.end()).toEqual({
      outcome: 'blocked',
      reason: GAME_LIFECYCLE_REASON.IDENTITY_CHANGED,
    })
    expect(await queueSlots()).toHaveLength(0)
    expect(posts).toHaveLength(0)
  })

  it('grantsと実GETの世代が食い違えば追記しない', async () => {
    vi.mocked(lifecycle.readGameLifecycle).mockResolvedValue({
      kind: 'found',
      game: { ...currentRead(), recovery_generation: '999' },
    })
    const c = controller()
    await c.refresh()
    expect(c.view.lastFailure).toBe(GAME_LIFECYCLE_REASON.GRANT_CHANGED)
    expect(await c.end()).toEqual({
      outcome: 'blocked',
      reason: GAME_LIFECYCLE_REASON.GRANT_CHANGED,
    })
    expect(await queueSlots()).toHaveLength(0)
  })
})

describe('画面パネル', () => {
  function view(overrides: Partial<GameLifecycleView> = {}): GameLifecycleView {
    return {
      status: 'finished',
      confirmedStatus: 'finished',
      lastVersion: '2',
      active: {
        version: '2',
        eventId: '33333333-3333-4333-8333-333333333333',
        receiptId: '44444444-4444-4444-8444-444444444444',
      },
      lastSavedAt: '2026-11-06T10:00:00Z',
      nextPosition: { d1: '7', d2: '1' },
      recoveryGeneration: '1',
      checkpointRef: {
        id: '66666666-6666-4666-8666-666666666666',
        revision: '3',
        digest: 'c'.repeat(64),
      },
      pageItemCount: 1,
      hasNextPage: false,
      preparedCount: 0,
      unknownCount: 0,
      unpreparedCount: 0,
      pendingLifecycleCount: 0,
      otherUnsettledCount: 0,
      scanTruncated: false,
      saveAck: 'accepted',
      refresh: 'done',
      stale: false,
      lastFailure: null,
      blockedReason: null,
      reopenBlocked: false,
      canEnd: false,
      canReopen: true,
      canRetry: false,
      busy: false,
      resumeHandoff: null,
      ...overrides,
    }
  }

  it('期待status/サーバー確認済み/最終更新/未送信・結果不明を表示する', () => {
    const wrapper = mount(GameScreenLifecyclePanel, {
      props: {
        view: view({
          status: 'finished',
          confirmedStatus: 'in_progress',
          pendingLifecycleCount: 2,
          preparedCount: 3,
          unknownCount: 2,
          lastFailure: 'stale-read',
        }),
      },
    })
    expect(wrapper.get('[data-testid="lifecycle-status"]').text()).toBe('終了')
    expect(
      wrapper.get('[data-testid="lifecycle-confirmed-status"]').text(),
    ).toBe('進行中')
    expect(wrapper.get('[data-testid="lifecycle-last-version"]').text()).toBe(
      'v2',
    )
    expect(wrapper.get('[data-testid="lifecycle-active"]').text()).toBe('v2')
    expect(
      wrapper
        .get('[data-testid="lifecycle-last-saved"]')
        .attributes('datetime'),
    ).toBe('2026-11-06T10:00:00Z')
    expect(wrapper.get('[data-testid="lifecycle-unknown-count"]').text()).toBe(
      '2件',
    )
    expect(wrapper.get('[data-testid="lifecycle-unsent-count"]').text()).toBe(
      '3件',
    )
    expect(
      wrapper.get('[data-testid="lifecycle-server-unconfirmed"]').text(),
    ).toContain('2件')
    expect(wrapper.get('[data-testid="lifecycle-failure"]').text()).toContain(
      '追いついていません',
    )
  })

  it('再開未裁定は実行できず、理由を表示する', () => {
    const wrapper = mount(GameScreenLifecyclePanel, {
      props: {
        view: view({
          reopenBlocked: true,
          canReopen: false,
          blockedReason: 'reopen-kind-unavailable',
        }),
      },
    })
    expect(
      wrapper.get('[data-testid="lifecycle-reopen"]').attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.get('[data-testid="lifecycle-reopen-blocked"]').text(),
    ).toContain('接合')
    expect(
      wrapper.get('[data-testid="lifecycle-blocked-reason"]').text(),
    ).toContain('正式裁定')
  })

  it('操作をemitし、資格原値を表示しない', async () => {
    const handoff = {
      gameId,
      tenantId: tenant,
      nextPosition: { d1: '7', d2: '1' },
      checkpointRef: {
        id: '66666666-6666-4666-8666-666666666666',
        revision: '3',
        digest: 'c'.repeat(64),
      },
      recoveryGeneration: '1',
      lastSavedAt: '2026-11-06T10:00:00Z',
    }
    const wrapper = mount(GameScreenLifecyclePanel, {
      props: {
        view: view({
          status: 'in_progress',
          confirmedStatus: 'in_progress',
          active: null,
          canEnd: true,
          canReopen: false,
          resumeHandoff: handoff,
        }),
      },
    })
    await wrapper.get('[data-testid="lifecycle-end"]').trigger('click')
    await wrapper.get('[data-testid="lifecycle-refresh"]').trigger('click')
    await wrapper.get('[data-testid="lifecycle-resume"]').trigger('click')
    await wrapper.get('[data-testid="lifecycle-back"]').trigger('click')
    expect(wrapper.emitted('end')).toHaveLength(1)
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.emitted('back')).toHaveLength(1)
    expect(wrapper.emitted('resume-recording')?.[0]).toEqual([handoff])
    expect(wrapper.text()).not.toContain('unit-only-proof')
    expect(wrapper.text()).not.toContain('unit-only-credential')
  })
})
