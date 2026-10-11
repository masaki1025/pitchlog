// @vitest-environment node

import { describe, expect, it } from 'vitest'
import viteConfig, { stripApiPrefix } from '../../vite.config.ts'

describe('開発用 /api proxy', () => {
  it.each([
    ['/api/health', '/health'],
    ['/api/players?limit=1', '/players?limit=1'],
    ['/api', '/'],
    ['/api?x=1', '/?x=1'],
    ['/apix', '/apix'],
    ['/players', '/players'],
  ])('%s は %s になる', (path, expected) => {
    expect(stripApiPrefix(path)).toBe(expected)
  })

  it('server.proxy の /api が stripApiPrefix を使う', () => {
    const apiProxy = viteConfig.server?.proxy?.['/api']

    expect(apiProxy).toBeTypeOf('object')
    if (typeof apiProxy !== 'object' || apiProxy === null) {
      throw new Error('/api の proxy 設定がありません')
    }
    expect(apiProxy.rewrite).toBe(stripApiPrefix)
  })
})
