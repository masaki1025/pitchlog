import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it } from 'vitest'
import { VmArtifactAdapter, VmArtifactError } from './artifactAdapter'
import { runVectors, type VectorContract } from './vectorRunner'

const ROOT = resolve(process.cwd(), '..')
const FIXTURE = resolve(ROOT, 'tests/domain/runners/fixtures/artifact-adapter')
const vector = JSON.parse(
  readFileSync(resolve(FIXTURE, 'vector.json'), 'utf8'),
) as {
  generatedId: string
  contract: Omit<VectorContract, 'runner'>
  cases: {
    caseId: string
    raw: unknown
    normalized: unknown
    expected: unknown
  }[]
}
const declaration = JSON.parse(
  readFileSync(resolve(FIXTURE, 'pitchlog-domain.json'), 'utf8'),
) as { sha256: string }

it('同じ合成 artifact を vm で読み、全 case を runner で消費する', async () => {
  const adapter = new VmArtifactAdapter(
    resolve(FIXTURE, 'pitchlog-domain.js'),
    vector.generatedId,
  )
  expect(adapter.sourceHash).toBe(`sha256:${declaration.sha256}`)
  const report = await runVectors(
    vector.cases,
    { ...vector.contract, runner: 'vitest' },
    adapter,
    adapter,
  )
  expect(report.complete).toBe(true)
  expect(report.consumedCaseIds).toEqual(
    vector.cases.map((item) => item.caseId),
  )
  expect(adapter.calls).toHaveLength(vector.cases.length * 2)
  for (const [index, item] of vector.cases.entries()) {
    expect(JSON.parse(adapter.calls[index * 2]?.responseJson ?? '')).toEqual(
      item.normalized,
    )
    expect(
      JSON.parse(adapter.calls[index * 2 + 1]?.responseJson ?? ''),
    ).toEqual(item.expected)
  }
})

it('JSON の数値型をゲストへ渡さない', () => {
  const adapter = new VmArtifactAdapter(
    resolve(FIXTURE, 'pitchlog-domain.js'),
    vector.generatedId,
  )
  expect(() => adapter.normalize([{ legacyValue: 1 }])).toThrow(VmArtifactError)
  expect(adapter.calls).toHaveLength(0)
})
