import { describe, expect, it } from 'vitest'
import p3ResultSource from './p3Result.ts?raw'
import {
  readCanonP3BoundaryResults,
  type CanonP3BoundaryResult,
} from './canonOracle'
import {
  parseP3ResultEnvelope,
  type P3AcceptedResultEnvelope,
  type P3RejectedResultEnvelope,
} from './p3Result'
import type { I6Acceptance, I6AcceptedResult } from './queueState'
import {
  TARGET_EVENT_REFERENCE_ELEMENTS,
  type TargetEventReference,
} from './syncEvent'

const P3_BOUNDARY_RESULTS = readCanonP3BoundaryResults()
type AcceptedBoundaryResult = Extract<CanonP3BoundaryResult, { accepted: true }>
type RejectedBoundaryResult = Extract<
  CanonP3BoundaryResult,
  { accepted: false }
>

function acceptedBoundaryResult(): AcceptedBoundaryResult {
  const result = P3_BOUNDARY_RESULTS.find(
    (candidate): candidate is AcceptedBoundaryResult => candidate.accepted,
  )
  if (!result) {
    throw new Error('P3 の受理結果がありません')
  }
  return result
}

const ACCEPTED_BOUNDARY_RESULT = acceptedBoundaryResult()
const REJECTED_BOUNDARY_RESULTS = P3_BOUNDARY_RESULTS.filter(
  (result): result is RejectedBoundaryResult => !result.accepted,
)

function targetReference(): TargetEventReference {
  return Object.fromEntries(
    TARGET_EVENT_REFERENCE_ELEMENTS.map((element) => [element, {}]),
  ) as TargetEventReference
}

function firstTargetReferenceElement(): keyof TargetEventReference {
  const element = TARGET_EVENT_REFERENCE_ELEMENTS[0]
  if (!element) {
    throw new Error('対象参照の要素がありません')
  }
  return element
}

function acceptance(): I6Acceptance {
  return {
    targetReference: targetReference(),
    expectedVersion: {},
    d5: {},
    confirmedContent: {},
  }
}

function acceptedCandidate(
  expected: I6Acceptance,
  overrides: Partial<I6AcceptedResult> = {},
): unknown {
  return {
    boundaryResult: ACCEPTED_BOUNDARY_RESULT.id,
    acceptedResult: {
      ...expected,
      acceptedAt: {},
      ...overrides,
    },
  }
}

