// Python 側の比較試験から Vitest と同じ vm adapter を直接呼ぶ。
import { readFileSync } from 'node:fs'
import { VmArtifactAdapter } from '../../../../../frontend/src/testing/artifactAdapter.ts'

const artifactPath = process.argv[2]
const vectorPath = process.argv[3]
if (!artifactPath || !vectorPath) throw new Error('artifact と vector のパスが必要')

const vector = JSON.parse(readFileSync(vectorPath, 'utf8'))
const adapter = new VmArtifactAdapter(artifactPath, vector.generatedId)
for (const item of vector.cases) {
  const normalized = adapter.normalize(item.raw)
  adapter.execute(item.caseId, normalized)
}
process.stdout.write(JSON.stringify(adapter.calls))
