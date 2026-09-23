// @vitest-environment node

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { inspectBuildArtifacts, inspectCspDocument } from '../../vite.config.ts'

const FRONTEND_ROOT = process.cwd()
const VALID_CSP =
  "default-src 'self'; base-uri 'none'; connect-src 'self'; " +
  "font-src 'self'; form-action 'self'; frame-src 'none'; " +
  "img-src 'self' data:; manifest-src 'self'; object-src 'none'; " +
  "script-src 'self'; style-src 'self' 'unsafe-inline'; worker-src 'self'"

function html(body: string): string {
  return (
    '<!doctype html><html><head>' +
    `<meta http-equiv="Content-Security-Policy" content="${VALID_CSP}">` +
    `</head><body>${body}</body></html>`
  )
}

describe('frontend production build の閉域', { timeout: 60_000 }, () => {
  it('index.html の CSP の実内容を読んで閉域設定を確認する', () => {
    const source = readFileSync(resolve(FRONTEND_ROOT, 'index.html'), 'utf8')
    const inspected = inspectCspDocument(source)

    expect(inspected.status, inspected.reasons.join('\n')).toBe('conforming')
    expect(inspected.directives['script-src']).toEqual(["'self'"])
    expect(inspected.directives['object-src']).toEqual(["'none'"])
    expect(inspected.directives['connect-src']).toEqual(["'self'"])
  })

  it('外部リソース参照が 1 件でも不適合にする', () => {
    const inspected = inspectBuildArtifacts([
      {
        path: 'index.html',
        content: html(
          '<script src="https://cdn.example.invalid/app.js"></script>',
        ),
      },
    ])

    expect(inspected.status).toBe('nonconforming')
    expect(inspected.scannedFiles).toBe(1)
    expect(inspected.externalReferences).toEqual([
      {
        path: 'index.html',
        reference: 'https://cdn.example.invalid/app.js',
      },
    ])
  })

  it('解析不能な build を合格にしない', () => {
    const inspected = inspectBuildArtifacts([
      { path: 'index.html', content: html('') },
      { path: 'assets/broken.js', content: new Uint8Array([0xff]) },
    ])

    expect(inspected.status).toBe('indeterminate')
    expect(inspected.scannedFiles).toBe(2)
    expect(inspected.reasons).toContain(
      'build を UTF-8 として読めない: assets/broken.js',
    )
  })

  it('走査対象が 0 件なら空振りとして合格にしない', () => {
    const inspected = inspectBuildArtifacts([])

    expect(inspected.status).toBe('indeterminate')
    expect(inspected.scannedFiles).toBe(0)
  })

  it('index.html が無い build は CSP 未検査として不適合にする', () => {
    const inspected = inspectBuildArtifacts([
      { path: 'assets/app.js', content: "console.log('built')\n" },
    ])

    expect(inspected.status).toBe('nonconforming')
    expect(inspected.scannedFiles).toBe(1)
    expect(inspected.policyViolations).toEqual([
      {
        path: 'index.html',
        message: 'CSP を検査する index.html が build にない',
      },
    ])
  })

  it('外部参照の無い build 出力を正の走査件数で受理する', () => {
    const inspected = inspectBuildArtifacts([
      {
        path: 'index.html',
        content: html('<script type="module" src="/assets/app.js"></script>'),
      },
      {
        path: 'assets/app.js',
        content: "fetch('/api/games')\n",
      },
      {
        path: 'assets/app.css',
        content: "main { background-image: url('/assets/field.png'); }\n",
      },
      {
        path: 'assets/field.png',
        content: new Uint8Array([0x89, 0x50, 0x4e, 0x47]),
      },
    ])

    expect(inspected.status, JSON.stringify(inspected)).toBe('conforming')
    expect(inspected.scannedFiles).toBeGreaterThan(0)
    expect(inspected.externalReferences).toEqual([])
    expect(inspected.policyViolations).toEqual([])
  })
})
