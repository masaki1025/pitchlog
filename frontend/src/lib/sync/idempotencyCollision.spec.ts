import { describe, expect, it, vi } from 'vitest'
import { SYNC_EVENT_PATH } from './eventFieldRules'
import type { EventKindId } from './eventKinds'
import {
  CONTENT_IDENTITY,
  decideIdempotencyCollision,
  IDEMPOTENCY_DECISION,
  IDEMPOTENCY_SCOPE_RULE,
  type IdempotencyEventOriginal,
  type IdempotencyOperation,
  type IdempotencyOriginal,
  type IdempotencyOriginalComparator,
  type StoredIdempotencyOperation,
} from './idempotencyCollision'
import idempotencyCollisionSource from './idempotencyCollision.ts?raw'

type TestResult = Readonly<{ result: string }>

function eventOriginal(
  value = 'first',
  kind: EventKindId = '1',
): IdempotencyEventOriginal {
  return {
    fields: {
      V1: 'same-d5',
      V2: 'd1',
      V3: 'generation-a',
      V4: 'game-a',
      V5: kind,
      V6: 'position',
      V7: { value },
      V8: {},
    },
  }
}

function original(
  overrides: Partial<IdempotencyOriginal> = {},
): IdempotencyOriginal {
  return {
    game: 'game-a',
    recordingRightsGeneration: 'generation-a',
    path: SYNC_EVENT_PATH.P1,
    event: eventOriginal(),
    ...overrides,
  }
}

function operation(
  overrides: Partial<Omit<IdempotencyOperation, 'original'>> = {},
  originalOverrides: Partial<IdempotencyOriginal> = {},
): IdempotencyOperation {
  return {
    tenant: 'tenant-a',
    d5: 'same-d5',
    original: original(originalOverrides),
    ...overrides,
  }
}

function storedOperation(
  operationOverrides: Partial<Omit<IdempotencyOperation, 'original'>> = {},
  originalOverrides: Partial<IdempotencyOriginal> = {},
): StoredIdempotencyOperation<TestResult> {
  return {
    operation: operation(operationOverrides, originalOverrides),
    savedResult: { result: 'saved' },
  }
}

function eventValue(originalValue: IdempotencyOriginal): unknown {
  return (originalValue.event.fields.V7 as { value: unknown }).value
}

