import { execFileSync, spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

const REPOSITORY_ROOT = resolve(process.cwd(), '..')
const BACKEND_SOURCE = resolve(REPOSITORY_ROOT, 'backend/src')
const temporaryRepositories: string[] = []

type CollectorResult = Readonly<{
  attempts: number
  entries: readonly Readonly<{ path: string }>[]
  unresolved: readonly unknown[]
}>
type UnknownRecord = Record<string, unknown>
type EntrypointClosureResult = Readonly<{
  status: 'conforming' | 'nonconforming' | 'indeterminate'
  missingDeclarations: readonly string[]
  missingActualEntries: readonly string[]
  reasons: readonly string[]
}>

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function sortedDifference(
  left: ReadonlySet<string>,
  right: ReadonlySet<string>,
): string[] {
  return [...left].filter((value) => !right.has(value)).sort()
}

function readCollectedPaths(collection: unknown): ReadonlySet<string> | string {
  if (!isRecord(collection)) {
    return '収集結果が object でない'
  }
  if (
    !Number.isInteger(collection.attempts) ||
    Number(collection.attempts) <= 0
  ) {
    return '収集器の走査回数が正の整数でない'
  }
  if (!Array.isArray(collection.unresolved)) {
    return '収集結果に unresolved 配列がない'
  }
  if (collection.unresolved.length > 0) {
    return '静的に解決できない入口がある'
  }
  if (!Array.isArray(collection.entries)) {
    return '収集結果に entries 配列がない'
  }

  const paths = new Set<string>()
  for (const entry of collection.entries) {
    if (
      !isRecord(entry) ||
      typeof entry.path !== 'string' ||
      entry.path.length === 0
    ) {
      return '入口に有効な path がない'
    }
    paths.add(entry.path)
  }
  return paths
}

function readDeclaredPaths(manifest: unknown): ReadonlySet<string> | string {
  if (!isRecord(manifest) || !Array.isArray(manifest.calculations)) {
    return 'マニフェストに calculations 配列がない'
  }

  const paths = new Set<string>()
  for (const calculation of manifest.calculations) {
    if (!isRecord(calculation) || !Array.isArray(calculation.entrypoints)) {
      return '対象計算に entrypoints 配列がない'
    }
    for (const entrypoint of calculation.entrypoints) {
      if (
        !isRecord(entrypoint) ||
        typeof entrypoint.module !== 'string' ||
        entrypoint.module.length === 0
      ) {
        return 'entrypoints[] に有効な module がない'
      }
      paths.add(entrypoint.module)
    }
  }
  return paths
}

/** 独立収集した入口とマニフェスト宣言の exact-set を比較する。 */
function compareEntrypointClosure(
  collection: unknown,
  manifest: unknown,
): EntrypointClosureResult {
  const actual = readCollectedPaths(collection)
  const declared = readDeclaredPaths(manifest)

  if (typeof actual === 'string' || typeof declared === 'string') {
    return {
      status: 'indeterminate',
      missingDeclarations: [],
      missingActualEntries: [],
      reasons: [actual, declared].filter(
        (value): value is string => typeof value === 'string',
      ),
    }
  }

  const missingDeclarations = sortedDifference(actual, declared)
  const missingActualEntries = sortedDifference(declared, actual)
  return {
    status:
      missingDeclarations.length === 0 && missingActualEntries.length === 0
        ? 'conforming'
        : 'nonconforming',
    missingDeclarations,
    missingActualEntries,
    reasons: [],
  }
}

function write(root: string, relative: string, content: string): void {
  const path = resolve(root, relative)
  mkdirSync(resolve(path, '..'), { recursive: true })
  writeFileSync(path, content, 'utf8')
}

function syntheticRepository(): string {
  const root = mkdtempSync(resolve(tmpdir(), 'pitchlog-step45-entrypoints-'))
  temporaryRepositories.push(root)
  write(root, 'frontend/vite.config.ts', 'export default { build: {} }\n')
  write(
    root,
    'frontend/index.html',
    '<script type="module" src="/src/main.ts"></script>\n',
  )
  write(root, 'frontend/src/main.ts', "import './reachable'\n")
  write(root, 'frontend/src/reachable.ts', 'export const reachable = true\n')
  write(root, 'frontend/public/manifest.webmanifest', '{}\n')
  return root
}

function runCollector(root: string): Readonly<{
  exitCode: number
  result: CollectorResult
}> {
  const process = spawnSync(
    'python3',
    ['-m', 'pitchlog.domaincheck.collect_entrypoints_fe', '--root', root],
    {
      cwd: REPOSITORY_ROOT,
      env: { ...globalThis.process.env, PYTHONPATH: BACKEND_SOURCE },
      encoding: 'utf8',
    },
  )
  if (process.error !== undefined) {
    throw process.error
  }
  return {
    exitCode: process.status ?? 2,
    result: JSON.parse(process.stdout) as CollectorResult,
  }
}

function manifestFor(result: CollectorResult): unknown {
  return {
    calculations: [
      {
        entrypoints: result.entries.map((entry) => ({ module: entry.path })),
      },
    ],
  }
}

afterEach(() => {
  for (const root of temporaryRepositories.splice(0)) {
    rmSync(root, { recursive: true, force: true })
  }
})

describe('frontend 入口の exact-set', () => {
  it('収集器の実測と entrypoints[] が一致すれば通る', () => {
    const collected = runCollector(syntheticRepository())

    expect(collected.exitCode).toBe(0)
    expect(
      compareEntrypointClosure(collected.result, manifestFor(collected.result)),
    ).toEqual({
      status: 'conforming',
      missingDeclarations: [],
      missingActualEntries: [],
      reasons: [],
    })
  })

  it('実在入口の宣言を 1 件落とすと差分になる', () => {
    const collected = runCollector(syntheticRepository())
    const manifest = manifestFor(collected.result) as {
      calculations: { entrypoints: { module: string }[] }[]
    }
    manifest.calculations[0]?.entrypoints.pop()

    const compared = compareEntrypointClosure(collected.result, manifest)

    expect(compared.status).toBe('nonconforming')
    expect(compared.missingDeclarations).toHaveLength(1)
    expect(compared.missingActualEntries).toEqual([])
  })

  it('実在しない宣言を 1 件足すと逆向きの差分になる', () => {
    const collected = runCollector(syntheticRepository())
    const manifest = manifestFor(collected.result) as {
      calculations: { entrypoints: { module: string }[] }[]
    }
    manifest.calculations[0]?.entrypoints.push({
      module: 'frontend/src/not-collected.ts',
    })

    const compared = compareEntrypointClosure(collected.result, manifest)

    expect(compared.status).toBe('nonconforming')
    expect(compared.missingDeclarations).toEqual([])
    expect(compared.missingActualEntries).toEqual([
      'frontend/src/not-collected.ts',
    ])
  })

  it('収集器が解析不能なら一致として扱わない', () => {
    const root = syntheticRepository()
    write(
      root,
      'frontend/src/main.ts',
      "const workerPath = './worker.ts'\nnew Worker(workerPath)\n",
    )
    const collected = runCollector(root)

    expect(collected.exitCode).toBe(2)
    expect(
      compareEntrypointClosure(collected.result, manifestFor(collected.result)),
    ).toMatchObject({
      status: 'indeterminate',
      missingDeclarations: [],
      missingActualEntries: [],
    })
  })

  it('収集器を別実装へ置き換えず既存モジュールとして起動する', () => {
    const help = execFileSync(
      'python3',
      ['-m', 'pitchlog.domaincheck.collect_entrypoints_fe', '--help'],
      {
        cwd: REPOSITORY_ROOT,
        env: { ...globalThis.process.env, PYTHONPATH: BACKEND_SOURCE },
        encoding: 'utf8',
      },
    )

    expect(help).toContain('Frontend の実在入口')
  })
})
