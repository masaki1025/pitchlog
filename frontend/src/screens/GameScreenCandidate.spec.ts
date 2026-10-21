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
const baselineHistorySha256 = [
  '01b562abdd4a36ce7a912e0a0da7ee894461ecfc1d5792f6e73552aa6c109811',
  '38d2cc07a45b96c940498e79e9281cf578d7cbd0d96eee9a70f8937ccdf21e35',
  '879f570ed17f87195ca226773ee50fbe20bd70fc07f99390647a19af46b949e7',
  'e94351f5b55bec417d6c099a0f0564996e34d4c76d579dd94bc21f9370679238',
  'ad14bfc343f73416bf6399d3dda2bf1a8e4cb5cec313c9ae9afd0c29427c5a26',
  'cbea483400812d264c1ee693f7a2443ad616d0293ad946a73dfe3fdd1962a4b4',
  '031cfad26c9b8a055a8bae050bf171c920497bb3a8d810b691ad277959a55862',
  'de209b128ce1e70cffbb020bb45cdad08fccb88c022b3035323c15d53db66f5b',
  '4768e1fed92ebf821cec977d1939f444cecd527bfe62c6b58cdee1fd6793cfd6',
  '025a14a9f073c8f62786f5898f861853bd8d6441b3bd4445580e4382dd348928',
  '2a50f0d07b7765d44f2bfe26dbc72c42d15107995435b89f28dcdc42f9b2bf2a',
  'a5bfe64104cba757e57730cb080d7e26e5c98d0f50e9a3c765e0519938f586e4',
  '00bebcde101fb5727fe36f0c40664503c11850d891163b01f20de5ae3a72f417',
  'bc7fa149d631258b5ceedaacaece948fbbd51618e308a60df7ab577384e8af6c',
  '787440bdf068bcd8953bbaceee6bf8717ad605b37470d7a21bb777876f6b59bd',
  '0d9711eccf91592ae0b733f15951698f5204cbcf2c4fc68e4f09ed8d1cdafcc7',
  'cb4b921be3056856bbcd01deffc38a651daae3267755c3fd01ea2e6ad0baee60',
  'b600ecc1145f0222e174d3616e68bba5151d8202346ca79bb688ba3417f34978',
  '509e497845665c81621e295e19c752846a6571ca0a34f5942f5d248d9d0b3b47',
  '65fb0c981ba2a85473b1c3eaef556e755ad9fab1d9bcfa84fcd400a7b7ce6171',
  '7fe796cc8e5fad42680cf664478239fddc35cc02fe8ec7ac0ddbadf734da38bf',
  'c8c8164c494677f036442de561eb1b9178a78d7126b6147aff55fa545b748582',
  '3b7fd08ecc2649673f73faaf5877037760e8bf887287b1936f5d69da77613da2',
  '42e8b18456daa39bf5370d7757ee281e35211b7cc15ca9bdeb1ad5d0fcffdc8a',
] as const

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
    expect(oldHistory).toHaveLength(baselineHistorySha256.length)
    expect(
      oldHistory.map((record) => sha256(Buffer.from(JSON.stringify(record)))),
    ).toEqual(baselineHistorySha256)
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
