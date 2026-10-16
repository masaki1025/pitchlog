import 'fake-indexeddb/auto'

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueScope,
} from '../lib/sync/durableQueue'
import type {
  ExclusiveLockManager,
  SingleWriterInjections,
} from '../lib/sync/singleWriter'
import type { SyncEvent } from '../lib/sync/syncEvent'
import {
  acceptPitchEvent,
  PITCH_ACCEPTANCE_FAILURE,
  type PitchAcceptanceQueue,
} from './GameScreenPitchAcceptance'
import acceptanceSource from './GameScreenPitchAcceptance.ts?raw'
import { buildPitchEventDraft } from './GameScreenPitchEvent'

const gameIdentifier = 'f1e2d3c4-b5a6-4789-9abc-def012345678'
const scope: DurableQueueScope = { game: gameIdentifier, d4: 'generation-a' }
const d5 = '0b5f1c2e-3a4d-4e5f-8a9b-0c1d2e3f4a5b'

let databaseSequence = 0
const openedQueues: DurableQueue[] = []

afterEach(() => {
  for (const queue of openedQueues.splice(0)) {
    queue.close()
  }
  vi.restoreAllMocks()
})

async function openIsolatedQueue(): Promise<DurableQueue> {
  databaseSequence += 1
  const queue = await openDurableQueue({
    databaseName: `uf8-pitch-acceptance-${databaseSequence}`,
    requestStoragePersistence: async () => false,
  })
  openedQueues.push(queue)
  return queue
}

/** 下書き(ステップ 1)に「モックの」状態差分を足したイベント。計算核は使わない。 */
function eventWithMockStateDiff(marker = 'mock-state-diff'): SyncEvent {
  const draft = buildPitchEventDraft({
    d5,
    d4: 'generation-a',
    gameId: gameIdentifier,
    d2: '0007',
    payload: { resultId: 'ball' },
  })
  if (!draft.ok) {
    throw new Error('下書きを組み立てられませんでした')
  }
  return { fields: { ...draft.draft.fields, V8: { marker } } }
}

function lockManagerThatGrants(): ExclusiveLockManager {
  return {
    request: async (_name, callback) => callback({ granted: true }),
  }
}

function singleWriterInjections(
  overrides: Partial<SingleWriterInjections> = {},
): SingleWriterInjections {
  return {
    resolvePreconditions: () => ({
      topLevelHttps: true,
      sameBrowserProfile: true,
      sameBrowsingMode: true,
      sameStorageBucket: true,
      siteStorageAvailable: true,
      lockdownModeNotApplied: true,
    }),
    revalidateSingleWriter: () => true,
    lockManager: lockManagerThatGrants(),
    ...overrides,
  }
}

function input(event: SyncEvent = eventWithMockStateDiff()) {
  return { gameIdentifier, scope, d5, version: { marker: 'v1' }, event }
}

describe('排他の下での採番・永続追記・受理', () => {
  it('追記が成立した時点を受理とし、D1 は durableQueue が採番する', async () => {
    const queue = await openIsolatedQueue()

    const result = await acceptPitchEvent(input(), {
      queue,
      singleWriterInjections: singleWriterInjections(),
    })

    expect(result.outcome).toBe('accepted')
    if (result.outcome !== 'accepted') return
    expect(result.slot.d1).toBe(1)
    expect(result.slot.state).toBe('未送信')
    expect(result.unsentCount).toBe(1)
    expect(await queue.readSlot(scope, 1)).toBeDefined()
  })

  it('同じ範囲への 2 件目は D1 が 1 つ進む', async () => {
    const queue = await openIsolatedQueue()
    const injections = singleWriterInjections()

    await acceptPitchEvent(input(), {
      queue,
      singleWriterInjections: injections,
    })
    const second = await acceptPitchEvent(
      input({
        fields: { ...eventWithMockStateDiff('second').fields, V1: 'second-d5' },
      }),
      { queue, singleWriterInjections: injections },
    )

    expect(second.outcome).toBe('accepted')
    if (second.outcome !== 'accepted') return
    expect(second.slot.d1).toBe(2)
  })

  it('未送信件数の閾値を伝える', async () => {
    const queue = await openIsolatedQueue()

    const result = await acceptPitchEvent(input(), {
      queue,
      singleWriterInjections: singleWriterInjections(),
      warningThreshold: 1,
    })

    expect(result.outcome).toBe('accepted')
    if (result.outcome !== 'accepted') return
    expect(result.warningThresholdReached).toBe(true)
  })
})

describe('排他が取れないときは追記しない', () => {
  it.each([
    ['鍵の管理機構が無い', singleWriterInjections({ lockManager: null })],
    [
      '前提が揃っていない',
      singleWriterInjections({ resolvePreconditions: () => undefined }),
    ],
    [
      '再確認が通らない',
      singleWriterInjections({ revalidateSingleWriter: () => false }),
    ],
  ])('%s ときは受理せず、キューへ何も積まない', async (_label, injections) => {
    const queue = await openIsolatedQueue()
    const append = vi.spyOn(queue, 'append')

    const result = await acceptPitchEvent(input(), {
      queue,
      singleWriterInjections: injections,
    })

    expect(result).toMatchObject({
      outcome: 'not-accepted',
      reason: PITCH_ACCEPTANCE_FAILURE.SINGLE_WRITER_NOT_STARTED,
    })
    expect(append).not.toHaveBeenCalled()
    expect(await queue.countSlots()).toBe(0)
  })
})

