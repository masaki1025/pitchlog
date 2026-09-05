import { describe, expect, it, vi } from 'vitest'
import { readCanonV12BoundaryRules } from './canonOracle'
import type { DurableQueueSlot } from './durableQueue'
import { REQUEST_ONLY_IDS, SYNC_EVENT_PATH } from './eventFieldRules'
import {
  DEFAULT_LOCAL_QUEUE_FILE_CODEC,
  exportLocalQueueFile,
  importLocalQueueFile,
  LOCAL_QUEUE_IMPORT_STATUS,
  LOCAL_QUEUE_V12_BOUNDARY_RULES,
  LocalQueueFileError,
  type LocalQueueFileCodec,
  type LocalQueueFileImportInjections,
} from './localQueueFile'
import {
  REQUEST_BOUNDARY_RESULT,
  type RequestBoundaryEnvelope,
} from './requestBoundary'
import { queueStateId } from './queueState'

const CURRENT_D4 = 'current-generation'
const CURRENT_SCOPE = Object.freeze({ game: 'game-a', d4: CURRENT_D4 })

function queueEvent(
  overrides: Partial<DurableQueueSlot> = {},
): DurableQueueSlot {
  return {
    game: 'game-a',
    d4: CURRENT_D4,
    d1: 1,
    d5: 'event-key-a',
    version: { revision: 1 },
    event: { fields: { V7: { value: 'original' } } },
    state: queueStateId('未送信'),
    ...overrides,
  }
}

function boundaryRequest(): Extract<
  RequestBoundaryEnvelope,
  { p3State?: never }
> {
  const requestOnlyId = REQUEST_ONLY_IDS[0]
  if (!requestOnlyId) {
    throw new Error('要求レベルの識別子がありません')
  }
  return {
    path: SYNC_EVENT_PATH.P1,
    requestValues: { [requestOnlyId]: 'proof' },
    recoveryGenerationAtCreation: 'recovery-generation',
  }
}

function acceptedInjections(
  overrides: Partial<LocalQueueFileImportInjections> = {},
): LocalQueueFileImportInjections {
  return {
    resolveProvenance: () => ({ sameDevice: true, sameBrowser: true }),
    v12Binding: () => true,
    ...overrides,
  }
}

async function exportedText(
  events: readonly DurableQueueSlot[],
  codec: LocalQueueFileCodec = DEFAULT_LOCAL_QUEUE_FILE_CODEC,
): Promise<string> {
  return exportLocalQueueFile(
    {
      schemaVersion: 'schema-v1',
      exportedAt: 'exported-at',
      events,
    },
    { codec },
  )
}

