// @vitest-environment node
// esbuild の TextEncoder と Uint8Array は Node の同じ realm で使う。
import { createHash } from 'node:crypto'
import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { buildDomain } from './build.mjs'
import { inspectArtifactTokens } from './lexical.mjs'

const scriptDirectory = dirname(fileURLToPath(import.meta.url))
const frontendRoot = resolve(scriptDirectory, '../..')
const committedDirectory = join(frontendRoot, 'public/domain')
const temporaryDirectories = []

/** 検査ごとに空のビルド先を作る。 */
async function cleanDirectory() {
  const directory = await mkdtemp(join(tmpdir(), 'pitchlog-domain-'))
  temporaryDirectories.push(directory)
  return directory
}

afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  )
})

describe('単一 artifact の字句閉包', () => {
  it('コメントと文字列の語は読み込みと判定しない', () => {
    const source = `// require import export\nconst text = "require import export"; /* import */ const template = \`require \${value} import export\`;`
    expect(inspectArtifactTokens(source)).toEqual([])
  })

  it('テンプレート式の中の読み込みは拒否する', () => {
    expect(
      inspectArtifactTokens('const value = `x ${require("./other.js")}`').map(
        (violation) => violation.token,
      ),
    ).toContain('require')
  })

  it.each([
    ['literal-require.js.txt', 'require'],
    ['nonliteral-require.js.txt', 'require'],
    ['literal-import.js.txt', 'import'],
    ['dynamic-import.js.txt', 'import'],
    ['export.js.txt', 'export'],
  ])('%s の %s を拒否する', async (name, token) => {
    const source = await readFile(
      join(scriptDirectory, 'fixtures', name),
      'utf8',
    )
    expect(
      inspectArtifactTokens(source).map((violation) => violation.token),
    ).toContain(token)
  })

  it('解析不能な JS を合格扱いにしない', () => {
    expect(
      inspectArtifactTokens('const =').map((item) => item.token),
    ).toContain('PARSE_ERROR')
  })
})

describe('再現ビルド', () => {
  it('独立した空の出力先で同じ SHA-256 を得て、宣言と一致する', async () => {
    const firstDirectory = await cleanDirectory()
    const secondDirectory = await cleanDirectory()
    expect(await readdir(firstDirectory)).toEqual([])
    expect(await readdir(secondDirectory)).toEqual([])

    const first = await buildDomain({ outputDirectory: firstDirectory })
    const second = await buildDomain({ outputDirectory: secondDirectory })
    const committed = await readFile(
      join(committedDirectory, 'pitchlog-domain.js'),
    )
    const declaration = JSON.parse(
      await readFile(join(committedDirectory, 'pitchlog-domain.json'), 'utf8'),
    )
    const committedHash = createHash('sha256').update(committed).digest('hex')
    expect(first.sha256).toBe(second.sha256)
    expect(first.sha256).toBe(committedHash)
    expect(declaration).toEqual({
      schemaVersion: 1,
      fileName: 'pitchlog-domain.js',
      sha256: committedHash,
    })
    expect(await readFile(first.artifactPath)).toEqual(committed)
    expect(await readFile(second.artifactPath)).toEqual(committed)
    expect(first.sizeBytes).toBe(committed.length)
    expect(inspectArtifactTokens(committed.toString('utf8'))).toEqual([])
  })

  it('AST 違反がある入口から artifact と宣言を出さない', async () => {
    const directory = await cleanDirectory()
    const domainDirectory = join(directory, 'src/domain')
    const entry = join(domainDirectory, 'entry.ts')
    const outputDirectory = join(directory, 'output')
    await mkdir(domainDirectory, { recursive: true })
    await writeFile(entry, "eval('1')\n")

    await expect(
      buildDomain({ domainDirectory, entry, outputDirectory }),
    ).rejects.toThrow('EVAL')
    await expect(
      stat(join(outputDirectory, 'pitchlog-domain.js')),
    ).rejects.toMatchObject({
      code: 'ENOENT',
    })
    await expect(
      stat(join(outputDirectory, 'pitchlog-domain.json')),
    ).rejects.toMatchObject({
      code: 'ENOENT',
    })
  })

  it('型付き違反がある入口から artifact を出さない', async () => {
    const directory = await cleanDirectory()
    const domainDirectory = join(directory, 'src/domain')
    const entry = join(domainDirectory, 'entry.ts')
    const outputDirectory = join(directory, 'output')
    await mkdir(domainDirectory, { recursive: true })
    await writeFile(entry, "export const count = 'x'.length\n")

    await expect(
      buildDomain({ domainDirectory, entry, outputDirectory }),
    ).rejects.toThrow('NUMBER_TYPE')
    await expect(
      stat(join(outputDirectory, 'pitchlog-domain.js')),
    ).rejects.toMatchObject({ code: 'ENOENT' })
  })
})
