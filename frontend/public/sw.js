/* 配布時に build plugin が版固定 manifest を埋め込む。開発 server では登録しない。 */
const manifest = __PITCHLOG_PRECACHE_MANIFEST__
const cacheName = `pitchlog-static-${manifest.buildId}`
const stageName = `${cacheName}-stage`
const assets = new Map(
  manifest.assets.map((asset) => [asset.path, asset.sha256]),
)
const expectedPaths = [...assets.keys()].sort()

async function matchesHash(response, expected) {
  if (!response || !response.ok) return false
  const bytes = await response.clone().arrayBuffer()
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const actual = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
  return actual === expected
}

async function complete(cache) {
  const keys = await cache.keys()
  const actualPaths = keys
    .map((key) => {
      const url = new URL(key.url)
      if (url.origin !== self.location.origin || url.search || url.hash)
        return ''
      return url.pathname
    })
    .sort()
  if (
    actualPaths.length !== expectedPaths.length ||
    actualPaths.some((path, index) => path !== expectedPaths[index])
  )
    return false
  for (const [path, digest] of assets) {
    if (!(await matchesHash(await cache.match(path), digest))) return false
  }
  return true
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      if ((await caches.keys()).includes(cacheName)) {
        if (!(await complete(await caches.open(cacheName))))
          throw new Error('既存の同版 cache が不完全')
        return
      }
      await caches.delete(stageName)
      const stage = await caches.open(stageName)
      try {
        for (const [path, digest] of assets) {
          const url = new URL(path, self.location.origin)
          const response = await fetch(
            new Request(url, {
              cache: 'no-store',
              credentials: 'omit',
              redirect: 'error',
            }),
          )
          if (
            !response.ok ||
            response.redirected ||
            response.url !== url.href ||
            !(await matchesHash(response, digest))
          )
            throw new Error(`静的 asset が不正: ${path}`)
          await stage.put(path, response)
        }
        if (!(await complete(stage))) throw new Error('静的 bundle が不完全')
        const final = await caches.open(cacheName)
        try {
          for (const path of expectedPaths) {
            const response = await stage.match(path)
            if (!response) throw new Error('静的 bundle が不完全')
            await final.put(path, response)
          }
          if (!(await complete(final))) throw new Error('静的 bundle が不完全')
        } catch (error) {
          await caches.delete(cacheName)
          throw error
        }
      } finally {
        await caches.delete(stageName)
      }
    })(),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const current = await caches.open(cacheName)
      if (!(await complete(current))) throw new Error('静的 bundle が不完全')
      for (const name of await caches.keys()) {
        if (name.startsWith('pitchlog-static-') && name !== cacheName)
          await caches.delete(name)
      }
    })(),
  )
})

function shellRoute(path) {
  return (
    path === '/' ||
    path === '/help' ||
    path === '/login' ||
    path === '/team' ||
    path === '/games' ||
    /^\/games\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/record$/i.test(
      path,
    )
  )
}

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  if (url.pathname === '/api' || url.pathname.startsWith('/api/')) return
  const navigation = request.mode === 'navigate' && shellRoute(url.pathname)
  const path = navigation
    ? '/index.html'
    : !url.search && assets.has(url.pathname)
      ? url.pathname
      : null
  if (path === null) return
  event.respondWith(
    (async () => {
      try {
        const cache = await caches.open(cacheName)
        if (navigation && !(await complete(cache))) return Response.error()
        const response = await cache.match(path)
        if (!(await matchesHash(response, assets.get(path))))
          return Response.error()
        return response
      } catch {
        return Response.error()
      }
    })(),
  )
})
