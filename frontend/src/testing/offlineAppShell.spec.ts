import { webcrypto } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runInNewContext } from 'node:vm'
import { describe, expect, it } from 'vitest'
import { createOfflineBundle, type StaticArtifact } from '../../offline-build'

const origin = 'https://pitchlog.test'
const artifacts: StaticArtifact[] = [
  { path: 'index.html', content: '<html>PitchLog</html>' },
  { path: 'manifest.webmanifest', content: '{}' },
  { path: 'domain/pitchlog-domain.js', content: 'globalThis.pitchlog = {}' },
  { path: 'domain/pitchlog-domain.json', content: '{}' },
  { path: 'assets/app.js', content: 'console.log("ready")' },
  { path: 'assets/app.css', content: 'body { color: black; }' },
  { path: 'icons/app.svg', content: '<svg />' },
]
const template = readFileSync(resolve('public/sw.js'), 'utf8')

class MemoryCache {
  readonly values = new Map<string, Response>()

  async put(path: string, response: Response): Promise<void> {
    this.values.set(new URL(path, origin).pathname, response.clone())
  }

  async match(path: string): Promise<Response | undefined> {
    return this.values.get(new URL(path, origin).pathname)?.clone()
  }

  async keys(): Promise<Request[]> {
    return [...this.values.keys()].map(
      (path) => new Request(new URL(path, origin)),
    )
  }
}

class MemoryStorage {
  readonly values = new Map<string, MemoryCache>()

  async keys(): Promise<string[]> {
    return [...this.values.keys()]
  }

  async open(name: string): Promise<MemoryCache> {
    let cache = this.values.get(name)
    if (!cache) {
      cache = new MemoryCache()
      this.values.set(name, cache)
    }
    return cache
  }

  async delete(name: string): Promise<boolean> {
    return this.values.delete(name)
  }
}

type FetchEvent = {
  request: { method: string; url: string; mode: string }
  respondWith(promise: Promise<Response>): void
}

function workerHarness(options: { tamperedPath?: string } = {}) {
  const bundle = createOfflineBundle(artifacts, template)
  const storage = new MemoryStorage()
  const handlers = new Map<string, (event: never) => void>()
  const self = {
    location: { origin },
    addEventListener(name: string, callback: (event: never) => void) {
      handlers.set(name, callback)
    },
  }
  const fetch = async (request: Request): Promise<Response> => {
    const path = new URL(request.url).pathname
    const artifact = artifacts.find((item) => `/${item.path}` === path)
    if (!artifact) throw new Error(`unexpected network request: ${path}`)
    const content =
      options.tamperedPath === path
        ? 'tampered'
        : typeof artifact.content === 'string'
          ? artifact.content
          : new TextDecoder().decode(artifact.content)
    const response = new Response(content)
    Object.defineProperty(response, 'url', { value: request.url })
    return response
  }
  runInNewContext(bundle.workerSource, {
    self,
    caches: storage,
    fetch,
    Request,
    Response,
    URL,
    crypto: webcrypto,
  })
  async function dispatch(name: string): Promise<void> {
    let pending: Promise<unknown> | undefined
    handlers.get(name)?.({
      waitUntil(promise: Promise<unknown>) {
        pending = promise
      },
    } as never)
    if (!pending) throw new Error(`${name} handler did not wait`)
    await pending
  }
  async function request(
    path: string,
    mode: string = 'navigate',
  ): Promise<Response | undefined> {
    let pending: Promise<Response> | undefined
    const event: FetchEvent = {
      request: { method: 'GET', url: new URL(path, origin).href, mode },
      respondWith(promise) {
        pending = promise
      },
    }
    handlers.get('fetch')?.(event as never)
    return pending
  }
  return { bundle, storage, dispatch, request }
}

describe('版固定 offline app shell', () => {
  it('閉域の全 asset を埋め込み、欠損・未知・重複を拒否する', () => {
    const bundle = createOfflineBundle(artifacts, template)
    expect(bundle.manifest.assets.map((asset) => asset.path)).toEqual([
      '/assets/app.css',
      '/assets/app.js',
      '/domain/pitchlog-domain.js',
      '/domain/pitchlog-domain.json',
      '/icons/app.svg',
      '/index.html',
      '/manifest.webmanifest',
    ])
    expect(bundle.workerSource).not.toContain('__PITCHLOG_PRECACHE_MANIFEST__')
    expect(() =>
      createOfflineBundle(
        artifacts.filter((item) => item.path !== 'index.html'),
        template,
      ),
    ).toThrow('欠損')
    expect(() =>
      createOfflineBundle(
        [...artifacts, { path: 'api/session.json', content: '{}' }],
        template,
      ),
    ).toThrow('path が不正')
    expect(() =>
      createOfflineBundle([...artifacts, artifacts[0]!], template),
    ).toThrow('path が不正')
  })

  it('全件成功後の既 route だけを静的 cache から返し、API は横取りしない', async () => {
    const harness = workerHarness()
    await harness.dispatch('install')
    await harness.dispatch('activate')
    expect((await harness.request('/help'))?.status).toBe(200)
    expect(
      (
        await harness.request(
          '/games/12345678-1234-1234-1234-123456789abc/record',
        )
      )?.status,
    ).toBe(200)
    expect((await harness.request('/assets/app.js', 'cors'))?.status).toBe(200)
    expect(await harness.request('/api/auth/session')).toBeUndefined()
    expect(await harness.request('/unknown')).toBeUndefined()
    expect(await harness.request('https://other.test/app.js')).toBeUndefined()
    expect([...harness.storage.values.keys()]).toEqual([
      `pitchlog-static-${harness.bundle.manifest.buildId}`,
    ])
  })

  it('配布改竄で新 install を失敗させ、既版 cache を保つ', async () => {
    const harness = workerHarness({ tamperedPath: '/assets/app.js' })
    await harness.storage.open('pitchlog-static-old')
    await expect(harness.dispatch('install')).rejects.toThrow('不正')
    expect([...harness.storage.values.keys()]).toEqual(['pitchlog-static-old'])
  })

  it('容量不足で新 cache の確定が失敗しても既版を壊さない', async () => {
    const harness = workerHarness()
    await harness.storage.open('pitchlog-static-old')
    const originalOpen = harness.storage.open.bind(harness.storage)
    harness.storage.open = async (name: string) => {
      const cache = await originalOpen(name)
      if (name === `pitchlog-static-${harness.bundle.manifest.buildId}`) {
        cache.put = async () => {
          throw new Error('quota')
        }
      }
      return cache
    }
    await expect(harness.dispatch('install')).rejects.toThrow('quota')
    expect([...harness.storage.values.keys()]).toEqual(['pitchlog-static-old'])
  })

  it('cache の後発改竄・bundle 欠損を cold navigation 前に拒否する', async () => {
    const harness = workerHarness()
    await harness.dispatch('install')
    const cache = await harness.storage.open(
      `pitchlog-static-${harness.bundle.manifest.buildId}`,
    )
    await cache.put('/index.html', new Response('modified'))
    expect((await harness.request('/help'))?.type).toBe('error')
    await harness.storage.delete(
      `pitchlog-static-${harness.bundle.manifest.buildId}`,
    )
    const incomplete = await harness.storage.open(
      `pitchlog-static-${harness.bundle.manifest.buildId}`,
    )
    await incomplete.put('/index.html', new Response('<html>PitchLog</html>'))
    expect((await harness.request('/help'))?.type).toBe('error')
  })
})
