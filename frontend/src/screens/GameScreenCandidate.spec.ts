import { createHash } from 'node:crypto'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const candidate = resolve(
  repository,
  'docs/features/uf8-full-game-followup/step7-candidate',
)
const authority = 'contracts/tenant_boundary/base-allowlist.json'
const manifest = 'tests/fixtures/frozen-archive-cases/manifest.json'
const ci = '.github/workflows/ci.yml'

function candidateBytes(stage: 'before' | 'after', path: string): Buffer {
  return readFileSync(resolve(candidate, stage, path))
}

function json(value: Buffer): Record<string, unknown> {
  return JSON.parse(value.toString('utf8')) as Record<string, unknown>
}

function sha256(value: Buffer): string {
  return createHash('sha256').update(value).digest('hex')
}

describe('ステップ7の未受理凍結候補', () => {
  const metadata = json(readFileSync(resolve(candidate, 'metadata.json')))
  const affected = metadata.affected_assets as string[]
  const generated = metadata.undeclared_generated_scope as string[]
  const paths = [ci, manifest, ...affected, ...generated].sort()

  it('候補内のbefore/afterは固定SHAと対象集合に一致する', () => {
    const beforeHashes = metadata.before_file_sha256 as Record<string, string>
    const afterHashes = metadata.candidate_file_sha256 as Record<string, string>
    expect(Object.keys(beforeHashes).sort()).toEqual(paths)
    expect(Object.keys(afterHashes).sort()).toEqual(paths)
    for (const path of paths) {
      expect(sha256(candidateBytes('before', path))).toBe(beforeHashes[path])
      expect(sha256(candidateBytes('after', path))).toBe(afterHashes[path])
    }
    const assets = affected.map((path) => ({
      path,
      value: json(candidateBytes('before', path)),
    }))
    const actual = assets
      .filter(({ value }) => {
        const control = value.baseline_control as Record<string, unknown>
        const identity = control.identity as Record<string, unknown>
        const projection = identity.frozen_projection as Record<string, unknown>
        return (projection.external_files as string[]).includes(ci)
      })
      .map(({ path }) => path)
    expect(actual).toEqual(affected)
    expect(metadata.asset_set).toEqual(
      [...affected, 'contracts/tenant_boundary/frozen-inputs.json'].sort(),
    )
    expect(affected).toHaveLength(8)
    expect(generated).toHaveLength(3)
    expect(metadata.undeclared_asset_scope).toHaveLength(6)
  })

  it('CI候補は必須frontend jobでbackend変更とPython支援も検査する', () => {
    const after = candidateBytes('after', ci).toString('utf8')
    expect(after).toContain("- 'backend/**'")
    expect(after).toContain(
      "- 'docs/features/uf8-full-game-followup/step7-candidate/generate.py'",
    )
    expect(after).toContain("- 'pyproject.toml'")
    expect(after).toContain("- 'uv.lock'")
    expect(after).toContain("- 'mise.toml'")
    expect(after).toContain('timeout-minutes: 40')
    expect(after).toContain('GameScreenE2eSupport.py')
    expect(after).toContain('step7-candidate/generate.py')
    expect(after).toContain('backend/.venv/bin/ruff check')
    expect(after).toContain('backend/.venv/bin/ty check')
    expect(after).toContain('- run: pnpm run test:browser')
  })

  it('旧履歴・署名はbefore/after共通で、新しい人間受理欄は空に保つ', () => {
    const oldAsset = json(candidateBytes('before', authority))
    const newAsset = json(candidateBytes('after', authority))
    const oldHistory = (oldAsset.baseline_control as Record<string, unknown>)[
      'history'
    ] as Record<string, unknown>[]
    const newHistory = (newAsset.baseline_control as Record<string, unknown>)[
      'history'
    ] as Record<string, unknown>[]
    expect(oldHistory).toHaveLength(23)
    expect(newHistory.slice(0, oldHistory.length)).toEqual(oldHistory)
    expect(newHistory).toHaveLength(oldHistory.length + 1)
    expect(newHistory.at(-1)).toMatchObject({
      acceptance_id: '',
      approved_by: '',
      approved_on: '',
    })
    expect(metadata.old_history_length).toBe(oldHistory.length)
    expect(metadata.candidate_history_length).toBe(newHistory.length)
    expect(metadata.accepted_by).toBe('')
    expect(metadata.accepted_date).toBe('')
    expect(metadata.accepted_on).toBe('')
    expect(metadata.signature).toBe('')
  })

  it('patchの固定digestと対象集合・新snapshot bytesが整合する', () => {
    const patchPath = resolve(candidate, 'candidate.patch')
    const patch = readFileSync(patchPath)
    expect(sha256(patch)).toBe(metadata.patch_sha256)
    expect(patch.toString('utf8')).not.toMatch(/^ $/m)
    const snapshotNames = metadata.new_snapshot_names as string[]
    expect(readdirSync(resolve(candidate, 'new-snapshots')).sort()).toEqual(
      snapshotNames,
    )
    for (const name of snapshotNames) {
      expect(
        sha256(readFileSync(resolve(candidate, 'new-snapshots', name))),
      ).toBe(name)
    }
    const patchPaths = [
      ...patch.toString('utf8').matchAll(/^diff --git a\/(.*?) b\//gm),
    ].map((match) => match[1])
    expect(patchPaths.sort()).toEqual(
      [
        ...paths,
        ...snapshotNames.map(
          (name) => `contracts/tenant_boundary/history-snapshots/${name}`,
        ),
      ].sort(),
    )
  })
})
