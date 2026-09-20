import { spawnSync } from 'node:child_process'
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

const FRONTEND_ROOT = process.cwd()
const CONFIG = resolve(FRONTEND_ROOT, '.dependency-cruiser.cjs')
const DEPCRUISE = resolve(FRONTEND_ROOT, 'node_modules/.bin/depcruise')
const ESLINT = resolve(FRONTEND_ROOT, 'node_modules/.bin/eslint')
const temporaryDirectories: string[] = []

type CruiseResult = Readonly<{
  modules: readonly Readonly<{
    source: string
    dependencies: readonly Readonly<{ resolved: string }>[]
  }>[]
  summary: Readonly<{
    error: number
    violations: readonly Readonly<{ rule: Readonly<{ name: string }> }>[]
  }>
}>

function fixtureRoot(): string {
  const root = mkdtempSync(resolve(FRONTEND_ROOT, '.step45-dependency-'))
  temporaryDirectories.push(root)
  return root
}

function write(root: string, relative: string, content: string): void {
  const path = resolve(root, relative)
  mkdirSync(resolve(path, '..'), { recursive: true })
  writeFileSync(path, content, 'utf8')
}

function runCruiser(root: string): Readonly<{
  exitCode: number
  result: CruiseResult
}> {
  const source = resolve(root, 'src')
  const graph = spawnSync(
    DEPCRUISE,
    ['--config', CONFIG, '--validate', '--output-type', 'json', source],
    { cwd: FRONTEND_ROOT, encoding: 'utf8' },
  )
  if (graph.error !== undefined) {
    throw graph.error
  }
  const result = JSON.parse(graph.stdout) as CruiseResult
  return {
    exitCode: result.summary.error === 0 ? 0 : 1,
    result,
  }
}

function writeGeneratedPair(root: string): void {
  write(
    root,
    'src/lib/generated/artifacts/value.ts',
    "export const generatedValue = 'ok'\n",
  )
  write(
    root,
    'src/lib/generated/wrappers/value.ts',
    "export { generatedValue } from '../artifacts/value'\n",
  )
}

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true })
  }
})

describe('frontend の依存閉域', { timeout: 30_000 }, () => {
  it('生成ラッパー越しの依存を import graph から読み取って受理する', () => {
    const root = fixtureRoot()
    writeGeneratedPair(root)
    write(
      root,
      'src/feature.ts',
      "import { generatedValue } from './lib/generated/wrappers/value'\nvoid generatedValue\n",
    )

    const cruised = runCruiser(root)
    const feature = cruised.result.modules.find((module) =>
      module.source.endsWith('src/feature.ts'),
    )

    expect(cruised.exitCode).toBe(0)
    expect(cruised.result.summary.violations).toEqual([])
    expect(
      feature?.dependencies.some((dependency) =>
        dependency.resolved.endsWith('wrappers/value.ts'),
      ),
    ).toBe(true)
  })

  it('生成物を直接 import すると依存規則違反になる', () => {
    const root = fixtureRoot()
    writeGeneratedPair(root)
    write(
      root,
      'src/feature.ts',
      "import { generatedValue } from './lib/generated/artifacts/value'\nvoid generatedValue\n",
    )

    const cruised = runCruiser(root)

    expect(cruised.exitCode, JSON.stringify(cruised.result)).not.toBe(0)
    expect(
      cruised.result.summary.violations.map((violation) => violation.rule.name),
    ).toContain('no-direct-generated-artifact-import')
  })

  it('解決不能な依存を合格にしない', () => {
    const root = fixtureRoot()
    write(root, 'src/feature.js', "import './missing.js'\n")

    const cruised = runCruiser(root)

    expect(cruised.exitCode, JSON.stringify(cruised.result)).not.toBe(0)
    expect(
      cruised.result.summary.violations.map((violation) => violation.rule.name),
    ).toContain('no-unresolvable-dependency')
  })

  it('lint が動的 import と動的コード生成を拒否する', () => {
    const root = fixtureRoot()
    const source = resolve(root, 'dynamic.ts')
    write(
      root,
      'dynamic.ts',
      "const target = './feature'\nvoid import(target)\neval('target')\nnew Function('return target')\n",
    )

    const linted = spawnSync(ESLINT, ['--format', 'json', source], {
      cwd: FRONTEND_ROOT,
      encoding: 'utf8',
    })
    const messages = (
      JSON.parse(linted.stdout) as readonly Readonly<{
        messages: readonly Readonly<{ ruleId: string | null }>[]
      }>[]
    ).flatMap((result) => result.messages.map((message) => message.ruleId))

    expect(linted.status).toBe(1)
    expect(messages).toContain('no-restricted-syntax')
    expect(messages).toContain('no-eval')
    expect(messages).toContain('no-new-func')
  })

  it('package と lock が同じ dependency-cruiser 版を宣言する', () => {
    const packageJson = JSON.parse(
      readFileSync(resolve(FRONTEND_ROOT, 'package.json'), 'utf8'),
    ) as {
      devDependencies: Record<string, string>
    }
    const lock = readFileSync(resolve(FRONTEND_ROOT, 'pnpm-lock.yaml'), 'utf8')

    expect(packageJson.devDependencies['dependency-cruiser']).toBe('18.3.1')
    expect(lock).toContain('dependency-cruiser:')
    expect(lock).toContain('specifier: 18.3.1')
    expect(lock).toContain('dependency-cruiser@18.3.1:')
  })
})
