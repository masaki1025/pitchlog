import { afterEach, describe, expect, it, vi } from 'vitest'
import singleWriterSource from './singleWriter.ts?raw'
import {
  NON_OWNER_INPUT_REASON,
  rejectNonOwnerInput,
  runAsSingleWriter,
  SINGLE_WRITER_PRECONDITION_IDS,
  SINGLE_WRITER_START_FAILURE,
  singleWriterLockName,
  type ExclusiveLockManager,
  type SingleWriterPreconditionId,
  type SingleWriterPreconditions,
} from './singleWriter'

const CONFIRMED_PRECONDITIONS: SingleWriterPreconditions = {
  topLevelHttps: true,
  sameBrowserProfile: true,
  sameBrowsingMode: true,
  sameStorageBucket: true,
  siteStorageAvailable: true,
  lockdownModeNotApplied: true,
}

type Deferred = Readonly<{
  promise: Promise<void>
  resolve: () => void
}>

function deferred(): Deferred {
  let resolvePromise: (() => void) | undefined
  const promise = new Promise<void>((resolve) => {
    resolvePromise = resolve
  })
  if (!resolvePromise) {
    throw new Error('待機制御を初期化できません')
  }
  return { promise, resolve: resolvePromise }
}

class MockExclusiveLockManager implements ExclusiveLockManager {
  readonly requestCalls: { name: string; argumentCount: number }[] = []
  readonly #tails = new Map<string, Promise<void>>()

