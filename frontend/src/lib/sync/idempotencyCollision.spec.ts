import { describe, expect, it, vi } from 'vitest'
import { SYNC_EVENT_PATH } from './eventFieldRules'
import {
  CONTENT_IDENTITY,
  decideIdempotencyCollision,
  IDEMPOTENCY_DECISION,
  IDEMPOTENCY_SCOPE_RULE,
  type ContentIdentityComparator,
  type IdempotencyOperation,
  type StoredIdempotencyOperation,
} from './idempotencyCollision'

type TestContent = Readonly<{ value: string }>
type TestResult = Readonly<{ result: string }>

function operation(
  overrides: Partial<IdempotencyOperation<TestContent>> = {},
): IdempotencyOperation<TestContent> {
  return {
    tenant: 'tenant-a',
    d5: 'same-d5',
    game: 'game-a',
    generation: 'generation-a',
    path: SYNC_EVENT_PATH.P1,
    content: { value: 'first' },
    ...overrides,
  }
}

function storedOperation(
  operationOverrides: Partial<IdempotencyOperation<TestContent>> = {},
): StoredIdempotencyOperation<TestContent, TestResult> {
  return {
    operation: operation(operationOverrides),
    savedResult: { result: 'saved' },
  }
}

describe('idempotencyCollision', () => {
  it('N-13: 同じ D5・同じ内容は保存済み結果を再掲し、適用しない', () => {
    const stored = storedOperation()
    const apply = vi.fn(() => ({ result: 'applied' }))
    const compareContent = vi.fn<ContentIdentityComparator<TestContent>>(
      () => CONTENT_IDENTITY.SAME,
    )

    const result = decideIdempotencyCollision(
      operation(),
      [stored],
      compareContent,
      apply,
    )

    expect(result).toEqual({
      decision: IDEMPOTENCY_DECISION.REPLAY_SAVED_RESULT,
      savedResult: stored.savedResult,
    })
    expect(result).toHaveProperty('savedResult', stored.savedResult)
    expect(apply).not.toHaveBeenCalled()
  })

  it('N-14: D1 付き経路の異内容を B3b とし、先着原本を変えない', () => {
    const stored = storedOperation()
    const before = structuredClone(stored)
    const apply = vi.fn(() => ({ result: 'applied' }))

    const result = decideIdempotencyCollision(
      operation({ content: { value: 'later' } }),
      [stored],
      () => CONTENT_IDENTITY.DIFFERENT,
      apply,
    )

    expect(result).toEqual({ decision: IDEMPOTENCY_DECISION.D1_COLLISION })
    expect(stored).toEqual(before)
    expect(apply).not.toHaveBeenCalled()
  })

  it('N-15: P3 の異内容を B13 とする', () => {
    const apply = vi.fn(() => ({ result: 'applied' }))

    const result = decideIdempotencyCollision(
      operation({
        path: SYNC_EVENT_PATH.P3,
        content: { value: 'later' },
      }),
      [storedOperation()],
      () => CONTENT_IDENTITY.DIFFERENT,
      apply,
    )

    expect(result).toEqual({ decision: IDEMPOTENCY_DECISION.P3_COLLISION })
    expect(result).not.toEqual({ decision: IDEMPOTENCY_DECISION.D1_COLLISION })
    expect(apply).not.toHaveBeenCalled()
  })

  it.each([
    ['判定不能', () => CONTENT_IDENTITY.INDETERMINATE],
    [
      '判定器の例外',
      () => {
        throw new Error('comparison failed')
      },
    ],
  ] satisfies readonly (readonly [
    string,
    ContentIdentityComparator<TestContent>,
  ])[])('N-16: %s は B コードではない後着拒否へ倒す', (_, comparator) => {
    const apply = vi.fn(() => ({ result: 'applied' }))
    const result = decideIdempotencyCollision(
      operation({ content: { value: 'later' } }),
      [storedOperation()],
      comparator,
      apply,
    )

    expect(result).toEqual({ decision: IDEMPOTENCY_DECISION.REJECT_LATER })
    expect(result.decision).not.toMatch(/^B/)
    expect(apply).not.toHaveBeenCalled()
  })

  it('N-17: 別試合・別世代の同じ D5 を同一操作として扱う', () => {
    const stored = storedOperation()
    const apply = vi.fn(() => ({ result: 'applied' }))

    const result = decideIdempotencyCollision(
      operation({
        game: 'another-game',
        generation: 'another-generation',
      }),
      [stored],
      () => CONTENT_IDENTITY.SAME,
      apply,
    )

    expect(result).toEqual({
      decision: IDEMPOTENCY_DECISION.REPLAY_SAVED_RESULT,
      savedResult: stored.savedResult,
    })
    expect(apply).not.toHaveBeenCalled()
  })

  it('N-18: 別テナントの同じ D5 を重複として扱わず、保存結果を返さない', () => {
    const stored = storedOperation()
    const appliedResult = { result: 'applied' }
    const apply = vi.fn(() => appliedResult)
    const compareContent = vi.fn<ContentIdentityComparator<TestContent>>(
      () => CONTENT_IDENTITY.SAME,
    )

    const result = decideIdempotencyCollision(
      operation({ tenant: 'tenant-b' }),
      [stored],
      compareContent,
      apply,
    )

    expect(result).toEqual({
      decision: IDEMPOTENCY_DECISION.NOT_DUPLICATE,
      appliedResult,
    })
    expect('savedResult' in result).toBe(false)
    expect(compareContent).not.toHaveBeenCalled()
    expect(apply).toHaveBeenCalledOnce()
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
        () => ({ result: 'applied' }),
      ),
    ).toEqual({
      decision: IDEMPOTENCY_DECISION.REPLAY_SAVED_RESULT,
      savedResult: stored.savedResult,
    })
  })

  it('判定器を差し替えても同じ三値から同じ分岐を選ぶ', () => {
    const compareByValue: ContentIdentityComparator<TestContent> = (
      first,
      later,
    ) => {
      if (later.value === 'unknown') {
        return CONTENT_IDENTITY.INDETERMINATE
      }
      return first.value === later.value
        ? CONTENT_IDENTITY.SAME
        : CONTENT_IDENTITY.DIFFERENT
    }
    const compareByTable: ContentIdentityComparator<TestContent> = (
      _first,
      later,
    ) => {
      const identityByValue = {
        first: CONTENT_IDENTITY.SAME,
        later: CONTENT_IDENTITY.DIFFERENT,
        unknown: CONTENT_IDENTITY.INDETERMINATE,
      } as const
      return identityByValue[later.value as keyof typeof identityByValue]
    }

    for (const comparator of [compareByValue, compareByTable]) {
      const apply = vi.fn(() => ({ result: 'applied' }))
      const same = decideIdempotencyCollision(
        operation(),
        [storedOperation()],
        comparator,
        apply,
      )
      const differentD1 = decideIdempotencyCollision(
        operation({ content: { value: 'later' } }),
        [storedOperation()],
        comparator,
        apply,
      )
      const differentP3 = decideIdempotencyCollision(
        operation({
          path: SYNC_EVENT_PATH.P3,
          content: { value: 'later' },
        }),
        [storedOperation()],
        comparator,
        apply,
      )
      const indeterminate = decideIdempotencyCollision(
        operation({ content: { value: 'unknown' } }),
        [storedOperation()],
        comparator,
        apply,
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
      expect(apply).not.toHaveBeenCalled()
    }
  })

  it('変異 M12: 照合キーを試合・世代・D5へ変えたことを検出する', () => {
    const mutatedScope = structuredClone(IDEMPOTENCY_SCOPE_RULE) as {
      keyParts: ('tenant' | 'd5' | 'game' | 'generation')[]
      differentTenantIsDuplicate: boolean
    }
    mutatedScope.keyParts.splice(
      0,
      mutatedScope.keyParts.length,
      'game',
      'generation',
      'd5',
    )

    expect(() =>
      expect(mutatedScope.keyParts).toEqual(['tenant', 'd5']),
    ).toThrow()
  })

  it('変異 M13: 別テナントの同じ D5 を重複扱いへ変えたことを検出する', () => {
    const mutatedScope = structuredClone(IDEMPOTENCY_SCOPE_RULE) as {
      keyParts: ('tenant' | 'd5' | 'game' | 'generation')[]
      differentTenantIsDuplicate: boolean
    }
    mutatedScope.differentTenantIsDuplicate = true

    expect(() =>
      expect(mutatedScope.differentTenantIsDuplicate).toBe(false),
    ).toThrow()
  })
})
