import { createHash } from 'node:crypto'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
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

function bytes(path: string): Buffer {
  return readFileSync(resolve(repository, path))
}

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

  it('元のCI・全影響資産・corpusを保持し、宣言外の波及を隠さない', () => {
    expect(affected).toHaveLength(8)
    expect(metadata.undeclared_asset_scope).toHaveLength(6)
    for (const path of [ci, manifest, ...affected]) {
      expect(candidateBytes('before', path)).toEqual(bytes(path))
    }
    const actualTargets = readdirSync(
      resolve(repository, 'contracts/tenant_boundary'),
    )
      .filter((name) => name.endsWith('.json'))
      .map((name) => `contracts/tenant_boundary/${name}`)
      .filter((path) => {
        const asset = json(bytes(path))
        const control = asset.baseline_control as Record<string, unknown>
        const identity = control.identity as Record<string, unknown>
        const projection = identity.frozen_projection as Record<string, unknown>
        return (projection.external_files as string[]).includes(ci)
      })
    expect(actualTargets).toEqual(affected)
  })

  it('CI候補のbrowser scriptは封鎖projectだけを必須経路にする', () => {
    const packageJson = json(bytes('frontend/package.json'))
    const scripts = packageJson.scripts as Record<string, string>
    expect(scripts['test:browser']).toContain('--project sealed-ui')
    expect(scripts['test:browser:real']).toContain('--project real-game')
    expect(candidateBytes('after', ci).toString('utf8')).toContain(
      '- run: pnpm run test:browser',
    )
  })

  it('旧履歴と署名を維持し、新しい人間受理欄は空のままにする', () => {
    const oldAsset = json(candidateBytes('before', authority))
    const newAsset = json(candidateBytes('after', authority))
    const oldHistory = (oldAsset.baseline_control as Record<string, unknown>)[
      'history'
    ] as Record<string, unknown>[]
    const newHistory = (newAsset.baseline_control as Record<string, unknown>)[
      'history'
    ] as Record<string, unknown>[]
    expect(newHistory.slice(0, oldHistory.length)).toEqual(oldHistory)
    expect(newHistory).toHaveLength(oldHistory.length + 1)
    expect(newHistory.at(-1)).toMatchObject({
      acceptance_id: '',
      approved_by: '',
      approved_on: '',
    })
    expect(metadata.accepted_by).toBe('')
    expect(metadata.accepted_date).toBe('')
    expect(metadata.accepted_on).toBe('')
    expect(metadata.signature).toBe('')
  })

  it('patch は前後ファイルと追記snapshotだけを含み、候補bytesと一致する', () => {
    const hashes = metadata.candidate_file_sha256 as Record<string, string>
    expect(Object.keys(hashes).sort()).toEqual(
      [ci, manifest, ...affected].sort(),
    )
    for (const [path, expected] of Object.entries(hashes)) {
      expect(sha256(candidateBytes('after', path))).toBe(expected)
    }
    const snapshotNames = metadata.new_snapshot_names as string[]
    expect(readdirSync(resolve(candidate, 'new-snapshots')).sort()).toEqual(
      snapshotNames,
    )
    for (const name of snapshotNames) {
      expect(
        existsSync(
          resolve(
            repository,
            'contracts/tenant_boundary/history-snapshots',
            name,
          ),
        ),
      ).toBe(false)
      expect(
        sha256(readFileSync(resolve(candidate, 'new-snapshots', name))),
      ).toBe(name)
    }
    const patch = readFileSync(resolve(candidate, 'candidate.patch'), 'utf8')
    const paths = [...patch.matchAll(/^diff --git a\/(.*?) b\//gm)].map(
      (match) => match[1],
    )
    expect(paths.sort()).toEqual(
      [
        ci,
        manifest,
        ...affected,
        ...snapshotNames.map(
          (name) => `contracts/tenant_boundary/history-snapshots/${name}`,
        ),
      ].sort(),
    )
  })
})
