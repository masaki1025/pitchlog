import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from './client'
import { ApiError } from './client'
import {
  GAME_LIFECYCLE_PROJECTION,
  GAME_LIFECYCLE_READ_FORMAT,
  GAME_LIFECYCLE_WIRE_EVENT_KIND,
  buildGameLifecyclePayload,
  buildGameLifecycleRequestBody,
  buildGameLifecycleSyncEvent,
  gameLifecycleEventKind,
  isGameLifecycleGame,
  isGameLifecycleRequestBody,
  isGameLifecycleMeta,
  postGameLifecycleRequestBody,
  readGameLifecycle,
  type GameLifecycleGame,
} from './gameLifecycle'
import { queueStateId } from '../lib/sync/queueState'
import type { DurableQueueSlot } from '../lib/sync/durableQueue'
import { undoRead } from '../screens/GameScreenUndoProduct.test-support'

const tenant = '11111111-1111-4111-8111-111111111111'
const gameId = '22222222-2222-4222-8222-222222222222'
const d4 = 'd4.1.' + 'A'.repeat(55)
const proof = 'unit-only-proof'

function inProgress(): GameLifecycleGame {
  const base = undoRead()
  const value: unknown = {
    ...base,
    id: gameId,
    current_d4: d4,
    recovery_generation: '7',
    checkpoint: {
      ...base.checkpoint,
      content: {
        ...base.checkpoint.content,
        scope: {
          ...base.checkpoint.content.scope,
          tenantId: tenant,
          gameId,
          generation: d4,
        },
      },
    },
    status: 'in_progress',
    lifecycle: {
      formatVersion: GAME_LIFECYCLE_READ_FORMAT,
      status: 'in_progress',
      lastVersion: '3',
      active: null,
      activeStatsVersionId: null,
    },
  }
  if (!isGameLifecycleGame(value))
    throw new Error('in_progress fixture invalid')
  return value
}

function finished(from: GameLifecycleGame = inProgress()): GameLifecycleGame {
  const value: unknown = {
    ...from,
    status: 'finished',
    lifecycle: {
      formatVersion: GAME_LIFECYCLE_READ_FORMAT,
      status: 'finished',
      lastVersion: '4',
      active: {
        version: '4',
        eventId: '33333333-3333-4333-8333-333333333333',
        receiptId: '44444444-4444-4444-8444-444444444444',
      },
      activeStatsVersionId: '55555555-5555-4555-8555-555555555555',
    },
  }
  if (!isGameLifecycleGame(value)) throw new Error('finished fixture invalid')
  return value
}

function slot(action: 'end' | 'reopen' = 'end'): DurableQueueSlot {
  const kind = kindForTest(action)
  const payload = buildGameLifecyclePayload({
    action,
    checkpointRef: {
      id: '66666666-6666-4666-8666-666666666666',
      revision: '2',
      digest: 'a'.repeat(64),
    },
    target:
      action === 'reopen'
        ? {
            version: '4',
            eventId: '33333333-3333-4333-8333-333333333333',
            receiptId: '44444444-4444-4444-8444-444444444444',
          }
        : null,
    event: {
      eventId: '77777777-7777-4777-8777-777777777777',
      receiptId: '88888888-8888-4888-8888-888888888888',
    },
  })
  return {
    game: gameId,
    d4,
    d1: 5,
    d5: '99999999-9999-4999-8999-999999999999',
    version: 1,
    event: buildGameLifecycleSyncEvent({
      gameId,
      d4,
      d5: '99999999-9999-4999-8999-999999999999',
      d2: 2001,
      payload,
      eventKind: kind,
    }),
    state: queueStateId('未送信'),
  }
}

/**
 * 正本の写しに再開種別がまだ無いため、順序検査のためだけに構造だけを差し込む。
 * 実認可/DB成功の証拠ではなく、正式裁定後に実在する予定の種別である。
 */
