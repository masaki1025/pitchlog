// @vitest-environment-options {"url":"https://pitchlog.test"}
//
// この spec は保存呼出順・耐久・ACK 分岐・再取得分岐を検査する。
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
  type GameLifecycleView,
} from './gameLifecycleController'
import { undoRead } from './GameScreenUndoProduct.test-support'

const base = undoRead()
const tenant = base.checkpoint.content.scope.tenantId
const gameId = base.id
const d4 = base.current_d4
const deviceId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

type WirePayload = Readonly<{
  formatVersion: string
  action: 'end' | 'reopen'
  checkpointRef: unknown
  target: unknown
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
let applied: Set<string>
let posts: { body: GameLifecycleRequestBody; attempt: string }[]
let readFailsFrom: number
let readCount: number
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
  applied = new Set()
  posts = []
  readFailsFrom = Number.POSITIVE_INFINITY
  readCount = 0
  postMode = 'ok'
}

function currentRead(): GameLifecycleGame {
  const value: unknown = {
    ...base,
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

/** 既通常/NP入力の代わりに「同じqueueの2球」だけを積む。計算は実装しない。 */
async function appendOrdinaryMarkers(count: number): Promise<void> {
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
            V6: 1000 + index,
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
        away_lineup_id: base.lineups.away.lineup_id,
        home_lineup_id: base.lineups.home.lineup_id,
        recording_right_proof: 'unit-only-proof',
        recovery_generation: base.recovery_generation,
      },
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
  vi.spyOn(lifecycle, 'readGameLifecycle').mockImplementation(
    async (): Promise<GameLifecycleReadResult> => {
      readCount += 1
      if (readCount >= readFailsFrom) throw new Error('read failed')
      return { kind: 'found', game: currentRead() }
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

describe('終了から再終了まで', () => {
  it('終了v1→再開→2球→再終了v2→reloadを、同queue/同本文/実GET復元で接続する', async () => {
    // 再開種別の正式裁定patchが入った後の遷移を、表への一時追加で再現する。
    installPendingReopenKind()
    const c = controller()
    const first = await c.refresh()
    expect(first.status).toBe('in_progress')
    expect(first.canEnd).toBe(true)
    expect(first.canReopen).toBe(false)
    expect(first.resumeHandoff).not.toBeNull()

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
      d2: Number(base.next_position.d2),
    })
    expect(wireEvent(posts[0]!.body).payload).toMatchObject({
      formatVersion: 'native-game-lifecycle-v1',
      action: 'end',
      checkpointRef: base.checkpoint.ref,
      target: null,
    })
    expect(posts[0]!.body.recording_right_proof).toBe('unit-only-proof')
    const view1 = c.view
    expect(view1.status).toBe('finished')
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
      target,
      checkpointRef: base.checkpoint.ref,
    })
    const view2 = c.view
    expect(view2.status).toBe('in_progress')
    expect(view2.active).toBeNull()
    expect(view2.lastVersion).toBe('1')

    // 既通常/NP入力controllerが積む2球分。計算はここで実装しない。
    await appendOrdinaryMarkers(2)
    const deferred = await c.end()
    expect(deferred.outcome).toBe('pending')
    if (deferred.outcome !== 'pending') return
    expect(deferred.reason).toBe(
      GAME_LIFECYCLE_REASON.QUEUED_AWAITING_PREDECESSOR,
    )
    // FR-010: 未同期プレイがあっても終了宣言はキューへ積む。ただし先行分を飛ばして
    // 送らない（postsは増えない）。
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
    expect(view3.lastVersion).toBe('2')
    expect(view3.active?.version).toBe('2')

    // reload: 新しいcontrollerが実GETからだけ復元する。
    const reloaded = controller()
    const restored = await reloaded.refresh()
    expect(restored.status).toBe('finished')
    expect(restored.lastVersion).toBe('2')
    expect(restored.active?.version).toBe('2')
    expect(restored.activeStatsVersionId).toBe(server.statsId)
    expect(restored.saveAck).toBeNull()
    expect(restored.unknownCount).toBe(0)
  })

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
})

