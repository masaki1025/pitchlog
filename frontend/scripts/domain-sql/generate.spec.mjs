import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import ts from 'typescript'

import { compileSql, SQL_SUBSET } from './generate.mjs'

const ROW = 'type Row = { amount: bigint; active: boolean; code: string }\n'
const ROWS = [
  { amount: '-5', active: true, code: 'a' },
  { amount: '18446744073709551621', active: true, code: 'b' },
  { amount: '2', active: false, code: 'c' },
]
const BINDINGS = { threshold: '0' }
const aggregate = readFileSync(
  resolve(process.cwd(), 'scripts/domain-sql/fixtures/aggregate.ts'),
  'utf8',
)
const classify = readFileSync(
  resolve(process.cwd(), 'scripts/domain-sql/fixtures/classify.ts'),
  'utf8',
)

function classification(body, returnType = 'string') {
  return `${ROW}export const definition = (row: Row, threshold: bigint): ${returnType} => ${body}\n`
}

function aggregation(countBody, sumBody = 'row.amount') {
  return (
    `${ROW}export const definition = {\n` +
    `count: (row: Row, threshold: bigint): boolean => ${countBody},\n` +
    `sum: (row: Row, threshold: bigint): bigint => ${sumBody},\n` +
    '}\n'
  )
}

function expectRule(source, mode, ruleId) {
  expect(() => compileSql(source, mode, ROWS, BINDINGS)).toThrowError(
    expect.objectContaining({ ruleId }),
  )
}

describe('型付き TS からの SQL 生成', () => {
  it('宣言した構文・演算・関数集合だけを変換対象にする', () => {
    expect(SQL_SUBSET.sourceKinds).toEqual([
      ts.SyntaxKind.TypeAliasDeclaration,
      ts.SyntaxKind.VariableStatement,
    ])
    expect(SQL_SUBSET.functions).toEqual([])
    expect(SQL_SUBSET.operators[ts.SyntaxKind.SlashToken]).toBeUndefined()
    expect(SQL_SUBSET.aggregateKeys).toEqual(['count', 'sum'])
  })

  it('合成の集計を FILTER と SUM を持つパラメータ化 SQL にする', () => {
    const generated = compileSql(aggregate, 'aggregate', ROWS, BINDINGS)
    expect(generated.sql).toContain('COUNT(*) FILTER (WHERE')
    expect(generated.sql).toContain('COALESCE(SUM(')
    expect(generated.sql).toContain('FROM jsonb_array_elements(%s::jsonb)')
    expect(generated.sql).not.toContain('18446744073709551621')
    expect(generated.resultType).toBe('aggregate')
    expect(generated.parameters).toEqual(['0', '0', '0', JSON.stringify(ROWS)])
  })

  it('合成の行分類を CASE と順序を持つパラメータ化 SQL にする', () => {
    const generated = compileSql(classify, 'classify', ROWS, BINDINGS)
    expect(generated.sql).toContain('CASE WHEN')
    expect(generated.sql).toContain('WITH ORDINALITY')
    expect(generated.sql).toContain('ORDER BY r.ordinal')
    expect(generated.sql).not.toContain('accepted')
    expect(generated.resultType).toBe('string')
    expect(generated.parameters).toEqual([
      '0',
      'accepted',
      'rejected',
      JSON.stringify(ROWS),
    ])
  })

  it('文字列の利用者値を SQL へ連結しない', () => {
    const source = classification("row.code === prefix ? 'yes' : 'no'").replace(
      'threshold: bigint',
      'prefix: string',
    )
    const injected = "a' OR TRUE --"
    const generated = compileSql(source, 'classify', ROWS, { prefix: injected })
    expect(generated.sql).not.toContain(injected)
    expect(generated.parameters).toContain(injected)
  })

  it('行分類の戻り値に BigInt と真偽も許す', () => {
    const bigint = compileSql(
      `${ROW}export const definition = (row: Row): bigint => row.amount`,
      'classify',
      ROWS,
      {},
    )
    const boolean = compileSql(
      `${ROW}export const definition = (row: Row): boolean => row.active`,
      'classify',
      ROWS,
      {},
    )
    expect(bigint.resultType).toBe('bigint')
    expect(boolean.resultType).toBe('boolean')
  })

  it('エンジン間で照合順序が異なる文字列の大小比較を拒否する', () => {
    expectRule(
      classification("row.code > 'a' ? 'yes' : 'no'"),
      'classify',
      'SQL_UNSUPPORTED_OPERATOR',
    )
  })

  it.each([
    [
      'ループ',
      classification(
        "{ for (const item of [row.code]) { void item } return 'x' }",
      ),
      aggregation(
        '{ for (const item of [row.code]) { void item } return true }',
      ),
      'SQL_UNSUPPORTED_SYNTAX',
    ],
    [
      '再帰',
      classification('definition(row, threshold)'),
      aggregation('definition.count(row, threshold)'),
      'SQL_UNSUPPORTED_CALL',
    ],
    [
      '配列操作',
      classification("row.code.split(',').join('')"),
      aggregation("row.code.includes('a')"),
      'SQL_UNSUPPORTED_CALL',
    ],
    ['number', classification('1'), aggregation('1'), 'SQL_NUMBER_TYPE'],
    [
      '文字列結合',
      classification("row.code + 'x'"),
      aggregation("row.code + 'x' === 'ax'"),
      'SQL_UNSUPPORTED_OPERATOR',
    ],
    [
      '判定不能',
      classification('missing'),
      aggregation('missing'),
      'SQL_TYPE_UNRESOLVED',
    ],
    [
      '丸め関数',
      classification("Math.round(row.amount) === 0 ? 'x' : 'y'"),
      aggregation('Math.round(row.amount) === 0'),
      'SQL_UNSUPPORTED_CALL',
    ],
  ])(
    '%s は分類と集計の両方で拒否する',
    (_name, classified, counted, ruleId) => {
      expectRule(classified, 'classify', ruleId)
      expectRule(counted, 'aggregate', ruleId)
    },
  )

  it('不正な入力と構文解析失敗に SQL を返さない', () => {
    expectRule(
      classification("row.amount / threshold === 0n ? 'x' : 'y'"),
      'classify',
      'SQL_UNSUPPORTED_OPERATOR',
    )
    expectRule(
      aggregation('row.amount / threshold === 0n'),
      'aggregate',
      'SQL_UNSUPPORTED_OPERATOR',
    )
    expectRule(classification('('), 'classify', 'SQL_PARSE_ERROR')
    expect(() =>
      compileSql(
        classify,
        'classify',
        [{ ...ROWS[0], amount: '01' }],
        BINDINGS,
      ),
    ).toThrowError(expect.objectContaining({ ruleId: 'SQL_INVALID_INPUT' }))
  })

  it('Row の number 型を分類と集計の両方で拒否する', () => {
    expectRule(
      classify.replace('amount: bigint', 'amount: number'),
      'classify',
      'SQL_NUMBER_TYPE',
    )
    expectRule(
      aggregate.replace('amount: bigint', 'amount: number'),
      'aggregate',
      'SQL_NUMBER_TYPE',
    )
  })
})