describe('p3Result', () => {
  it('P3 受理結果を I6 の5要素の全組として束縛する', () => {
    const expected = acceptance()
    const parsed = parseP3ResultEnvelope(acceptedCandidate(expected), expected)

    expect(parsed.boundaryResult).toEqual(ACCEPTED_BOUNDARY_RESULT)
    expect(parsed.boundaryResult.accepted).toBe(true)
    if (!('acceptedResult' in parsed)) {
      throw new Error('P3 受理結果が保持されていません')
    }
    expect(parsed.acceptedResult.targetReference).toBe(expected.targetReference)
    expect(parsed.acceptedResult.expectedVersion).toBe(expected.expectedVersion)
    expect(parsed.acceptedResult.d5).toBe(expected.d5)
    expect(parsed.acceptedResult.confirmedContent).toBe(
      expected.confirmedContent,
    )
    expect(parsed.acceptedResult.acceptedAt).toBeDefined()
  })

  const mismatchCases = [
    [
      '対象参照',
      (expected: I6Acceptance): Partial<I6AcceptedResult> => ({
        targetReference: {
          ...expected.targetReference,
          [firstTargetReferenceElement()]: {},
        },
      }),
      /対象参照/,
    ],
    ['D5', (): Partial<I6AcceptedResult> => ({ d5: {} }), /D5/],
    ['V11', (): Partial<I6AcceptedResult> => ({ expectedVersion: {} }), /V11/],
    [
      '確定内容',
      (): Partial<I6AcceptedResult> => ({ confirmedContent: {} }),
      /確定内容/,
    ],
  ] as const

  it.each(mismatchCases)(
    '別%sの P3 受理結果を fail-closed に拒否する',
    (_name, createOverrides, expectedError) => {
      const expected = acceptance()

      expect(() =>
        parseP3ResultEnvelope(
          acceptedCandidate(expected, createOverrides(expected)),
          expected,
        ),
      ).toThrowError(expectedError)
    },
  )

  it('accepted_at が undefined の P3 受理結果を拒否する', () => {
    const expected = acceptance()

    expect(() =>
      parseP3ResultEnvelope(
        acceptedCandidate(expected, { acceptedAt: undefined }),
        expected,
      ),
    ).toThrowError(/accepted_at/)
  })

  it.each([
    'targetReference',
    'expectedVersion',
    'd5',
    'confirmedContent',
  ] as const)('%s が undefined の P3 受理結果を拒否する', (key) => {
    const expected = acceptance()

    expect(() =>
      parseP3ResultEnvelope(
        acceptedCandidate(expected, { [key]: undefined }),
        expected,
      ),
    ).toThrow()
  })

  it('境界結果が undefined の P3 応答を拒否する', () => {
    expect(() =>
      parseP3ResultEnvelope({ boundaryResult: undefined }, acceptance()),
    ).toThrow()
  })

  it.each([
    (expected: I6Acceptance) => ({
      boundaryResult: ACCEPTED_BOUNDARY_RESULT.id,
      acceptedResult: { ...expected, acceptedAt: {} },
      extra: {},
    }),
    (expected: I6Acceptance) => ({
      boundaryResult: ACCEPTED_BOUNDARY_RESULT.id,
      acceptedResult: { ...expected, acceptedAt: {}, extra: {} },
    }),
  ])('余分なキーを持つ P3 受理入力を拒否する', (candidate) => {
    const expected = acceptance()

    expect(() => parseP3ResultEnvelope(candidate(expected), expected)).toThrow()
  })

  it.each(REJECTED_BOUNDARY_RESULTS)(
    '$id は I6 情報を持たない独立応答として受け取る',
    (boundaryResult) => {
      const parsed = parseP3ResultEnvelope(
        { boundaryResult: boundaryResult.id },
        acceptance(),
      )

      expect(parsed).toEqual({ boundaryResult })
      expect(Object.keys(parsed)).toEqual(['boundaryResult'])
    },
  )

  it.each(REJECTED_BOUNDARY_RESULTS)(
    '$id に I6 情報を載せると fail-closed に拒否する',
    (boundaryResult) => {
      const expected = acceptance()

      expect(() =>
        parseP3ResultEnvelope(
          {
            boundaryResult: boundaryResult.id,
            acceptedResult: {
              ...expected,
              acceptedAt: {},
            },
          },
          expected,
        ),
      ).toThrowError(/拒否結果に I6 情報/)
    },
  )

  it('未知の P3 境界結果を fail-closed に拒否する', () => {
    expect(() =>
      parseP3ResultEnvelope(
        { boundaryResult: '未知の P3 境界結果' },
        acceptance(),
      ),
    ).toThrowError(/未知の境界結果/)
  })

  it('受理と拒否の封筒を型で区別し、拒否側に I6 情報を持たせない', () => {
    const accepted: P3AcceptedResultEnvelope = {
      boundaryResult: ACCEPTED_BOUNDARY_RESULT,
      acceptedResult: { ...acceptance(), acceptedAt: {} },
    }
    const rejectedBoundaryResult = REJECTED_BOUNDARY_RESULTS[0]
    if (!rejectedBoundaryResult) {
      throw new Error('P3 の拒否結果がありません')
    }
    const rejected: P3RejectedResultEnvelope = {
      boundaryResult: rejectedBoundaryResult,
      // @ts-expect-error 拒否結果の封筒は I6 情報を受け取らない。
      acceptedResult: accepted.acceptedResult,
    }

    expect(Object.hasOwn(rejected, 'acceptedResult')).toBe(true)
  })

  it('識別値や確定内容の内部形式を検査しない', () => {
    const opaque = new Proxy(
      {},
      {
        get() {
          throw new Error('不透明値の内部を読みました')
        },
        ownKeys() {
          throw new Error('不透明値の内部キーを読みました')
        },
      },
    )
    const reference = Object.fromEntries(
      TARGET_EVENT_REFERENCE_ELEMENTS.map((element) => [element, opaque]),
    ) as TargetEventReference
    const expected: I6Acceptance = {
      targetReference: reference,
      expectedVersion: opaque,
      d5: opaque,
      confirmedContent: opaque,
    }
    const acceptedAt = Symbol('accepted_at')
    const parsed = parseP3ResultEnvelope(
      acceptedCandidate(expected, { acceptedAt }),
      expected,
    )

    expect(parsed.boundaryResult.accepted).toBe(true)
    if ('acceptedResult' in parsed) {
      expect(parsed.acceptedResult.expectedVersion).toBe(opaque)
      expect(parsed.acceptedResult.d5).toBe(opaque)
      expect(parsed.acceptedResult.confirmedContent).toBe(opaque)
      expect(parsed.acceptedResult.acceptedAt).toBe(acceptedAt)
    }
  })

  it('値の長さ・文字種・物理型を検査するコードを持たない', () => {
    const formatInspectionPatterns = [
      /\.match\s*\(/,
      /\.test\s*\(/,
      /\bRegExp\b/,
      /charCodeAt/,
      /codePointAt/,
      /\.startsWith\s*\(/,
      /\.endsWith\s*\(/,
      /UUID/i,
      /typeof\s+[^\n]*(?:expectedVersion|d5|confirmedContent|acceptedAt)/,
    ]

    for (const pattern of formatInspectionPatterns) {
      expect(p3ResultSource).not.toMatch(pattern)
    }
  })
})