describe('追記の成否を戻り値だけで判定しない', () => {
  it('未送信件数の読取りだけが失敗しても、追記は成立しているので受理とする', async () => {
    const queue = await openIsolatedQueue()
    const failingCount: PitchAcceptanceQueue = {
      prepareAppend: (value) => queue.prepareAppend(value),
      append: (preparation) => queue.append(preparation),
      countUnsentSlots: () => Promise.reject(new Error('件数を読めません')),
      readSlot: (target, d1) => queue.readSlot(target, d1),
      readNextD1: (target) => queue.readNextD1(target),
    }

    const result = await acceptPitchEvent(input(), {
      queue: failingCount,
      singleWriterInjections: singleWriterInjections(),
    })

    expect(result.outcome).toBe('accepted')
    if (result.outcome !== 'accepted') return
    expect(result.unsentCount).toBeUndefined()
    expect(result.warningThresholdReached).toBeUndefined()
    // 実際にキューへ積まれている。
    expect(await queue.readSlot(scope, 1)).toBeDefined()
  })

  it('追記そのものが失敗していれば、読取りで確かめて受理しない', async () => {
    const queue = await openIsolatedQueue()
    const failingAppend: PitchAcceptanceQueue = {
      prepareAppend: (value) => queue.prepareAppend(value),
      append: () => Promise.reject(new Error('追記できません')),
      countUnsentSlots: () => queue.countUnsentSlots(),
      readSlot: (target, d1) => queue.readSlot(target, d1),
      readNextD1: (target) => queue.readNextD1(target),
    }

    const result = await acceptPitchEvent(input(), {
      queue: failingAppend,
      singleWriterInjections: singleWriterInjections(),
    })

    expect(result).toEqual({
      outcome: 'not-accepted',
      reason: PITCH_ACCEPTANCE_FAILURE.APPEND_FAILED,
    })
    expect(await queue.countSlots()).toBe(0)
  })

  it('同じ D1 に別の D5 のスロットがあっても、自分の追記が成立したとは見なさない', async () => {
    const queue = await openIsolatedQueue()
    await queue.append(
      queue.prepareAppend({
        scope,
        d5: 'other-d5',
        version: {},
        event: { fields: {} },
      }),
    )
    const failingAppend: PitchAcceptanceQueue = {
      prepareAppend: (value) => queue.prepareAppend(value),
      append: () => Promise.reject(new Error('追記できません')),
      countUnsentSlots: () => queue.countUnsentSlots(),
      // 追記前に読んだ次の D1(2)ではなく、既存スロット(D1=1)を返してしまう場合。
      readSlot: () => queue.readSlot(scope, 1),
      readNextD1: (target) => queue.readNextD1(target),
    }

    const result = await acceptPitchEvent(input(), {
      queue: failingAppend,
      singleWriterInjections: singleWriterInjections(),
    })

    expect(result).toEqual({
      outcome: 'not-accepted',
      reason: PITCH_ACCEPTANCE_FAILURE.APPEND_FAILED,
    })
  })
})

describe('成否を確かめられないときは受理を表示しない', () => {
  it('照合の読取りが失敗すれば不明として返す', async () => {
    const queue = await openIsolatedQueue()
    const unreadable: PitchAcceptanceQueue = {
      prepareAppend: (value) => queue.prepareAppend(value),
      append: () => Promise.reject(new Error('追記できません')),
      countUnsentSlots: () => queue.countUnsentSlots(),
      readSlot: () => Promise.reject(new Error('読めません')),
      readNextD1: (target) => queue.readNextD1(target),
    }

    const result = await acceptPitchEvent(input(), {
      queue: unreadable,
      singleWriterInjections: singleWriterInjections(),
    })

    expect(result).toEqual({
      outcome: 'undetermined',
      reason: PITCH_ACCEPTANCE_FAILURE.RECONCILIATION_FAILED,
    })
  })

  it('照合に使う次の D1 を読めていなければ不明として返す', async () => {
    const queue = await openIsolatedQueue()
    const unreadable: PitchAcceptanceQueue = {
      prepareAppend: (value) => queue.prepareAppend(value),
      append: () => Promise.reject(new Error('追記できません')),
      countUnsentSlots: () => queue.countUnsentSlots(),
      readSlot: (target, d1) => queue.readSlot(target, d1),
      readNextD1: () => Promise.reject(new Error('採番を読めません')),
    }

    const result = await acceptPitchEvent(input(), {
      queue: unreadable,
      singleWriterInjections: singleWriterInjections(),
    })

    expect(result).toEqual({
      outcome: 'undetermined',
      reason: PITCH_ACCEPTANCE_FAILURE.RECONCILIATION_FAILED,
    })
  })

  it('受理でない結果はスロットを持たない', async () => {
    const queue = await openIsolatedQueue()

    const result = await acceptPitchEvent(input(), {
      queue,
      singleWriterInjections: singleWriterInjections({ lockManager: null }),
    })

    expect(result).not.toHaveProperty('slot')
  })
})

describe('隔離', () => {
  it('本モジュールはキューを開かず、呼出元が注入したキューだけを使う', () => {
    expect(acceptanceSource).not.toContain('openDurableQueue')
    expect(acceptanceSource).not.toContain('indexedDB')
  })
})
