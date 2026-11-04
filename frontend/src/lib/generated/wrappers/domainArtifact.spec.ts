// @vitest-environment node

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runInNewContext } from 'node:vm'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { getDomainArtifact, invokeFirstBallDomain } from './domainArtifact'

const artifactPath = resolve(process.cwd(), 'public/domain/pitchlog-domain.js')

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('配布済みドメイン artifact の読み込み口', () => {
  it.each(['18446744073709551621', '-18446744073709551621'])(
    '同一ファイルを vm で読み込み、%s を公開口から往復する',
    (value) => {
      const context: Record<string, unknown> = Object.create(null)
      runInNewContext(readFileSync(artifactPath, 'utf8'), context, {
        timeout: 1_000,
      })

      const published: unknown = Reflect.get(context, 'PitchlogDomain')
      expect(published).toBeDefined()
      expect(Object.isFrozen(published)).toBe(true)
      vi.stubGlobal('PitchlogDomain', published)

      const request = JSON.stringify({ value })
      const expected = JSON.stringify({ ok: true, value })
      expect(
        (published as { ping: (requestJson: string) => string }).ping(request),
      ).toBe(expected)
      expect(getDomainArtifact().ping(request)).toBe(expected)
    },
  )

  it('未読み込みと公開口の形の不一致を明示的に拒否する', () => {
    vi.stubGlobal('PitchlogDomain', undefined)
    expect(() => getDomainArtifact()).toThrow('読み込まれていません')

    vi.stubGlobal('PitchlogDomain', { ping: () => '{}' })
    expect(() => getDomainArtifact()).toThrow('公開口が不正')

    vi.stubGlobal('PitchlogDomain', Object.freeze({ ping: 'invalid' }))
    expect(() => getDomainArtifact()).toThrow('公開口が不正')
  })
})

describe('初球の単一artifact操作呼出', () => {
  it('操作未供給時に成功値を補わない', () => {
    vi.stubGlobal('PitchlogDomain', Object.freeze({ ping: () => '{}' }))
    expect(() => invokeFirstBallDomain('quantizeCourse', {})).toThrow(
      '供給されていません',
    )
  })
  it('失敗封筒や余剰キーを成功値へ読み替えない', () => {
    for (const response of [
      '{"ok":false,"error":{"code":"INVALID_REQUEST"}}',
      '{"ok":true,"value":{},"extra":1}',
    ]) {
      vi.stubGlobal(
        'PitchlogDomain',
        Object.freeze({ ping: () => '{}', quantizeCourse: () => response }),
      )
      expect(() => invokeFirstBallDomain('quantizeCourse', {})).toThrow(
        '成立しませんでした',
      )
    }
  })
})

import prefixCases from '../../../../../contracts/state-transition/play_prefix_v2_cases.json'
it('既配布artifactの新v2口へ入力を無変換で渡し既契約の全応答を返す', () => {
  const context: Record<string, unknown> = {}
  runInNewContext(readFileSync(artifactPath, 'utf8'), context)
  vi.stubGlobal('PitchlogDomain', Reflect.get(context, 'PitchlogDomain'))
  const row = prefixCases.cases.find(
    (c) => c.caseId === 'V2-TERMINAL-BB-S0-B3',
  )!
  expect({
    ok: true,
    value: invokeFirstBallDomain(
      'derivePlayPrefixWithContinuation',
      row.request,
    ),
  }).toEqual(row.expected)
})
