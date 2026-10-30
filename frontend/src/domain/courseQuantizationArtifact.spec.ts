// @vitest-environment node
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { expect, it } from 'vitest'

it('実配布artifactで1093契約の完全封筒を返す', () => {
  const context = createContext(Object.create(null))
  new Script(
    readFileSync(resolve('public/domain/pitchlog-domain.js'), 'utf8'),
  ).runInContext(context, { timeout: 1000 })
  const contract = JSON.parse(
    readFileSync(
      resolve(
        '../contracts/display-geometry/course_input_quantization_contract_v1.json',
      ),
      'utf8',
    ),
  ) as { cases: Array<{ caseId: string; input: unknown; expected: unknown }> }
  expect(contract.cases).toHaveLength(1093)
  for (const row of contract.cases) {
    context.request = JSON.stringify(row.input)
    const output: unknown = new Script(
      'PitchlogDomain.quantizeCourse(request)',
    ).runInContext(context, { timeout: 1000 })
    expect(typeof output).toBe('string')
    expect(JSON.parse(output as string), row.caseId).toEqual(row.expected)
  }
})
