import { describe, expect, it } from 'vitest'

import './entry'
import { domainOperations } from './publicApi'

describe('ドメイン公開口の疎通操作', () => {
  it('操作表を凍結し、公開操作を既存5口と量子化に限定する', () => {
    expect(Object.isFrozen(domainOperations)).toBe(true)
    expect(Object.keys(domainOperations)).toEqual([
      'ping',
      'deriveState',
      'deriveOrdinaryPitch',
      'deriveFirstPitchWithContinuation',
      'validateInitialGameRoster',
      'quantizeCourse',
    ])
  })

  it('build 入口が同じ凍結済み公開表を globalThis に置く', () => {
    const domainGlobal = globalThis as typeof globalThis & {
      PitchlogDomain?: typeof domainOperations
    }
    expect(domainGlobal.PitchlogDomain).toBe(domainOperations)
    expect(Object.isFrozen(domainGlobal.PitchlogDomain)).toBe(true)
  })

  it.each(['0', '-1', '9007199254740993', '18446744073709551621'])(
    '十進文字列 %s を JSON 文字列のまま往復する',
    (value) => {
      const response = domainOperations.ping(JSON.stringify({ value }))
      expect(response).toBe(JSON.stringify({ ok: true, value }))
    },
  )

  it('不正な JSON と不正な入力を構造化エラーで返す', () => {
    expect(domainOperations.ping('{')).toBe(
      '{"ok":false,"error":{"code":"INVALID_JSON"}}',
    )
    expect(domainOperations.ping('{"value":1}')).toBe(
      '{"ok":false,"error":{"code":"INVALID_DECIMAL_INTEGER"}}',
    )
    expect(domainOperations.ping('{"value":"-0"}')).toBe(
      '{"ok":false,"error":{"code":"INVALID_DECIMAL_INTEGER"}}',
    )
    expect(domainOperations.ping('{"value":"1","other":"2"}')).toBe(
      '{"ok":false,"error":{"code":"INVALID_REQUEST"}}',
    )
  })
})
