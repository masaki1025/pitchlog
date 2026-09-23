import { readdirSync, readFileSync } from 'node:fs'
import { extname, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

const frontendRoot = fileURLToPath(new URL('.', import.meta.url))
const contractsRoot = fileURLToPath(new URL('../contracts/', import.meta.url))
const designRelationsRoot = fileURLToPath(
  new URL('../scripts/design_relations/', import.meta.url),
)
const buildOutputRoot = resolve(frontendRoot, 'dist')

type ClosureStatus = 'conforming' | 'nonconforming' | 'indeterminate'

export type BuildArtifact = Readonly<{
  path: string
  content: string | Uint8Array
}>

export type BuildClosureResult = Readonly<{
  status: ClosureStatus
  scannedFiles: number
  externalReferences: readonly Readonly<{
    path: string
    reference: string
  }>[]
  policyViolations: readonly Readonly<{
    path: string
    message: string
  }>[]
  reasons: readonly string[]
}>

export type CspInspectionResult = Readonly<{
  status: ClosureStatus
  directives: Readonly<Record<string, readonly string[]>>
  reasons: readonly string[]
}>

const REQUIRED_CSP = {
  'default-src': ["'self'"],
  'base-uri': ["'none'"],
  'connect-src': ["'self'"],
  'font-src': ["'self'"],
  'form-action': ["'self'"],
  'frame-src': ["'none'"],
  'img-src': ["'self'", 'data:'],
  'manifest-src': ["'self'"],
  'object-src': ["'none'"],
  'script-src': ["'self'"],
  'style-src': ["'self'", "'unsafe-inline'"],
  'worker-src': ["'self'"],
} as const

const TEXT_EXTENSIONS = new Set([
  '.css',
  '.html',
  '.js',
  '.json',
  '.map',
  '.mjs',
  '.svg',
  '.txt',
  '.webmanifest',
  '.xml',
])
const BINARY_EXTENSIONS = new Set([
  '.avif',
  '.gif',
  '.ico',
  '.jpeg',
  '.jpg',
  '.otf',
  '.pdf',
  '.png',
  '.ttf',
  '.wasm',
  '.webp',
  '.woff',
  '.woff2',
])
const MARKUP_RESOURCE_ATTRIBUTES = new Set([
  'action',
  'cite',
  'data',
  'formaction',
  'href',
  'imagesrcset',
  'poster',
  'src',
  'srcset',
])
const JSON_RESOURCE_KEYS = new Set([
  'action',
  'href',
  'icons',
  'scope',
  'screenshots',
  'shortcuts',
  'src',
  'start_url',
  'url',
])

function attributesOf(tag: string): Readonly<Record<string, string>> {
  const attributes: Record<string, string> = {}
  const pattern = /([:\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g
  for (const match of tag.matchAll(pattern)) {
    const name = match[1]
    const value = match[2] ?? match[3]
    if (name !== undefined && value !== undefined) {
      attributes[name.toLowerCase()] = value
    }
  }
  return attributes
}

function sameStrings(
  actual: readonly string[],
  expected: readonly string[],
): boolean {
  return (
    actual.length === expected.length &&
    [...actual]
      .sort()
      .every((value, index) => value === [...expected].sort()[index])
  )
}

/** index.html の CSP を実内容から検査する。 */
export function inspectCspDocument(html: string): CspInspectionResult {
  const cspTags = [...html.matchAll(/<meta\b[^>]*>/gi)]
    .map((match) => attributesOf(match[0]))
    .filter(
      (attributes) =>
        attributes['http-equiv']?.toLowerCase() === 'content-security-policy',
    )

  if (cspTags.length === 0) {
    return {
      status: 'nonconforming',
      directives: {},
      reasons: ['Content-Security-Policy の meta 要素がない'],
    }
  }
  if (cspTags.length !== 1 || cspTags[0]?.content === undefined) {
    return {
      status: 'indeterminate',
      directives: {},
      reasons: ['Content-Security-Policy を一意に解析できない'],
    }
  }

  const directives: Record<string, string[]> = {}
  for (const part of cspTags[0].content.split(';')) {
    const tokens = part.trim().split(/\s+/).filter(Boolean)
    const name = tokens.shift()
    if (name === undefined) {
      continue
    }
    if (directives[name] !== undefined || tokens.length === 0) {
      return {
        status: 'indeterminate',
        directives,
        reasons: [`CSP directive を解析できない: ${name}`],
      }
    }
    directives[name] = tokens
  }

  const reasons: string[] = []
  for (const [name, expected] of Object.entries(REQUIRED_CSP)) {
    const actual = directives[name]
    if (actual === undefined || !sameStrings(actual, expected)) {
      reasons.push(`${name} が閉域の規定値と一致しない`)
    }
  }
  for (const [name, sources] of Object.entries(directives)) {
    if (
      sources.some(
        (source) =>
          source === '*' ||
          /^(?:https?|wss?):/i.test(source) ||
          source.startsWith('//') ||
          source === "'unsafe-eval'",
      )
    ) {
      reasons.push(`${name} に外部接続または動的評価を許す source がある`)
    }
  }

  return {
    status: reasons.length === 0 ? 'conforming' : 'nonconforming',
    directives,
    reasons,
  }
}

function isExternalReference(value: string): boolean {
  const candidate = value.trim()
  return (
    candidate.startsWith('//') || /^(?:https?|wss?|ftp):\/\//i.test(candidate)
  )
}

function splitSourceSet(value: string): string[] {
  return value
    .split(',')
    .map((candidate) => candidate.trim().split(/\s+/, 1)[0])
    .filter((candidate): candidate is string => candidate !== undefined)
}

function markupReferences(content: string): string[] {
  const references: string[] = []
  for (const tag of content.match(/<[^>]+>/g) ?? []) {
    for (const [name, value] of Object.entries(attributesOf(tag))) {
      if (!MARKUP_RESOURCE_ATTRIBUTES.has(name)) {
        continue
      }
      references.push(
        ...(name.endsWith('srcset') ? splitSourceSet(value) : [value]),
      )
    }
  }
  return references
}

function cssReferences(content: string): readonly string[] | string {
  const withoutComments = content.replace(/\/\*[\s\S]*?\*\//g, '')
  if (withoutComments.includes('/*')) {
    return 'CSS のコメントを解析できない'
  }

  const references: string[] = []
  const urlPattern = /url\(\s*(?:"([^"]*)"|'([^']*)'|([^)'"\s]+))\s*\)/gi
  for (const match of withoutComments.matchAll(urlPattern)) {
    const reference = match[1] ?? match[2] ?? match[3]
    if (reference !== undefined) {
      references.push(reference)
    }
  }
  const importPattern = /@import\s+(?:url\(\s*)?["']([^"']+)["']/gi
  for (const match of withoutComments.matchAll(importPattern)) {
    if (match[1] !== undefined) {
      references.push(match[1])
    }
  }
  return references
}

function javascriptReferences(content: string): string[] {
  const references: string[] = []
  const callPattern =
    /\b(?:fetch|import|WebSocket|EventSource|Worker|SharedWorker)\s*\(\s*["'`]([^"'`]+)["'`]/g
  const registrationPattern =
    /\bserviceWorker\.register\s*\(\s*["'`]([^"'`]+)["'`]/g
  const assignmentPattern =
    /\.(?:href|src|action|poster)\s*=\s*["'`]([^"'`]+)["'`]/g
  const attributePattern =
    /\.setAttribute\s*\(\s*["'`](?:href|src|action|poster)["'`]\s*,\s*["'`]([^"'`]+)["'`]/g
  for (const pattern of [
    callPattern,
    registrationPattern,
    assignmentPattern,
    attributePattern,
  ]) {
    for (const match of content.matchAll(pattern)) {
      if (match[1] !== undefined) {
        references.push(match[1])
      }
    }
  }
  return references
}

function jsonReferences(value: unknown, parentKey = ''): string[] {
  if (typeof value === 'string') {
    return JSON_RESOURCE_KEYS.has(parentKey) ? [value] : []
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => jsonReferences(item, parentKey))
  }
  if (typeof value !== 'object' || value === null) {
    return []
  }
  return Object.entries(value).flatMap(([key, item]) =>
    jsonReferences(item, key),
  )
}

function decodeArtifact(artifact: BuildArtifact): string | undefined {
  if (typeof artifact.content === 'string') {
    return artifact.content
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(artifact.content)
  } catch {
    return undefined
  }
}

function artifactReferences(
  path: string,
  content: string,
): readonly string[] | string {
  const extension = extname(path).toLowerCase()
  if (extension === '.html' || extension === '.svg' || extension === '.xml') {
    return markupReferences(content)
  }
  if (extension === '.css') {
    return cssReferences(content)
  }
  if (extension === '.js' || extension === '.mjs') {
    return javascriptReferences(content)
  }
  if (
    extension === '.json' ||
    extension === '.map' ||
    extension === '.webmanifest'
  ) {
    try {
      return jsonReferences(JSON.parse(content))
    } catch {
      return 'JSON を解析できない'
    }
  }
  return []
}

/** production build の全ファイルを閉域として検査する。 */
export function inspectBuildArtifacts(
  artifacts: readonly BuildArtifact[],
): BuildClosureResult {
  if (artifacts.length === 0) {
    return {
      status: 'indeterminate',
      scannedFiles: 0,
      externalReferences: [],
      policyViolations: [],
      reasons: ['build の走査対象が 0 件である'],
    }
  }

  const externalReferences: { path: string; reference: string }[] = []
  const policyViolations: { path: string; message: string }[] = []
  const reasons: string[] = []
  const seenPaths = new Set<string>()
  for (const artifact of artifacts) {
    if (seenPaths.has(artifact.path)) {
      reasons.push(`build のパスが重複している: ${artifact.path}`)
      continue
    }
    seenPaths.add(artifact.path)
    const extension = extname(artifact.path).toLowerCase()
    if (BINARY_EXTENSIONS.has(extension)) {
      continue
    }
    if (!TEXT_EXTENSIONS.has(extension)) {
      reasons.push(`build の形式を判定できない: ${artifact.path}`)
      continue
    }
    const content = decodeArtifact(artifact)
    if (content === undefined) {
      reasons.push(`build を UTF-8 として読めない: ${artifact.path}`)
      continue
    }
    const references = artifactReferences(artifact.path, content)
    if (typeof references === 'string') {
      reasons.push(`${references}: ${artifact.path}`)
      continue
    }
    for (const reference of references) {
      if (isExternalReference(reference)) {
        externalReferences.push({ path: artifact.path, reference })
      }
    }
    if (artifact.path === 'index.html') {
      const csp = inspectCspDocument(content)
      if (csp.status === 'indeterminate') {
        reasons.push(...csp.reasons)
      } else if (csp.status === 'nonconforming') {
        policyViolations.push(
          ...csp.reasons.map((reason) => ({
            path: artifact.path,
            message: reason,
          })),
        )
      }
    }
  }
  if (!seenPaths.has('index.html')) {
    policyViolations.push({
      path: 'index.html',
      message: 'CSP を検査する index.html が build にない',
    })
  }

  return {
    status:
      reasons.length > 0
        ? 'indeterminate'
        : externalReferences.length > 0 || policyViolations.length > 0
          ? 'nonconforming'
          : 'conforming',
    scannedFiles: artifacts.length,
    externalReferences,
    policyViolations,
    reasons,
  }
}

function readBuildArtifacts(root: string): readonly BuildArtifact[] | string {
  const artifacts: BuildArtifact[] = []
  const visit = (directory: string): void => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = resolve(directory, entry.name)
      if (entry.isSymbolicLink()) {
        throw new Error(`symbolic link は解析できない: ${path}`)
      }
      if (entry.isDirectory()) {
        visit(path)
      } else if (entry.isFile()) {
        artifacts.push({
          path: relative(root, path).replaceAll('\\', '/'),
          content: readFileSync(path),
        })
      } else {
        throw new Error(`build の種類を解析できない: ${path}`)
      }
    }
  }
  try {
    visit(root)
    return artifacts
  } catch (error) {
    return error instanceof Error ? error.message : 'build を走査できない'
  }
}

/** production build のディレクトリを実ファイルから検査する。 */
export function inspectBuildDirectory(root: string): BuildClosureResult {
  const artifacts = readBuildArtifacts(root)
  if (typeof artifacts === 'string') {
    return {
      status: 'indeterminate',
      scannedFiles: 0,
      externalReferences: [],
      policyViolations: [],
      reasons: [artifacts],
    }
  }
  return inspectBuildArtifacts(artifacts)
}

function frontendBuildClosure(): Plugin {
  return {
    name: 'pitchlog-frontend-build-closure',
    apply: 'build',
    transformIndexHtml(html) {
      const inspected = inspectCspDocument(html)
      if (inspected.status !== 'conforming') {
        throw new Error(`CSP 検査失敗: ${inspected.reasons.join(', ')}`)
      }
      return html
    },
    closeBundle() {
      const inspected = inspectBuildDirectory(buildOutputRoot)
      console.log(
        `[frontend-build-closure] status=${inspected.status} ` +
          `scannedFiles=${inspected.scannedFiles} ` +
          `externalReferences=${inspected.externalReferences.length} ` +
          `policyViolations=${inspected.policyViolations.length}`,
      )
      if (inspected.status !== 'conforming') {
        const details = [
          ...inspected.reasons,
          ...inspected.externalReferences.map(
            (reference) => `${reference.path}: ${reference.reference}`,
          ),
          ...inspected.policyViolations.map(
            (violation) => `${violation.path}: ${violation.message}`,
          ),
        ]
        throw new Error(`production build 閉域検査失敗: ${details.join(', ')}`)
      }
    },
  }
}

// /api は FastAPI (port 8800) へプロキシ（docs/api_contract_v1.md 共通事項）
export default defineConfig({
  plugins: [vue(), tailwindcss(), frontendBuildClosure()],
  resolve: {
    alias: {
      '@contracts': contractsRoot,
      '@design-relations': designRelationsRoot,
    },
  },
  server: {
    fs: {
      allow: [frontendRoot, contractsRoot, designRelationsRoot],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8800',
        changeOrigin: true,
      },
    },
  },
})