describe('idempotencyCollision', () => {
  it('N-13: 同じ D5・同じ原本は保存済み結果を再掲する', () => {
    const stored = storedOperation()
    const compareOriginal = vi.fn<IdempotencyOriginalComparator>(
      () => CONTENT_IDENTITY.SAME,
    )
    const later = operation()

    const result = decideIdempotencyCollision(later, [stored], compareOriginal)

    expect(result).toEqual({
      decision: IDEMPOTENCY_DECISION.REPLAY_SAVED_RESULT,
      savedResult: stored.savedResult,
    })
    expect(compareOriginal).toHaveBeenCalledWith(
      stored.operation.original,
      later.original,
    )
  })

  it('N-14: D1 付き経路の異内容を B3b とし、先着原本を変えない', () => {
    const stored = storedOperation()
    const before = structuredClone(stored)

    const result = decideIdempotencyCollision(
      operation({}, { event: eventOriginal('later') }),
      [stored],
      () => CONTENT_IDENTITY.DIFFERENT,
    )

    expect(result).toEqual({ decision: IDEMPOTENCY_DECISION.D1_COLLISION })
    expect(stored).toEqual(before)
  })

  it('N-15: P3 の異内容を B13 とする', () => {
    const result = decideIdempotencyCollision(
      operation(
        {},
        {
          path: SYNC_EVENT_PATH.P3,
          event: eventOriginal('later', '10'),
        },
      ),
      [storedOperation()],
      () => CONTENT_IDENTITY.DIFFERENT,
    )

    expect(result).toEqual({ decision: IDEMPOTENCY_DECISION.P3_COLLISION })
    expect(result).not.toEqual({ decision: IDEMPOTENCY_DECISION.D1_COLLISION })
  })

  it.each([
    ['判定不能', () => CONTENT_IDENTITY.INDETERMINATE],
    [
      '判定器の例外',
      () => {
        throw new Error('comparison failed')
      },
    ],
  ] satisfies readonly (readonly [string, IdempotencyOriginalComparator])[])(
    'N-16: %s は B コードではない後着拒否へ倒す',
    (_, comparator) => {
      const result = decideIdempotencyCollision(
        operation({}, { event: eventOriginal('later') }),
        [storedOperation()],
        comparator,
      )

      expect(result).toEqual({ decision: IDEMPOTENCY_DECISION.REJECT_LATER })
      expect(result.decision).not.toMatch(/^B/)
    },
  )

  it('N-17a: 別試合・別世代でも同じテナント・D5を候補として見つける', () => {
    const stored = storedOperation()
    const later = operation(
      {},
      {
        game: 'another-game',
        recordingRightsGeneration: 'another-generation',
      },
    )
    const compareOriginal = vi.fn<IdempotencyOriginalComparator>(
      () => CONTENT_IDENTITY.DIFFERENT,
    )

    expect(
      decideIdempotencyCollision(later, [stored], compareOriginal),
    ).toEqual({ decision: IDEMPOTENCY_DECISION.D1_COLLISION })
    expect(compareOriginal).toHaveBeenCalledWith(
      stored.operation.original,
      later.original,
    )
  })

  it.each([
    [SYNC_EVENT_PATH.P1, IDEMPOTENCY_DECISION.D1_COLLISION],
    [SYNC_EVENT_PATH.P3, IDEMPOTENCY_DECISION.P3_COLLISION],
  ] as const)(
    'N-17b: 原本の試合・世代が違う %s を異内容として扱う',
    (path, expectedDecision) => {
      const compareOriginal: IdempotencyOriginalComparator = (first, later) =>
        Object.is(first.game, later.game) &&
        Object.is(
          first.recordingRightsGeneration,
          later.recordingRightsGeneration,
        )
          ? CONTENT_IDENTITY.SAME
          : CONTENT_IDENTITY.DIFFERENT
      const result = decideIdempotencyCollision(
        operation(
          {},
          {
            game: 'another-game',
            recordingRightsGeneration: 'another-generation',
            path,
          },
        ),
        [storedOperation()],
        compareOriginal,
      )

      expect(result).toEqual({ decision: expectedDecision })
    },
  )

  it('N-18: 別テナントの同じ D5 を重複として扱わず、保存結果を返さない', () => {
    const compareOriginal = vi.fn<IdempotencyOriginalComparator>(
      () => CONTENT_IDENTITY.SAME,
    )

    const result = decideIdempotencyCollision(
      operation({ tenant: 'tenant-b' }),
      [storedOperation()],
      compareOriginal,
    )

    expect(result).toEqual({ decision: IDEMPOTENCY_DECISION.NOT_DUPLICATE })
    expect('savedResult' in result).toBe(false)
    expect(compareOriginal).not.toHaveBeenCalled()
  })

  it.each([
    ['', ''],
    [0, 0],
    [null, null],
  ])('D5 の値形式を検査しない', (firstD5, laterD5) => {
    const stored = storedOperation({ d5: firstD5 })

    expect(
      decideIdempotencyCollision(
        operation({ d5: laterD5 }),
        [stored],
        () => CONTENT_IDENTITY.SAME,
      ),
    ).toEqual({
      decision: IDEMPOTENCY_DECISION.REPLAY_SAVED_RESULT,
      savedResult: stored.savedResult,
    })
  })

  it('判定器へ試合・世代・経路・種別を含む全イベント値を渡す', () => {
    const stored = storedOperation()
    const later = operation({}, { event: eventOriginal('later', '3') })
    const compareOriginal = vi.fn<IdempotencyOriginalComparator>(
      () => CONTENT_IDENTITY.DIFFERENT,
    )

    decideIdempotencyCollision(later, [stored], compareOriginal)

    const [firstArgument, laterArgument] = compareOriginal.mock.calls[0]!
    expect(firstArgument).toBe(stored.operation.original)
    expect(laterArgument).toBe(later.original)
    expect(firstArgument).toHaveProperty('game')
    expect(firstArgument).toHaveProperty('recordingRightsGeneration')
    expect(firstArgument).toHaveProperty('path')
    expect(firstArgument.event.fields).toEqual(
      stored.operation.original.event.fields,
    )
    expect(laterArgument.event.fields.V5).toBe('3')
  })

  it('判定器を差し替えても同じ三値から同じ分岐を選ぶ', () => {
    const compareByValue: IdempotencyOriginalComparator = (first, later) => {
      if (eventValue(later) === 'unknown') {
        return CONTENT_IDENTITY.INDETERMINATE
      }
      return eventValue(first) === eventValue(later)
        ? CONTENT_IDENTITY.SAME
        : CONTENT_IDENTITY.DIFFERENT
    }
    const compareByTable: IdempotencyOriginalComparator = (_first, later) => {
      const identityByValue = {
        first: CONTENT_IDENTITY.SAME,
        later: CONTENT_IDENTITY.DIFFERENT,
        unknown: CONTENT_IDENTITY.INDETERMINATE,
      } as const
      return identityByValue[eventValue(later) as keyof typeof identityByValue]
    }

    for (const comparator of [compareByValue, compareByTable]) {
      const same = decideIdempotencyCollision(
        operation(),
        [storedOperation()],
        comparator,
      )
      const differentD1 = decideIdempotencyCollision(
        operation({}, { event: eventOriginal('later') }),
        [storedOperation()],
        comparator,
      )
      const differentP3 = decideIdempotencyCollision(
        operation(
          {},
          {
            path: SYNC_EVENT_PATH.P3,
            event: eventOriginal('later', '10'),
          },
        ),
        [storedOperation()],
        comparator,
      )
      const indeterminate = decideIdempotencyCollision(
        operation({}, { event: eventOriginal('unknown') }),
        [storedOperation()],
        comparator,
      )

      expect([
        same.decision,
        differentD1.decision,
        differentP3.decision,
        indeterminate.decision,
      ]).toEqual([
        IDEMPOTENCY_DECISION.REPLAY_SAVED_RESULT,
        IDEMPOTENCY_DECISION.D1_COLLISION,
        IDEMPOTENCY_DECISION.P3_COLLISION,
        IDEMPOTENCY_DECISION.REJECT_LATER,
      ])
    }
  })

  it('未使用 D5 は後段検査対象と分類するだけで適用を行わない', () => {
    const compareOriginal = vi.fn<IdempotencyOriginalComparator>()

    expect(
      decideIdempotencyCollision(operation(), [], compareOriginal),
    ).toEqual({ decision: IDEMPOTENCY_DECISION.NOT_DUPLICATE })
    expect(compareOriginal).not.toHaveBeenCalled()
    expect(decideIdempotencyCollision).toHaveLength(3)
    expect(idempotencyCollisionSource).not.toMatch(/\bapply\b|AppliedResult/)
  })

  it('変異 M12: 照合キーを試合・世代・D5へ変えたことを検出する', () => {
    const mutatedScope = structuredClone(IDEMPOTENCY_SCOPE_RULE) as {
      keyParts: string[]
      differentTenantIsDuplicate: boolean
    }
    mutatedScope.keyParts.splice(
      0,
      mutatedScope.keyParts.length,
      'game',
      'recordingRightsGeneration',
      'd5',
    )

    expect(() =>
      expect(mutatedScope.keyParts).toEqual(['tenant', 'd5']),
    ).toThrow()
  })

  it('変異 M13: 別テナントの同じ D5 を重複扱いへ変えたことを検出する', () => {
    const mutatedScope = structuredClone(IDEMPOTENCY_SCOPE_RULE) as {
      keyParts: string[]
      differentTenantIsDuplicate: boolean
    }
    mutatedScope.differentTenantIsDuplicate = true

    expect(() =>
      expect(mutatedScope.differentTenantIsDuplicate).toBe(false),
    ).toThrow()
  })
})