function kindForTest(action: 'end' | 'reopen') {
  if (action === 'end') {
    const kind = gameLifecycleEventKind('end')
    if (!kind) throw new Error('終了種別が正本の写しにありません')
    return kind
  }
  return {
    id: '13',
    name: '試合再開',
    participation: '論理位置を持つ',
    hasRevisionOrder: false,
    group: 'A',
  } as never
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('lifecycle read', () => {
  it('lifecycle metadataの無い旧NP readを新縦断の成功にしない', async () => {
    const base = undoRead()
    expect(isGameLifecycleGame(base)).toBe(false)
    vi.spyOn(client, 'apiRequest').mockResolvedValue(base)
    await expect(readGameLifecycle(base.id)).resolves.toEqual({
      kind: 'unsupported',
    })
  })

  it('finishedは最新確定版とactive全3値が同時に揃う場合だけ受理する', () => {
    expect(isGameLifecycleGame(finished())).toBe(true)
    const missingActive: unknown = {
      ...finished(),
      lifecycle: {
        ...finished().lifecycle,
        active: null,
        activeStatsVersionId: null,
      },
    }
    expect(isGameLifecycleGame(missingActive)).toBe(false)
    const versionGap: unknown = {
      ...finished(),
      lifecycle: {
        ...finished().lifecycle,
        active: {
          ...finished().lifecycle.active,
          version: '3',
        },
      },
    }
    expect(isGameLifecycleGame(versionGap)).toBe(false)
    const inProgressWithActive: unknown = {
      ...inProgress(),
      lifecycle: finished().lifecycle,
    }
    expect(isGameLifecycleGame(inProgressWithActive)).toBe(false)
    const statusMismatch: unknown = {
      ...finished(),
      status: 'in_progress',
    }
    expect(isGameLifecycleGame(statusMismatch)).toBe(false)
    expect(isGameLifecycleMeta(finished().lifecycle, 'in_progress')).toBe(false)
  })

  it('projectionとlimitを明示し、404/409/400を成功にしない', async () => {
    const request = vi
      .spyOn(client, 'apiRequest')
      .mockResolvedValueOnce(inProgress())
    await expect(readGameLifecycle(gameId, { limit: 25 })).resolves.toEqual({
      kind: 'found',
      game: inProgress(),
    })
    expect(request).toHaveBeenCalledWith('GET', `/games/${gameId}/started`, {
      tenantBound: true,
      query: { projection: GAME_LIFECYCLE_PROJECTION, limit: 25 },
      signal: undefined,
    })

    request.mockRejectedValueOnce(
      new ApiError(404, 'not found', [], undefined, null),
    )
    await expect(readGameLifecycle(gameId)).resolves.toEqual({
      kind: 'not-found',
    })
    request.mockRejectedValueOnce(
      new ApiError(409, 'conflict', [], undefined, null),
    )
    await expect(readGameLifecycle(gameId)).resolves.toEqual({
      kind: 'unavailable',
    })
    for (const status of [400, 422, 501]) {
      request.mockRejectedValueOnce(
        new ApiError(status, 'unsupported', [], undefined, null),
      )
      await expect(readGameLifecycle(gameId)).resolves.toEqual({
        kind: 'unsupported',
      })
    }
    request.mockRejectedValueOnce(
      new ApiError(500, 'server', [], undefined, null),
    )
    await expect(readGameLifecycle(gameId)).rejects.toBeInstanceOf(ApiError)
  })

  it('別試合IDの応答を受理しない', async () => {
    vi.spyOn(client, 'apiRequest').mockResolvedValue({
      ...inProgress(),
      id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    })
    await expect(readGameLifecycle(gameId)).rejects.toThrow('終了再開の応答')
  })

  it('limit/cursorの不正を送信前に拒む', async () => {
    const request = vi.spyOn(client, 'apiRequest')
    await expect(readGameLifecycle(gameId, { limit: 0 })).rejects.toThrow(
      '読取条件',
    )
    await expect(readGameLifecycle(gameId, { limit: 101 })).rejects.toThrow(
      '読取条件',
    )
    await expect(readGameLifecycle('not-a-uuid')).rejects.toThrow('読取条件')
    await expect(
      readGameLifecycle(gameId, { cursor: 'x'.repeat(2049) }),
    ).rejects.toThrow('読取条件')
    expect(request).not.toHaveBeenCalled()
  })
})

describe('lifecycle payload', () => {
  it('終了はtargetを持たず、再開は最新active全3値を要求する', () => {
    const event = {
      eventId: '77777777-7777-4777-8777-777777777777',
      receiptId: '88888888-8888-4888-8888-888888888888',
    }
    const checkpointRef = {
      id: '66666666-6666-4666-8666-666666666666',
      revision: '2',
      digest: 'b'.repeat(64),
    }
    expect(
      buildGameLifecyclePayload({
        action: 'end',
        checkpointRef,
        target: null,
        event,
      }),
    ).toMatchObject({ action: 'end', target: null })
    expect(() =>
      buildGameLifecyclePayload({
        action: 'end',
        checkpointRef,
        target: {
          version: '1',
          eventId: event.eventId,
          receiptId: event.receiptId,
        },
        event,
      }),
    ).toThrow('end-target')
    expect(() =>
      buildGameLifecyclePayload({
        action: 'reopen',
        checkpointRef,
        target: null,
        event,
      }),
    ).toThrow('reopen-target')
    expect(() =>
      buildGameLifecyclePayload({
        action: 'reopen',
        checkpointRef: { ...checkpointRef, revision: '02' },
        target: {
          version: '1',
          eventId: event.eventId,
          receiptId: event.receiptId,
        },
        event,
      }),
    ).toThrow('invalid-reference')
    expect(() =>
      buildGameLifecyclePayload({
        action: 'reopen',
        checkpointRef: { ...checkpointRef, digest: 'z'.repeat(64) },
        target: {
          version: '1',
          eventId: event.eventId,
          receiptId: event.receiptId,
        },
        event,
      }),
    ).toThrow('invalid-reference')
  })

  it('イベントはV1/V3/V4/V5/V6/V7だけで、V2/V8を持たない', () => {
    const event = slot('end').event
    expect(Object.keys(event.fields).sort()).toEqual([
      'V1',
      'V3',
      'V4',
      'V5',
      'V6',
      'V7',
    ])
    expect(event.fields.V5).toBe('5')
    expect(event.fields.V6).toBe(2001)
  })
})

describe('lifecycle wire rewrite', () => {
  it('終了のordinal 5だけをgame_end_declarationへ写し、他は変えない', () => {
    const built = buildGameLifecycleRequestBody({
      gameId,
      recordingRightProof: proof,
      slot: slot('end'),
      action: 'end',
      eventKind: kindForTest('end'),
    })
    expect(built.ok).toBe(true)
    if (!built.ok) return
    expect(built.body.events[0]).toMatchObject({
      d5: slot().d5,
      d1: 5,
      d4,
      game_id: gameId,
      event_kind: GAME_LIFECYCLE_WIRE_EVENT_KIND.end,
      d2: 2001,
    })
    expect(built.body.events[0]).not.toHaveProperty('state_diff')
    expect(built.body.events[0]).not.toHaveProperty('target_reference')
    expect(built.body.recording_right_proof).toBe(proof)
    // 同じ入力からは同じ本文。送信前の耐久固定と再送で使う。
    expect(
      buildGameLifecycleRequestBody({
        gameId,
        recordingRightProof: proof,
        slot: slot('end'),
        action: 'end',
        eventKind: kindForTest('end'),
      }),
    ).toEqual(built)
  })

  it('再開はgame_reopenへ写すが、種別が未裁定なら閉拒否する', () => {
    expect(gameLifecycleEventKind('reopen')).toBeUndefined()
    const built = buildGameLifecycleRequestBody({
      gameId,
      recordingRightProof: proof,
      slot: slot('reopen'),
      action: 'reopen',
      eventKind: kindForTest('reopen'),
    })
    expect(built.ok).toBe(true)
    if (!built.ok) return
    expect(built.body.events[0]?.event_kind).toBe(
      GAME_LIFECYCLE_WIRE_EVENT_KIND.reopen,
    )
  })

  it('操作と種別の食い違いを写像しない', () => {
    const built = buildGameLifecycleRequestBody({
      gameId,
      recordingRightProof: proof,
      slot: slot('end'),
      action: 'reopen',
      eventKind: kindForTest('reopen'),
    })
    expect(built).toMatchObject({ ok: false, reason: 'kind-mismatch' })
  })

  it('保存済み本文の外形を再送前に検査する', () => {
    const built = buildGameLifecycleRequestBody({
      gameId,
      recordingRightProof: proof,
      slot: slot('end'),
      action: 'end',
      eventKind: kindForTest('end'),
    })
    if (!built.ok) throw new Error('body invalid')
    expect(isGameLifecycleRequestBody(built.body)).toBe(true)
    expect(isGameLifecycleRequestBody({ ...built.body, extra: 1 })).toBe(false)
    expect(
      isGameLifecycleRequestBody({
        recording_right_proof: proof,
        events: [{ ...built.body.events[0], event_kind: 'unknown' }],
      }),
    ).toBe(false)
    expect(
      isGameLifecycleRequestBody({
        recording_right_proof: proof,
        events: [{ ...built.body.events[0], d2: -1 }],
      }),
    ).toBe(false)
    expect(
      isGameLifecycleRequestBody({
        recording_right_proof: '',
        events: built.body.events,
      }),
    ).toBe(false)
  })

  it('POSTは本文を変更せず、通信断/HTTP失敗を送信成功にしない', async () => {
    const built = buildGameLifecycleRequestBody({
      gameId,
      recordingRightProof: proof,
      slot: slot('end'),
      action: 'end',
      eventKind: kindForTest('end'),
    })
    if (!built.ok) throw new Error('body invalid')
    const request = vi
      .spyOn(client, 'apiRequest')
      .mockResolvedValueOnce({ advancedD3: 5, eventResults: [] })
    await expect(
      postGameLifecycleRequestBody(gameId, built.body, {
        deviceId: tenant,
        deviceCredential: 'secret-not-shown',
        attempt: 'abababab-abab-4bab-8bab-abababababab',
      }),
    ).resolves.toMatchObject({ sent: true })
    expect(request).toHaveBeenCalledWith(
      'POST',
      `/games/${gameId}/sync/events`,
      {
        body: built.body,
        syncCredentials: {
          deviceId: tenant,
          deviceCredential: 'secret-not-shown',
          attempt: 'abababab-abab-4bab-8bab-abababababab',
        },
      },
    )
    request.mockRejectedValueOnce(
      new ApiError(503, 'unavailable', [], undefined, null),
    )
    await expect(
      postGameLifecycleRequestBody(gameId, built.body),
    ).resolves.toMatchObject({
      sent: false,
      reason: 'response-not-interpreted',
      status: 503,
    })
    request.mockRejectedValueOnce(new Error('offline'))
    await expect(
      postGameLifecycleRequestBody(gameId, built.body),
    ).resolves.toMatchObject({ sent: false, reason: 'no-response' })
  })
})
