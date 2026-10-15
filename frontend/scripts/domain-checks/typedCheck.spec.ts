import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeAll, describe, expect, it } from 'vitest'
import { inspectSource, type RuleId } from './check'
import {
  inspectTypedDomainDirectory,
  inspectTypedFiles,
  type TypedRuleId,
  type TypedViolation,
} from './typedCheck'

const checkDirectory = dirname(fileURLToPath(import.meta.url))
const fixtureDirectory = join(checkDirectory, 'fixtures/typed')
const configPath = resolve(checkDirectory, '../../tsconfig.json')

const negativeCases: ReadonlyArray<[string, TypedRuleId]> = [
  ['number-literal.ts', 'NUMBER_TYPE'],
  ['number-parameter.ts', 'NUMBER_TYPE'],
  ['number-return.ts', 'NUMBER_TYPE'],
  ['number-property.ts', 'NUMBER_TYPE'],
  ['number-union.ts', 'NUMBER_TYPE'],
  ['number-string-length.ts', 'NUMBER_TYPE'],
  ['number-array-length.ts', 'NUMBER_TYPE'],
  ['number-indexof.ts', 'NUMBER_TYPE'],
  ['number-bigint-mix.ts', 'NUMBER_TYPE'],
  ['convert-implicit-minus.ts', 'STRING_TO_NUMBER'],
  ['convert-implicit-multiply.ts', 'STRING_TO_NUMBER'],
  ['round.ts', 'MATH_ROUNDING'],
  ['floor.ts', 'MATH_ROUNDING'],
  ['ceil.ts', 'MATH_ROUNDING'],
  ['trunc.ts', 'MATH_ROUNDING'],
  ['round-computed.ts', 'MATH_ROUNDING'],
  ['unknown-arithmetic.ts', 'UNRESOLVED_ARITHMETIC'],
]

const syntaxRejectedConversions: ReadonlyArray<[string, RuleId]> = [
  ['convert-number.ts', 'UNDECLARED_HOST_FUNCTION'],
  ['convert-parseint.ts', 'UNDECLARED_HOST_FUNCTION'],
  ['convert-parsefloat.ts', 'UNDECLARED_HOST_FUNCTION'],
  ['convert-unary-plus.ts', 'UNSUPPORTED_OPERATOR'],
  ['convert-multiply.ts', 'UNKNOWN_SYNTAX'],
]

const syntaxCleanTypedCases = [
  'number-string-length.ts',
  'number-array-length.ts',
  'number-indexof.ts',
  'convert-implicit-minus.ts',
  'convert-implicit-multiply.ts',
]

let fixtureViolations: TypedViolation[] = []

describe('ドメインの型付き number 禁止', () => {
  beforeAll(() => {
    fixtureViolations = inspectTypedFiles(
      [
        ...negativeCases.map(([name]) => join(fixtureDirectory, name)),
        join(checkDirectory, 'fixtures/positive.ts'),
      ],
      configPath,
    )
  })

  it.each(negativeCases)('%s は %s で拒否する', (name, ruleId) => {
    const actual = fixtureViolations
      .filter(
        (violation) => violation.fileName === join(fixtureDirectory, name),
      )
      .map((violation) => violation.ruleId)
    expect(actual).toContain(ruleId)
  })

  it.each(syntaxRejectedConversions)(
    '%s は既存の構文規則 %s で拒否する',
    (name, ruleId) => {
      const source = readFileSync(join(fixtureDirectory, name), 'utf8')
      const actual = inspectSource(
        source,
        resolve(checkDirectory, '../../src/domain/fixture.ts'),
      ).map((violation) => violation.ruleId)
      expect(actual).toContain(ruleId)
    },
  )

  it.each(syntaxCleanTypedCases)(
    '%s は構文上許されても型付き規則で拒否する',
    (name) => {
      const source = readFileSync(join(fixtureDirectory, name), 'utf8')
      expect(
        inspectSource(
          source,
          resolve(checkDirectory, '../../src/domain/fixture.ts'),
        ),
      ).toEqual([])
      expect(
        fixtureViolations.some(
          (violation) => violation.fileName === join(fixtureDirectory, name),
        ),
      ).toBe(true)
    },
  )

  it('BigInt だけの合成関数を受理する', () => {
    expect(
      fixtureViolations.filter((violation) =>
        violation.fileName.endsWith('/fixtures/positive.ts'),
      ),
    ).toEqual([])
  })

  it('実際の src/domain を受理する', () => {
    expect(
      inspectTypedDomainDirectory(
        resolve(checkDirectory, '../../src/domain'),
        configPath,
      ),
    ).toEqual([])
  })

  it('設定を読めなければ型検査済みとして扱わない', () => {
    expect(
      inspectTypedFiles(
        [join(checkDirectory, 'fixtures/positive.ts')],
        join(checkDirectory, 'missing-tsconfig.json'),
      ).map((violation) => violation.ruleId),
    ).toContain('TYPE_CHECK_FAILED')
  })
})