  async request<Result>(
    name: string,
    callback: (lock: unknown) => Result | PromiseLike<Result>,
  ): Promise<Result> {
    this.requestCalls.push({ name, argumentCount: arguments.length })
    const predecessor = this.#tails.get(name) ?? Promise.resolve()
    let release: (() => void) | undefined
    const turn = new Promise<void>((resolve) => {
      release = resolve
    })
    this.#tails.set(name, turn)

    await predecessor
    try {
      return await callback({ name })
    } finally {
      release?.()
      if (this.#tails.get(name) === turn) {
        this.#tails.delete(name)
      }
    }
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function confirmedInjections(lockManager: ExclusiveLockManager) {
  return {
    lockManager,
    resolvePreconditions: () => CONFIRMED_PRECONDITIONS,
    revalidateSingleWriter: () => true,
  }
}

describe('singleWriter', () => {
  it('ロック要求に禁止オプションを渡さない', async () => {
    const lockManager = new MockExclusiveLockManager()

    await runAsSingleWriter(
      { gameIdentifier: 'game-a' },
      () => undefined,
      confirmedInjections(lockManager),
    )

    expect(singleWriterSource).not.toContain('steal')
    expect(singleWriterSource).not.toContain('ifAvailable')
    expect(lockManager.requestCalls).toEqual([
      { name: singleWriterLockName('game-a'), argumentCount: 2 },
    ])
  })

  it('同じ試合の後発コンテキストを待機させ、先発の解放後に取得する', async () => {
    const lockManager = new MockExclusiveLockManager()
    const firstStarted = deferred()
    const releaseFirst = deferred()
    const secondOperation = vi.fn(() => 'second-completed')
    const invocationOrder: string[] = []

    const first = runAsSingleWriter(
      { gameIdentifier: 'same-game' },
      async () => {
        invocationOrder.push('first-started')
        firstStarted.resolve()
        await releaseFirst.promise
        invocationOrder.push('first-released')
        return 'first-completed'
      },
      confirmedInjections(lockManager),
    )
    await firstStarted.promise
    const second = runAsSingleWriter(
      { gameIdentifier: 'same-game' },
      () => {
        invocationOrder.push('second-started')
        return secondOperation()
      },
      confirmedInjections(lockManager),
    )
    await Promise.resolve()

    expect(secondOperation).not.toHaveBeenCalled()
    releaseFirst.resolve()
    const [firstResult, secondResult] = await Promise.all([first, second])

    expect(firstResult).toEqual({
      recordingStarted: true,
      value: 'first-completed',
    })
    expect(secondResult).toEqual({
      recordingStarted: true,
      value: 'second-completed',
    })
    expect(invocationOrder).toEqual([
      'first-started',
      'first-released',
      'second-started',
    ])
  })

  it('別の試合は競合せず同時に取得できる', async () => {
    const lockManager = new MockExclusiveLockManager()
    const bothStarted = deferred()
    const releaseBoth = deferred()
    let activeOperations = 0
    let maximumActiveOperations = 0

    const operation = async () => {
      activeOperations += 1
      maximumActiveOperations = Math.max(
        maximumActiveOperations,
        activeOperations,
      )
      if (activeOperations === 2) {
        bothStarted.resolve()
      }
      await releaseBoth.promise
      activeOperations -= 1
    }

    const first = runAsSingleWriter(
      { gameIdentifier: 'game-a' },
      operation,
      confirmedInjections(lockManager),
    )
    const second = runAsSingleWriter(
      { gameIdentifier: 'game-b' },
      operation,
      confirmedInjections(lockManager),
    )

    await bothStarted.promise
    expect(maximumActiveOperations).toBe(2)
    releaseBoth.resolve()
    await Promise.all([first, second])
  })

  it('取得後の再検証器が未注入なら記録を開始しない', async () => {
    const operation = vi.fn()
    const result = await runAsSingleWriter(
      { gameIdentifier: 'game-a' },
      operation,
      {
        lockManager: new MockExclusiveLockManager(),
        resolvePreconditions: () => CONFIRMED_PRECONDITIONS,
      },
    )

    expect(result).toEqual({
      recordingStarted: false,
      reason: SINGLE_WRITER_START_FAILURE.REVALIDATION_FAILED,
    })
    expect(operation).not.toHaveBeenCalled()
  })

  it('ロック取得後に再検証し、その成立後にだけ記録を開始する', async () => {
    const invocationOrder: string[] = []
    const lockManager: ExclusiveLockManager = {
      request: async (_name, callback) => {
        invocationOrder.push('lock-acquired')
        return callback({ held: true })
      },
    }

    const result = await runAsSingleWriter(
      { gameIdentifier: 'game-a' },
      () => {
        invocationOrder.push('recording-started')
        return 'completed'
      },
      {
        lockManager,
        resolvePreconditions: () => CONFIRMED_PRECONDITIONS,
        revalidateSingleWriter: () => {
          invocationOrder.push('revalidated')
          return true
        },
      },
    )

    expect(result).toEqual({ recordingStarted: true, value: 'completed' })
    expect(invocationOrder).toEqual([
      'lock-acquired',
      'revalidated',
      'recording-started',
    ])
  })

  it('取得後の再検証呼び出しを削ると検出し、失敗時はロックを解放する', async () => {
    const lockManager = new MockExclusiveLockManager()
    const revalidateSingleWriter = vi
      .fn()
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true)
    const rejectedOperation = vi.fn()

    const rejected = await runAsSingleWriter(
      { gameIdentifier: 'game-a' },
      rejectedOperation,
      {
        lockManager,
        resolvePreconditions: () => CONFIRMED_PRECONDITIONS,
        revalidateSingleWriter,
      },
    )
    const accepted = await runAsSingleWriter(
      { gameIdentifier: 'game-a' },
      () => 'accepted',
      {
        lockManager,
        resolvePreconditions: () => CONFIRMED_PRECONDITIONS,
        revalidateSingleWriter,
      },
    )

    expect(revalidateSingleWriter).toHaveBeenCalledTimes(2)
    expect(rejectedOperation).not.toHaveBeenCalled()
    expect(rejected.recordingStarted).toBe(false)
    expect(accepted).toEqual({ recordingStarted: true, value: 'accepted' })
  })

  const failedPreconditionCases = [
    ['未注入', undefined],
    ...SINGLE_WRITER_PRECONDITION_IDS.map(
      (id) =>
        [
          id,
          {
            ...CONFIRMED_PRECONDITIONS,
            [id]: false,
          },
        ] as const,
    ),
  ] as const

  it.each(failedPreconditionCases)(
    '6 前提の %s が不成立なら fail-closed にする',
    async (_name, preconditions) => {
      const lockManager = new MockExclusiveLockManager()
      const operation = vi.fn()
      const result = await runAsSingleWriter(
        { gameIdentifier: 'game-a' },
        operation,
        {
          lockManager,
          ...(preconditions
            ? { resolvePreconditions: () => preconditions }
            : {}),
          revalidateSingleWriter: () => true,
        },
      )

      expect(result).toEqual({
        recordingStarted: false,
        reason: SINGLE_WRITER_START_FAILURE.PRECONDITIONS_NOT_CONFIRMED,
      })
      expect(operation).not.toHaveBeenCalled()
      expect(lockManager.requestCalls).toEqual([])
    },
  )

  it('6 前提を過不足なく定義する', () => {
    const expectedIds: readonly SingleWriterPreconditionId[] = [
      'topLevelHttps',
      'sameBrowserProfile',
      'sameBrowsingMode',
      'sameStorageBucket',
      'siteStorageAvailable',
      'lockdownModeNotApplied',
    ]

    expect(failedPreconditionCases).toHaveLength(7)
    expect(SINGLE_WRITER_PRECONDITION_IDS).toHaveLength(6)
    expect(new Set(SINGLE_WRITER_PRECONDITION_IDS)).toEqual(
      new Set(expectedIds),
    )
  })

  it('navigator.locks が無い環境では記録を開始しない', async () => {
    vi.stubGlobal('navigator', {})
    const operation = vi.fn()

    const result = await runAsSingleWriter(
      { gameIdentifier: 'game-a' },
      operation,
      {
        resolvePreconditions: () => CONFIRMED_PRECONDITIONS,
        revalidateSingleWriter: () => true,
      },
    )

    expect(result).toEqual({
      recordingStarted: false,
      reason: SINGLE_WRITER_START_FAILURE.LOCK_MANAGER_UNAVAILABLE,
    })
    expect(operation).not.toHaveBeenCalled()
  })

  it('非所有タブの入力を未受理として拒否し、Q2-b の記述子を返す', () => {
    const rejection = rejectNonOwnerInput()

    expect(rejection).toEqual({
      accepted: false,
      reason: NON_OWNER_INPUT_REASON.NOT_ACCEPTED,
      notice: { noticeId: 'Q2-b', params: {} },
    })
    expect(rejection.reason).toBe('受理していない')
    expect(rejection.reason).not.toBe(
      NON_OWNER_INPUT_REASON.ACCEPTED_OPERATION_LOST,
    )
    expect(NON_OWNER_INPUT_REASON.ACCEPTED_OPERATION_LOST).not.toBe(
      NON_OWNER_INPUT_REASON.NOT_ACCEPTED,
    )
  })
})
