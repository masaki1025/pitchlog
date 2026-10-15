import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { inspectDomainDirectory, inspectSource, type RuleId } from './check'

const checkDirectory = dirname(fileURLToPath(import.meta.url))
const fixtureDirectory = join(checkDirectory, 'fixtures')
const sourceName = join(checkDirectory, 'src/domain/fixture.ts')

/** fixture の内容を TS 正本と同じパーサーへ渡す。 */
function inspectFixture(name: string) {
  return inspectSource(
    readFileSync(join(fixtureDirectory, name), 'utf8'),
    sourceName,
  )
}

const negativeCases: ReadonlyArray<[string, RuleId]> = [
  ['eval.ts', 'EVAL'],
  ['function-call.ts', 'FUNCTION_CONSTRUCTOR'],
  ['function-new.ts', 'FUNCTION_CONSTRUCTOR'],
  ['function-prototype.ts', 'FUNCTION_CONSTRUCTOR'],
  ['dynamic-import.ts', 'DYNAMIC_IMPORT'],
  ['require-literal.ts', 'REQUIRE'],
  ['require-nonliteral.ts', 'REQUIRE'],
  ['with.ts', 'WITH'],
  ['global-this.ts', 'GLOBAL_OBJECT'],
  ['window.ts', 'GLOBAL_OBJECT'],
  ['self.ts', 'GLOBAL_OBJECT'],
  ['global.ts', 'GLOBAL_OBJECT'],
  ['date.ts', 'DATE'],
  ['math-random.ts', 'MATH_RANDOM'],
  ['math-random-computed.ts', 'MATH_RANDOM'],
  ['intl.ts', 'INTL'],
  ['proxy.ts', 'PROXY'],
  ['reflect.ts', 'REFLECT'],
  ['regex-literal.ts', 'REGEXP'],
  ['regexp.ts', 'REGEXP'],
  ['host-function.ts', 'UNDECLARED_HOST_FUNCTION'],
  ['undeclared-global.ts', 'UNDECLARED_GLOBAL'],
  ['non-static-import.ts', 'NON_STATIC_IMPORT'],
  ['var.ts', 'VAR_DECLARATION'],
  ['unsupported-operator.ts', 'UNSUPPORTED_OPERATOR'],
  ['unknown-class.ts', 'UNKNOWN_SYNTAX'],
  ['unknown-for-in.ts', 'UNKNOWN_SYNTAX'],
  ['unknown-label.ts', 'UNKNOWN_SYNTAX'],
  ['parse-error.ts.txt', 'PARSE_ERROR'],
]

describe('ドメイン構文の閉じた部分集合', () => {
  it.each(negativeCases)('%s は %s で拒否する', (fileName, ruleId) => {
    expect(
      inspectFixture(fileName).map((violation) => violation.ruleId),
    ).toEqual([ruleId])
  })

  it('BigInt だけの合成関数を受理する', () => {
    expect(inspectFixture('positive.ts')).toEqual([])
  })

  it('実際の src/domain を spec を除いて受理する', () => {
    expect(
      inspectDomainDirectory(join(checkDirectory, '../../src/domain')),
    ).toEqual([])
  })

  it('局所宣言を別スコープのホスト関数として認めない', () => {
    const source = `function local(): void { const fetch = () => true; fetch() }
fetch('x')`
    expect(
      inspectSource(source, sourceName).map((item) => item.ruleId),
    ).toContain('UNDECLARED_HOST_FUNCTION')
  })

  it('entry.ts でも公開口への直接代入以外の globalThis は拒否する', () => {
    const entryName = join(checkDirectory, '../../src/domain/entry.ts')
    expect(
      inspectSource(
        'globalThis.PitchlogDomain = domainOperations',
        entryName,
      ).map((item) => item.ruleId),
    ).toContain('GLOBAL_OBJECT')
  })
})
