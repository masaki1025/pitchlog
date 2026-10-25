import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as state from './state'
import * as continuation from './firstPitchContinuation'

import './entry'
import { domainOperations } from './publicApi'

describe('ドメイン公開口の疎通操作', () => {
  it('操作表を凍結し、公開操作を疎通・一球・限定T2・初期名簿だけにする', () => {
    expect(Object.isFrozen(domainOperations)).toBe(true)
    expect(Object.keys(domainOperations)).toEqual([
      'ping',
      'deriveState',
      'deriveFirstPitchWithContinuation',
      'validateInitialGameRoster',
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

const combinedCases = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/t2_first_pitch_continuation_cases_v1.json',
    ),
    'utf8',
  ),
).cases

afterEach(() => vi.restoreAllMocks())

describe('単一T1評価と限定T2の接続', () => {
  it('各有効要求のT1を一回だけ評価し、その同一before/board/DerivedをT2へ渡す', () => {
    const t1 = vi.spyOn(state, 'derive')
    const t2 = vi.spyOn(continuation, 'evaluateFirstPitchContinuation')
    for (const item of combinedCases) {
      t1.mockClear()
      t2.mockClear()
      expect(
        JSON.parse(
          domainOperations.deriveFirstPitchWithContinuation(
            JSON.stringify(item.request),
          ),
        ),
      ).toEqual(item.expected)
      expect(t1).toHaveBeenCalledTimes(1)
      if (item.kind === 'existing-T1-failure') expect(t2).not.toHaveBeenCalled()
      else {
        expect(t2).toHaveBeenCalledTimes(1)
        expect(t2.mock.calls[0]![0]).toBe(t1.mock.calls[0]![0])
        expect(t2.mock.calls[0]![1]).toBe(t1.mock.calls[0]![1])
        expect(t2.mock.calls[0]![2]).toBe(t1.mock.results[0]!.value)
      }
    }
  })
  it('T2故障を新操作固有の未評価へ閉じ、全T1値を返しても保存成功にしない', () => {
    vi.spyOn(continuation, 'evaluateFirstPitchContinuation').mockImplementation(
      () => {
        throw new Error('試験だけのT2故障')
      },
    )
    const item = combinedCases[0]
    const result = JSON.parse(
      domainOperations.deriveFirstPitchWithContinuation(
        JSON.stringify(item.request),
      ),
    )
    expect(result).toEqual({
      ok: false,
      error: { code: 'T2_NOT_EVALUATED' },
      value: {
        t1: item.expected.value.t1,
        t2: { kind: 'not-evaluated', reason: 'evaluation-unavailable' },
      },
    })
    expect(
      JSON.parse(domainOperations.deriveState(JSON.stringify(item.request.t1))),
    ).toEqual({ ok: true, value: item.expected.value.t1 })
  })
})
