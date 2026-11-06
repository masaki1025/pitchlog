import { createHash } from 'node:crypto'
import { extname } from 'node:path'

export type StaticArtifact = Readonly<{
  path: string
  content: string | Uint8Array
}>

export type OfflineManifest = Readonly<{
  schemaVersion: 1
  buildId: string
  assets: readonly Readonly<{ path: string; sha256: string }>[]
}>

const MARKER = '__PITCHLOG_PRECACHE_MANIFEST__'
const REQUIRED = new Set([
  'index.html',
  'manifest.webmanifest',
  'domain/pitchlog-domain.js',
  'domain/pitchlog-domain.json',
])
const ASSET_EXTENSIONS = new Set([
  '.css',
  '.js',
  '.svg',
  '.png',
  '.ico',
  '.webp',
  '.woff',
  '.woff2',
  '.wasm',
])

function allowedStaticPath(path: string): boolean {
  if (
    !/^[a-zA-Z0-9._/-]+$/.test(path) ||
    path.includes('..') ||
    path.includes('//')
  )
    return false
  if (REQUIRED.has(path)) return true
  if (path.startsWith('assets/') || path.startsWith('icons/'))
    return ASSET_EXTENSIONS.has(extname(path).toLowerCase())
  return false
}

/** 検査済み build だけから版固定の静的 manifest と worker を作る。 */
export function createOfflineBundle(
  artifacts: readonly StaticArtifact[],
  workerTemplate: string,
): Readonly<{
  manifest: OfflineManifest
  manifestSource: string
  workerSource: string
}> {
  if (workerTemplate.split(MARKER).length !== 2) {
    throw new Error('Service Worker の埋込位置が一意ではない')
  }
  const seen = new Set<string>()
  const assets: { path: string; sha256: string }[] = []
  for (const artifact of artifacts) {
    if (artifact.path === 'sw.js' || artifact.path === 'offline-assets.json')
      continue
    // source map は実行に不要であり、個人情報を含む可能性があるため保存しない。
    if (artifact.path.endsWith('.map')) continue
    if (!allowedStaticPath(artifact.path) || seen.has(artifact.path)) {
      throw new Error(`静的 asset の path が不正: ${artifact.path}`)
    }
    seen.add(artifact.path)
    assets.push({
      path: `/${artifact.path}`,
      sha256: createHash('sha256').update(artifact.content).digest('hex'),
    })
  }
  for (const path of REQUIRED) {
    if (!seen.has(path)) throw new Error(`静的 asset が欠損: ${path}`)
  }
  if (
    !assets.some(
      (asset) =>
        asset.path.startsWith('/assets/') && asset.path.endsWith('.js'),
    )
  ) {
    throw new Error('実行 JS bundle が欠損')
  }
  assets.sort((left, right) => left.path.localeCompare(right.path, 'en'))
  const identity = JSON.stringify({ schemaVersion: 1, assets, workerTemplate })
  const buildId = createHash('sha256').update(identity).digest('hex')
  const manifest: OfflineManifest = { schemaVersion: 1, buildId, assets }
  return {
    manifest,
    manifestSource: `${JSON.stringify(manifest, null, 2)}\n`,
    workerSource: workerTemplate.replace(MARKER, JSON.stringify(manifest)),
  }
}
