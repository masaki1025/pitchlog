import { createHash } from 'node:crypto'
import { mkdir, mkdtemp, rename, rm, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { build } from 'esbuild'
import { inspectArtifactTokens } from './lexical.mjs'

const scriptDirectory = dirname(fileURLToPath(import.meta.url))
const frontendRoot = resolve(scriptDirectory, '../..')
const sourceRoot = join(frontendRoot, 'src/domain')
const entryPoint = join(sourceRoot, 'entry.ts')
const configPath = join(frontendRoot, 'tsconfig.json')
const artifactName = 'pitchlog-domain.js'
const declarationName = 'pitchlog-domain.json'

let checksPromise

/** 既存の TS 検査器を Node 用に一時変換し、検査関数を読み込む。 */
async function loadChecks() {
  checksPromise ??= (async () => {
    const temporary = await mkdtemp(join(scriptDirectory, '.checks-'))
    try {
      await build({
        entryPoints: [
          {
            in: join(frontendRoot, 'scripts/domain-checks/check.ts'),
            out: 'syntax',
          },
          {
            in: join(frontendRoot, 'scripts/domain-checks/typedCheck.ts'),
            out: 'typed',
          },
        ],
        outdir: temporary,
        bundle: true,
        platform: 'node',
        format: 'esm',
        packages: 'external',
        logLevel: 'silent',
      })
      const syntax = await import(
        pathToFileURL(join(temporary, 'syntax.js')).href
      )
      const typed = await import(
        pathToFileURL(join(temporary, 'typed.js')).href
      )
      return {
        inspectSyntax: syntax.inspectDomainDirectory,
        inspectTypes: typed.inspectTypedDomainDirectory,
      }
    } finally {
      await rm(temporary, { recursive: true, force: true })
    }
  })()
  return checksPromise
}

/** 構文・型検査後だけに単一 IIFE と SHA-256 宣言を出力する。 */
export async function buildDomain({
  domainDirectory = sourceRoot,
  entry = entryPoint,
  outputDirectory = join(frontendRoot, 'public/domain'),
  tsconfig = configPath,
} = {}) {
  if (resolve(entry) !== join(resolve(domainDirectory), 'entry.ts')) {
    throw new Error('ビルド入口は検査対象の src/domain/entry.ts に限定します')
  }
  const { inspectSyntax, inspectTypes } = await loadChecks()
  const syntaxViolations = inspectSyntax(domainDirectory)
  const typedViolations = inspectTypes(domainDirectory, tsconfig)
  if (syntaxViolations.length > 0 || typedViolations.length > 0) {
    throw new Error(
      `ドメイン検査違反: ${JSON.stringify({ syntaxViolations, typedViolations })}`,
    )
  }

  const output = await build({
    entryPoints: [entry],
    outfile: join(outputDirectory, artifactName),
    absWorkingDir: frontendRoot,
    bundle: true,
    format: 'iife',
    platform: 'neutral',
    splitting: false,
    target: 'es2020',
    minify: true,
    sourcemap: false,
    legalComments: 'none',
    charset: 'utf8',
    write: false,
    logLevel: 'silent',
  })
  if (output.outputFiles?.length !== 1) {
    throw new Error('単一 artifact を生成できません')
  }
  const bytes = output.outputFiles[0].contents
  const lexicalViolations = inspectArtifactTokens(
    new TextDecoder('utf-8', { fatal: true }).decode(bytes),
  )
  if (lexicalViolations.length > 0) {
    throw new Error(`artifact の禁止字句: ${JSON.stringify(lexicalViolations)}`)
  }

  const sha256 = createHash('sha256').update(bytes).digest('hex')
  const declaration = {
    schemaVersion: 1,
    fileName: artifactName,
    sha256,
  }
  const directory = resolve(outputDirectory)
  await mkdir(directory, { recursive: true })
  const artifactPath = join(directory, artifactName)
  const declarationPath = join(directory, declarationName)
  const stagedArtifact = `${artifactPath}.tmp`
  const stagedDeclaration = `${declarationPath}.tmp`
  try {
    await writeFile(stagedArtifact, bytes)
    await writeFile(
      stagedDeclaration,
      `${JSON.stringify(declaration, null, 2)}\n`,
    )
    await rename(stagedArtifact, artifactPath)
    await rename(stagedDeclaration, declarationPath)
  } finally {
    await rm(stagedArtifact, { force: true })
    await rm(stagedDeclaration, { force: true })
  }
  return { artifactPath, declarationPath, sha256, sizeBytes: bytes.length }
}

// artifact と宣言はこのスクリプトで生成し、人手で編集しない。
if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  buildDomain()
    .then(({ sha256, sizeBytes }) => {
      process.stdout.write(`${sha256} ${sizeBytes} bytes\n`)
    })
    .catch((error) => {
      process.stderr.write(
        `${error instanceof Error ? error.message : error}\n`,
      )
      process.exitCode = 1
    })
}
