import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'
import { quantizeCourse } from './courseQuantization'
import { domainOperations } from './publicApi'

type Input = { x: string; y: string; view: string; size: string }
type Success = { ok: true; value: { unit: string; x: string; y: string } }
type Case = { caseId: string; input: Input; expected: unknown }
const contract = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/display-geometry/course_input_quantization_contract_v1.json',
    ),
    'utf8',
  ),
) as {
  cases: Case[]
  mutationDescriptors: Array<{ id: string; caseIds: string[] }>
}
const cases = contract.cases
function run(input: unknown): unknown {
  return JSON.parse(quantizeCourse(JSON.stringify(input)))
}
function success(input: Input): Success {
  const result = run(input) as Success
  expect(result.ok).toBe(true)
  return result
}
const normal: Input = { x: '131.5', y: '124', view: 'catcher', size: '263' }

it('1093件の契約期待値を全封筒で消費する', () => {
  expect(cases).toHaveLength(1093)
  for (const row of cases)
    expect(run(row.input), row.caseId).toEqual(row.expected)
  expect(domainOperations.quantizeCourse).toBe(quantizeCourse)
})

it('整数格子の単調性・上下反転・視点反転・範囲を全264点で検証する', () => {
  let previous = -1n
  for (let k = 0n; k <= 263n; k += 1n) {
    const input = { ...normal, x: k.toString(), y: k.toString() }
    const catcher = success(input).value
    const pitcher = success({ ...input, view: 'pitcher' }).value
    expect(BigInt(catcher.x)).toBeGreaterThan(previous)
    expect(BigInt(catcher.x) + BigInt(pitcher.x)).toBe(263n)
    expect(BigInt(catcher.y) + k).toBe(263n)
    expect(catcher.y).toBe(pitcher.y)
    expect(BigInt(catcher.x)).toBeGreaterThanOrEqual(0n)
    expect(BigInt(catcher.x)).toBeLessThanOrEqual(263n)
    previous = BigInt(catcher.x)
  }
})

it('独立した非対称の軸とsize変更を保存単位まで比較する', () => {
  expect(run({ x: '4.5', y: '2.5', view: 'pitcher', size: '9' })).toEqual({
    ok: true,
    value: { unit: '1/9', x: '4', y: '6' },
  })
  expect(run({ ...normal, x: '0', y: '263' })).toEqual({
    ok: true,
    value: { unit: '1/263', x: '0', y: '0' },
  })
})

describe('閉じたJSON境界', () => {
  it.each([
    null,
    [],
    true,
    {},
    { ...normal, extra: true },
    { ...normal, size: undefined },
  ])('object欠落・余剰を拒否する %j', (input) => {
    expect(run(input)).toEqual({
      ok: false,
      error: { code: 'INVALID_REQUEST' },
    })
  })
  it.each([
    '0',
    '-1',
    '01',
    '1.0',
    '1e2',
    '+1',
    '',
    '1'.repeat(401),
    263,
    null,
  ])('size不正を拒否する %j', (size) => {
    expect(run({ ...normal, size })).toEqual({
      ok: false,
      error: { code: 'INVALID_SIZE' },
    })
  })
  it.each([null, true, 131.5, [], {}, '', '0'.repeat(401)])(
    '両軸の型と防護上限を拒否する %j',
    (value) => {
      for (const key of ['x', 'y'])
        expect(run({ ...normal, [key]: value })).toEqual({
          ok: false,
          error: { code: 'INVALID_DECIMAL' },
        })
    },
  )
  it('非JSON・非文字列の入口を拒否する', () => {
    expect(JSON.parse(quantizeCourse('{'))).toEqual({
      ok: false,
      error: { code: 'INVALID_JSON' },
    })
    expect(JSON.parse(quantizeCourse(null as unknown as string))).toEqual({
      ok: false,
      error: { code: 'INVALID_JSON' },
    })
  })
  it('指数防護の境界400と401・入力長400と401を区別する', () => {
    expect(run({ ...normal, x: '1e-400' })).toEqual({
      ok: true,
      value: { unit: '1/263', x: '0', y: '139' },
    })
    expect(run({ ...normal, x: '1e-401' })).toEqual({
      ok: false,
      error: { code: 'INVALID_DECIMAL' },
    })
    expect(run({ ...normal, x: '0.' + '0'.repeat(398) })).toEqual({
      ok: true,
      value: { unit: '1/263', x: '0', y: '139' },
    })
    expect(run({ ...normal, x: '0.' + '0'.repeat(399) })).toEqual({
      ok: false,
      error: { code: 'INVALID_DECIMAL' },
    })
  })
})

const original = readFileSync(
  resolve(process.cwd(), 'src/domain/courseQuantization.ts'),
  'utf8',
)
function mutated(source: string): (json: string) => string {
  const js = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const context = createContext({ exports: {} })
  new Script(js).runInContext(context, { timeout: 1000 })
  return context.exports.quantizeCourse as (json: string) => string
}
const mutations = [
  ['floor-instead-of-half-up', '>= divisor', '> divisor'],
  [
    'x-reflection-before-rounding',
    'storedX = size - roundedX',
    'storedX = halfUp({ numerator: size * power10(x.scale) - x.numerator, scale: x.scale })',
  ],
  ['skip-y-reflection', '(size - roundedY).toString()', 'roundedY.toString()'],
  [
    'range-after-rounding',
    '!inRange(x, size) || !inRange(y, size)',
    'halfUp(x) < 0n || halfUp(x) > size || halfUp(y) < 0n || halfUp(y) > size',
  ],
  ['hardcoded-size', 'return result\n}', 'return 263n\n}'],
] as const
it.each(mutations)(
  '契約descriptorが非等価変異 %s を実際に検出する',
  (id, before, after) => {
    expect(original.includes(before)).toBe(true)
    const invoke = mutated(original.replace(before, after))
    const descriptor = contract.mutationDescriptors.find(
      (row) => row.id === id,
    )!
    expect(descriptor).toBeDefined()
    const witnesses = cases.filter((row) =>
      descriptor.caseIds.includes(row.caseId),
    )
    expect(witnesses.length).toBeGreaterThan(0)
    expect(
      witnesses.some(
        (row) =>
          JSON.stringify(JSON.parse(invoke(JSON.stringify(row.input)))) !==
          JSON.stringify(row.expected),
      ),
    ).toBe(true)
  },
)
