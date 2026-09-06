import { describe, expect, it } from 'vitest'
import boundaryResultsSource from './boundaryResults.ts?raw'
import { readCanonBoundaryResults } from './canonOracle'
import {
  ACK_BOUNDARY_RESULTS,
  NO_ACK_BOUNDARY_RESULTS,
  parseAckBoundaryResult,
  type AckBoundaryResult,
  type NoAckBoundaryResult,
} from './boundaryResults'

const canonBoundaryResults = readCanonBoundaryResults()
const canonAckResults = canonBoundaryResults.slice(0, 4)
const canonNoAckResults = canonBoundaryResults.slice(4)

function expectAckResultSet(actual: readonly AckBoundaryResult[]): void {
  expect(new Set(actual.map((result) => result.boundaryResult.id))).toEqual(
    new Set(canonAckResults.map((result) => result.id)),
  )
}

describe('boundaryResults', () => {
  it('R-BOUNDARY の B1〜B7 を ACK あり4件・ACKなし3件へ完全に分ける', () => {
    expect(canonBoundaryResults).toHaveLength(7)
    expect(ACK_BOUNDARY_RESULTS).toHaveLength(4)
    expect(NO_ACK_BOUNDARY_RESULTS).toHaveLength(3)
    expectAckResultSet(ACK_BOUNDARY_RESULTS)
    expect(
      new Set(
        NO_ACK_BOUNDARY_RESULTS.map((result) => result.boundaryResult.id),
      ),
    ).toEqual(new Set(canonNoAckResults.map((result) => result.id)))
    expect(
      new Set(
        [...ACK_BOUNDARY_RESULTS, ...NO_ACK_BOUNDARY_RESULTS].map(
          (result) => result.boundaryResult.id,
        ),
      ),
    ).toEqual(new Set(canonBoundaryResults.map((result) => result.id)))
  })

  it.each(canonAckResults)('$id を ACK 経路から受け取る', ({ id }) => {
    expect(parseAckBoundaryResult(id)).toEqual({
      delivery: 'ack',
      boundaryResult: expect.objectContaining({ id }),
    })
  })

  it.each(canonNoAckResults)(
    '$id を ACK 経路へ渡すと fail-closed に拒否する',
    ({ id }) => {
      expect(() => parseAckBoundaryResult(id)).toThrowError(/ACK が返りません/)
    },
  )

  it('未知の境界結果を fail-closed に拒否する', () => {
    expect(() => parseAckBoundaryResult('未知の境界結果')).toThrowError(
      /未知の D1 境界結果/,
    )
  })

  it('余分なキーを持つ境界結果入力を拒否する', () => {
    expect(() =>
      parseAckBoundaryResult({
        boundaryResult: canonAckResults[0]!.id,
        extra: {},
      }),
    ).toThrow()
  })

  it('ACK ありと ACK なしを型の discriminant で区別する', () => {
    type AckDelivery = AckBoundaryResult['delivery']
    type NoAckDelivery = NoAckBoundaryResult['delivery']
    const ackDelivery: AckDelivery = 'ack'
    const noAckDelivery: NoAckDelivery = 'no-ack'
    const cannotPassNoAckAsAck = (result: NoAckBoundaryResult): void => {
      // @ts-expect-error ACK が返らない結果を ACK 結果として扱えない。
      const invalid: AckBoundaryResult = result
      expect(invalid).toBe(result)
    }

    expect(ackDelivery).not.toBe(noAckDelivery)
    expect(cannotPassNoAckAsAck).toBeTypeOf('function')
  })

  it('変異: ACK 許可集合へ最初の ACK なし結果を足すと exact-set 検査が失敗する', () => {
    const noAckResult = NO_ACK_BOUNDARY_RESULTS[0]!
    const mutatedResults: readonly AckBoundaryResult[] = [
      ...ACK_BOUNDARY_RESULTS,
      { delivery: 'ack', boundaryResult: noAckResult.boundaryResult },
    ]

    expect(() => expectAckResultSet(mutatedResults)).toThrow()
  })

  it('ACK 許可集合の境界 ID を文字列リテラルで再定義していない', () => {
    const exactBoundaryIdLiterals = [
      ...boundaryResultsSource.matchAll(/(['"])(B[1-7])\1/g),
    ].map((match) => match[2])

    expect(exactBoundaryIdLiterals).toEqual([])
  })

  it('境界 ID の文字列や数値を解釈して ACK 有無を決めない', () => {
    expect(boundaryResultsSource).not.toMatch(
      /\.slice\s*\(|\bNumber\s*\(|\bparseInt\s*\(|\bparseFloat\s*\(/,
    )
  })

  it('B3 の下位分類や境界結果の決定処理を持たない', () => {
    expect(boundaryResultsSource).not.toMatch(/(['"])B3[ab]\1/)
    expect(boundaryResultsSource).not.toMatch(/reason|content|payload/i)
  })
})