describe('非成功と結果不明', () => {
  it('ACK喪失は保存成功にせず、同D5/同本文/同attemptだけで再送する', async () => {
    const c = controller()
    await c.refresh()
    postMode = 'lost-ack'
    const lost = await c.end()
    expect(lost.outcome).toBe('pending')
    expect(c.view.saveAck).toBeNull()
    expect(c.view.unknownCount).toBe(1)
    expect(await queueSlots()).toHaveLength(1)

    postMode = 'ok'
    const retried = await c.retry()
    expect(retried).toEqual({
      outcome: 'acked',
      ack: 'duplicate',
      refresh: 'done',
    })
    expect(posts).toHaveLength(2)
    expect(posts[1]!.body).toEqual(posts[0]!.body)
    expect(posts[1]!.attempt).toBe(posts[0]!.attempt)
    expect(await queueSlots()).toHaveLength(1)
    expect(c.view.status).toBe('finished')
    expect(c.view.unknownCount).toBe(0)
  })

  it('reload後も原本文とattemptを復元し、新D5へ置換しない', async () => {
    const c = controller()
    await c.refresh()
    postMode = 'lost-ack'
    expect((await c.end()).outcome).toBe('pending')
    const firstBody = posts[0]!.body
    const firstAttempt = posts[0]!.attempt
    c.dispose()

    const reloaded = controller()
    const view = await reloaded.refresh()
    expect(view.status).toBe('finished')
    expect(view.unknownCount).toBe(1)
    expect(view.saveAck).toBeNull()

    postMode = 'ok'
    const retried = await reloaded.retry()
    expect(retried).toEqual({
      outcome: 'acked',
      ack: 'duplicate',
      refresh: 'done',
    })
    expect(posts[1]!.body).toEqual(firstBody)
    expect(posts[1]!.attempt).toBe(firstAttempt)
    expect(await queueSlots()).toHaveLength(1)
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
      expect(c.view.status).toBe('in_progress')
      expect((await queueSlots())[0]?.state).toBe('未送信')
      expect(c.view.lastFailure).toBe(GAME_LIFECYCLE_REASON.SEND_NOT_ACCEPTED)
    },
  )

  it('保存ACKと実GET未了を区別し、成功を装わない', async () => {
    const c = controller()
    await c.refresh()
    // 書込前GET(#2)は成功し、ACK後GET(#3)だけを失敗させる。
    readFailsFrom = 3
    const result = await c.end()
    expect(result).toEqual({
      outcome: 'acked',
      ack: 'accepted',
      refresh: 'pending',
    })
    expect(c.view.saveAck).toBe('accepted')
    expect(c.view.refresh).toBe('failed')
    expect(c.view.stale).toBe(true)
    expect(c.view.lastFailure).toBe(GAME_LIFECYCLE_REASON.READ_FAILED)
    expect(c.view.canEnd).toBe(false)
    expect((await queueSlots())[0]?.state).toBe('同期済み')
  })

  it('旧server/旧projectionは成功にしない', async () => {
    vi.mocked(lifecycle.readGameLifecycle).mockResolvedValue({
      kind: 'unsupported',
    })
    const c = controller()
    const view = await c.refresh()
    expect(view.status).toBeNull()
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

  it('先行の未終結slotを飛ばして送らない（追記は受理済みで保持する）', async () => {
    await appendOrdinaryMarkers(1)
    const c = controller()
    await c.refresh()
    const result = await c.end()
    expect(result.outcome).toBe('pending')
    if (result.outcome !== 'pending') return
    expect(result.reason).toBe(
      GAME_LIFECYCLE_REASON.QUEUED_AWAITING_PREDECESSOR,
    )
    const slots = await queueSlots()
    expect(slots).toHaveLength(2)
    expect(slots[1]!.event.fields.V5).toBe('5')
    expect(slots[1]!.state).toBe('未送信')
    expect(c.view.preparedCount).toBe(1)
    expect(c.view.unknownCount).toBe(0)
    expect(c.view.canRetry).toBe(false)
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
      lastVersion: '2',
      active: {
        version: '2',
        eventId: '33333333-3333-4333-8333-333333333333',
        receiptId: '44444444-4444-4444-8444-444444444444',
      },
      activeStatsVersionId: '55555555-5555-4555-8555-555555555555',
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
      unknownCount: 0,
      preparedCount: 0,
      unpreparedCount: 0,
      otherUnsettledCount: 0,
      scanTruncated: false,
      saveAck: 'accepted',
      refresh: 'done',
      stale: false,
      lastFailure: null,
      reopenBlocked: false,
      canEnd: false,
      canReopen: true,
      canRetry: false,
      busy: false,
      resumeHandoff: null,
      ...overrides,
    }
  }

  it('status/確定版/最終更新/未送信・結果不明を表示する', () => {
    const wrapper = mount(GameScreenLifecyclePanel, {
      props: {
        view: view({
          unknownCount: 2,
          preparedCount: 3,
          lastFailure: 'send-not-accepted',
        }),
      },
    })
    expect(wrapper.get('[data-testid="lifecycle-status"]').text()).toBe('終了')
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
    expect(wrapper.get('[data-testid="lifecycle-failure"]').text()).toContain(
      '結果は未確定',
    )
  })

  it('再開未裁定は実行できず、理由を表示する', () => {
    const wrapper = mount(GameScreenLifecyclePanel, {
      props: { view: view({ reopenBlocked: true, canReopen: false }) },
    })
    expect(
      wrapper.get('[data-testid="lifecycle-reopen"]').attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.get('[data-testid="lifecycle-reopen-blocked"]').text(),
    ).toContain('接合')
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

describe('耐久store', () => {
  it('queue受理前の準備行をD1単位で復元できる', async () => {
    const c = controller()
    await c.refresh()
    postMode = 'lost-ack'
    await c.end()
    const store = await NativeEnvelopePersistence.open()
    try {
      const prepared = await store.readPreparedSlot({
        tenantId: tenant,
        gameId,
        d4,
        d1: 2,
      })
      expect(prepared).toBeNull()
      const stored = await store.read({
        tenantId: tenant,
        gameId,
        d4,
        d1: 1,
        d5: wireEvent(posts[0]!.body).d5,
      })
      expect(stored?.attemptId).toBe(posts[0]!.attempt)
      expect(JSON.parse(stored!.requestJson)).toEqual(posts[0]!.body)
    } finally {
      store.close()
    }
  })
})