describe('localQueueFile', () => {
  it('X1: 書き出しと読み込みの往復で原形を保ち、D1 採番器を呼ばない', async () => {
    const events = [queueEvent(), queueEvent({ d1: 2, d5: 'event-key-b' })]
    const allocateD1 = vi.fn()
    const writeOutput = vi.fn()
    const codec: LocalQueueFileCodec = {
      encode: vi.fn(DEFAULT_LOCAL_QUEUE_FILE_CODEC.encode),
      decode: vi.fn(DEFAULT_LOCAL_QUEUE_FILE_CODEC.decode),
    }
    const text = await exportLocalQueueFile(
      {
        schemaVersion: 'schema-v1',
        exportedAt: 'exported-at',
        events,
      },
      { codec, allocateD1, writeOutput },
    )
    const result = importLocalQueueFile(
      {
        text,
        currentScope: CURRENT_SCOPE,
        boundaryRequest: boundaryRequest(),
      },
      acceptedInjections({ codec }),
    )

    expect(allocateD1).not.toHaveBeenCalled()
    expect(writeOutput).toHaveBeenCalledOnce()
    expect(codec.encode).toHaveBeenCalledOnce()
    expect(codec.decode).toHaveBeenCalledTimes(2)
    expect(result.status).toBe(LOCAL_QUEUE_IMPORT_STATUS.COMPLETED)
    expect(result.scope).toBe(CURRENT_SCOPE)
    expect(result.importedEvents).toEqual(events)
    expect(result.b4Events).toEqual([])
  })

  it('既定 codec の往復で undefined が失われる場合は出力を生成しない', async () => {
    const writeOutput = vi.fn()
    const event = queueEvent({
      event: { fields: { V7: { value: undefined } } },
    })

    await expect(
      exportLocalQueueFile(
        {
          schemaVersion: 'schema-v1',
          exportedAt: 'exported-at',
          events: [event],
        },
        { writeOutput },
      ),
    ).rejects.toBeInstanceOf(LocalQueueFileError)
    expect(writeOutput).not.toHaveBeenCalled()
  })

  it('X2: 同一 D5 でも内容と版が異なるイベントを原形のまま取り込む', async () => {
    const first = queueEvent({
      d1: 99,
      d5: 'same-key',
      version: { source: 'first' },
      event: { fields: { V7: { source: 'first' } } },
    })
    const second = queueEvent({
      d1: 100,
      d5: 'same-key',
      version: { source: 'second' },
      event: { fields: { V7: { source: 'second' } } },
    })
    const text = await exportedText([first, second])

    const result = importLocalQueueFile(
      {
        text,
        currentScope: CURRENT_SCOPE,
        boundaryRequest: boundaryRequest(),
      },
      acceptedInjections(),
    )

    expect(result.importedEvents).toEqual([first, second])
    expect(Reflect.ownKeys(result)).toEqual([
      'status',
      'scope',
      'importedEvents',
      'b4Events',
      'notImportedEvents',
    ])
  })

  it('R-V12-BOUNDARY の VF1・VF4 だけを逐語で読む', () => {
    const expectedRules = readCanonV12BoundaryRules().filter((rule) =>
      new Set(['VF1', 'VF4']).has(rule.id),
    )

    expect(LOCAL_QUEUE_V12_BOUNDARY_RULES).toHaveLength(2)
    expect(LOCAL_QUEUE_V12_BOUNDARY_RULES).toEqual(expectedRules)
    expect(LOCAL_QUEUE_V12_BOUNDARY_RULES.map((rule) => rule.id)).toEqual([
      'VF1',
      'VF4',
    ])
  })

  it('X3: 旧世代 D4 の要素を B4 として退避状態にする', async () => {
    const event = queueEvent({ d4: 'old-generation' })
    const text = await exportedText([event])
    const result = importLocalQueueFile(
      {
        text,
        currentScope: CURRENT_SCOPE,
        boundaryRequest: boundaryRequest(),
      },
      acceptedInjections(),
    )

    expect(result.importedEvents).toEqual([])
    expect(result.b4Events).toEqual([
      {
        result: REQUEST_BOUNDARY_RESULT.B4,
        event: { ...event, state: queueStateId('退避済み') },
      },
    ])
  })

  it('X3: 記録権 verifier が不成立なら B4 として退避状態にする', async () => {
    const event = queueEvent()
    const text = await exportedText([event])
    const result = importLocalQueueFile(
      {
        text,
        currentScope: CURRENT_SCOPE,
        boundaryRequest: boundaryRequest(),
      },
      acceptedInjections({ v12Binding: () => false }),
    )

    expect(result.importedEvents).toEqual([])
    expect(result.b4Events).toEqual([
      {
        result: REQUEST_BOUNDARY_RESULT.B4,
        event: { ...event, state: queueStateId('退避済み') },
      },
    ])
  })

  it('X3: 別試合のイベントには現試合の境界検証結果を使わない', async () => {
    const event = queueEvent({ game: 'game-b' })
    const text = await exportedText([event])
    const v12Binding = vi.fn(() => true)
    const result = importLocalQueueFile(
      {
        text,
        currentScope: CURRENT_SCOPE,
        boundaryRequest: boundaryRequest(),
      },
      acceptedInjections({ v12Binding }),
    )

    expect(v12Binding).toHaveBeenCalledWith(
      expect.objectContaining({ scope: CURRENT_SCOPE }),
    )
    expect(result.importedEvents).toEqual([])
    expect(result.b4Events).toEqual([
      {
        result: REQUEST_BOUNDARY_RESULT.B4,
        event: { ...event, state: queueStateId('退避済み') },
      },
    ])
  })

  it.each([
    ['試合', { game: 'game-b', d1: 2 }],
    ['D4', { d4: 'another-generation', d1: 2 }],
  ] as const)(
    'X3: 複数の %s スコープが混在するファイルを拒否する',
    async (_name, overrides) => {
      const text = await exportedText([queueEvent(), queueEvent(overrides)])

      expect(() =>
        importLocalQueueFile(
          {
            text,
            currentScope: CURRENT_SCOPE,
            boundaryRequest: boundaryRequest(),
          },
          acceptedInjections(),
        ),
      ).toThrowError(LocalQueueFileError)
    },
  )

  it.each([
    [
      '別ブラウザ',
      { resolveProvenance: () => ({ sameDevice: true, sameBrowser: false }) },
    ],
    ['provenance 未注入', {}],
  ] as const)(
    'X4: %sなら保証対象外として読み込まない',
    async (_name, injections) => {
      const event = queueEvent()
      const text = await exportedText([event])
      const result = importLocalQueueFile(
        {
          text,
          currentScope: CURRENT_SCOPE,
          boundaryRequest: boundaryRequest(),
        },
        { v12Binding: () => true, ...injections },
      )

      expect(result).toEqual({
        status: LOCAL_QUEUE_IMPORT_STATUS.OUTSIDE_GUARANTEE,
        scope: CURRENT_SCOPE,
        importedEvents: [],
        b4Events: [],
        notImportedEvents: [],
      })
    },
  )

  it('既に退避状態の要素を未送信へ戻さない', async () => {
    const event = queueEvent({ state: queueStateId('退避済み') })
    const text = await exportedText([event])
    const result = importLocalQueueFile(
      {
        text,
        currentScope: CURRENT_SCOPE,
        boundaryRequest: boundaryRequest(),
      },
      acceptedInjections(),
    )

    expect(result.importedEvents).toEqual([])
    expect(result.notImportedEvents).toEqual([event])
    expect(result.b4Events).toEqual([])
  })
})
