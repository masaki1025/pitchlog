import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { describe, expect, it } from 'vitest'

import { domainOperations } from './publicApi'

type Json = null | boolean | number | string | Json[] | { [key: string]: Json }
const boundary = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../docs/features/tsk544-t1-state-calculation/first-pitch-boundary.json',
    ),
    'utf8',
  ),
)
const errorCodes: string[] = boundary.response_schema.oneOf.find(
  (branch: { properties: { ok: { const: boolean } } }) =>
    !branch.properties.ok.const,
).properties.error.properties.code.enum

/** 全異常応答を承認済みの閉じたenvelope/enumへ照合する。 */
function parseResponse(text: string) {
  const value = JSON.parse(text)
  if (value.ok === false) {
    expect(Object.keys(value).sort()).toEqual(['error', 'ok'])
    expect(Object.keys(value.error)).toEqual(['code'])
    expect(errorCodes).toContain(value.error.code)
  }
  return value
}

const contract = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/state_transition_contract_v1.json',
    ),
    'utf8',
  ),
)
const formal = contract.cases.find(
  (item: { caseId: string }) => item.caseId === 'ST-MATRIX-0529a0eb116d64a9',
)
if (!formal) throw new Error('正式一球caseがない')

/** 契約整数の表現だけを既ABIの十進文字列へ写す。計算はしない。 */
function decimalize(value: Json): Json {
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new Error('安全整数でない契約値')
    return value.toString()
  }
  if (Array.isArray(value)) return value.map(decimalize)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, decimalize(item)]),
    )
  }
  return value
}

type Request = {
  eventKind: string
  resultId: string
  pitchEventKind: string
  before: {
    stateFields: Record<string, Json>
    scoreboard: Record<string, Json>
  }
}

/** 異常系試験だけで構造を変更するための検査済みobject参照。 */
function objectAt(value: unknown, path: string[]): Record<string, unknown> {
  function record(item: unknown): Record<string, unknown> {
    if (item === null || typeof item !== 'object' || Array.isArray(item)) {
      throw new Error('試験入力がobjectでない')
    }
    return item as Record<string, unknown>
  }
  let current = record(value)
  for (const part of path) current = record(current[part])
  return current
}

function request(): Request {
  return {
    eventKind: formal.inputCoordinate.eventKind,
    resultId: formal.inputCoordinate.resultId,
    pitchEventKind: formal.inputCoordinate['event.perPitch.pitchEventKind'],
    before: decimalize(formal.historyInput.before) as Request['before'],
  }
}
const expected = decimalize({
  countEffect: formal.expected.countEffect,
  plateAppearanceEnded: formal.expected.plateAppearanceEnded,
  batterDestination: formal.expected.batterDestination,
  runnerDefaultAdvance: formal.expected.runnerDefaultAdvance,
  outEffect: formal.expected.outEffect,
  statFlags: formal.expected.statFlags,
  after: formal.historyInput.after,
  historyContext: formal.expected.historyContext,
})
const artifact = readFileSync(
  resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
  'utf8',
)

/** ビルド済みartifactを実行する。TSの導出関数を代替実装しない。 */
function artifactOperation(source: string): (input: string) => string {
  const context = createContext({})
  new Script(source).runInContext(context, { timeout: 1000 })
  const api = context.PitchlogDomain as typeof domainOperations
  expect(Object.isFrozen(api)).toBe(true)
  return api.deriveState
}

const implementations = [
  { name: 'TS公開入口', invoke: domainOperations.deriveState },
  { name: 'ビルド済みartifact', invoke: artifactOperation(artifact) },
]

describe.each(implementations)('$name の最初の一球', ({ invoke }) => {
  it('正式caseの六効果・全23flag・after・履歴を全値比較する', () => {
    expect(parseResponse(invoke(JSON.stringify(request())))).toEqual({
      ok: true,
      value: expected,
    })
    expect(Object.keys(formal.expected.statFlags)).toHaveLength(23)
  })

  it('実入力を変更せず同じ入力は同じ結果を返す', () => {
    const input = request()
    const original = JSON.stringify(input)
    expect(invoke(original)).toBe(invoke(original))
    expect(JSON.stringify(input)).toBe(original)
  })

  it('他の正式結果IDを成功扱いにしない', () => {
    const ids = new Set<string>(
      contract.matrixRows.map((row: { resultId: string }) => row.resultId),
    )
    ids.delete('batting-result.ball')
    expect(ids.size).toBeGreaterThan(0)
    for (const resultId of ids) {
      const input = { ...request(), resultId }
      expect(parseResponse(invoke(JSON.stringify(input)))).toEqual({
        ok: false,
        error: { code: 'UNSUPPORTED_T1_SCOPE' },
      })
    }
  })

  it.each(['bottom', 'unknown-half'])(
    '攻守%sを一球成功へ代替しない',
    (half) => {
      const input = request()
      input.before.stateFields['state.half'] = half
      expect(parseResponse(invoke(JSON.stringify(input))).ok).toBe(false)
    },
  )

  it.each([
    ['state.count.balls', '1'],
    ['state.count.strikes', '1'],
    ['state.outs', '1'],
    ['state.inning', '2'],
    ['state.battingOrder', '2'],
    ['state.runners', 'first'],
    ['state.gameEnded', true],
    ['state.tiebreakActive', true],
  ])('未対応状態%sを適用しない', (key, value) => {
    const input = request()
    objectAt(input, ['before', 'stateFields'])[key as string] = value
    expect(parseResponse(invoke(JSON.stringify(input)))).toEqual({
      ok: false,
      error: { code: 'UNSUPPORTED_T1_SCOPE' },
    })
  })

  it.each(['0\n', '0\r\n', '00', '-0', '0 ', '1e0', 0, null])(
    '非canonical整数%jを拒否する',
    (value) => {
      const input = request()
      objectAt(input, ['before', 'stateFields'])['state.count.balls'] = value
      expect(parseResponse(invoke(JSON.stringify(input)))).toEqual({
        ok: false,
        error: { code: 'INVALID_DECIMAL_INTEGER' },
      })
    },
  )

  it.each([
    ['state.half', 'unknown-half'],
    ['state.gameEnded', 'false'],
    ['state.tiebreakActive', 0],
    ['state.runners', null],
  ])('不正型%sは閉じた既存errorで拒否する', (key, value) => {
    const input = request()
    objectAt(input, ['before', 'stateFields'])[key as string] = value
    expect(parseResponse(invoke(JSON.stringify(input)))).toEqual({
      ok: false,
      error: { code: 'INVALID_REQUEST' },
    })
  })

  it('全objectの余剰fieldと必須field欠落を拒否する', () => {
    const paths = [
      [],
      ['before'],
      ['before', 'stateFields'],
      ['before', 'scoreboard'],
      ['before', 'stateFields', 'state.score'],
      ['before', 'scoreboard', 'inningScores'],
    ]
    for (const path of paths) {
      const input = request()
      const target = objectAt(input, path)
      target.unexpected = true
      expect(parseResponse(invoke(JSON.stringify(input)))).toEqual({
        ok: false,
        error: { code: 'INVALID_REQUEST' },
      })
      delete target.unexpected
      for (const key of Object.keys(target)) {
        const bad = structuredClone(input)
        const object = objectAt(bad, path)
        delete object[key]
        expect(parseResponse(invoke(JSON.stringify(bad)))).toEqual({
          ok: false,
          error: { code: 'INVALID_REQUEST' },
        })
      }
    }
  })

  it('欠落投影を0で補わず、入力済み非0投影も未対応として拒否する', () => {
    const input = request()
    delete objectAt(input, ['before']).scoreboard
    expect(parseResponse(invoke(JSON.stringify(input))).ok).toBe(false)
    const other = request()
    other.before.scoreboard.hits = '1'
    expect(parseResponse(invoke(JSON.stringify(other)))).toEqual({
      ok: false,
      error: { code: 'UNSUPPORTED_T1_SCOPE' },
    })
  })
})

it.each([
  ['ballDelta:1n', 'ballDelta:2n'],
  ['与四球:!1', '与四球:!0'],
])('実artifactの非等価変異%sを正式caseが検出する', (before, after) => {
  expect(artifact.split(before)).toHaveLength(2)
  const mutant = artifactOperation(artifact.replace(before, after))
  expect(parseResponse(mutant(JSON.stringify(request())))).not.toEqual({
    ok: true,
    value: expected,
  })
})

const continuationCases = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/t2_first_pitch_continuation_cases_v1.json',
    ),
    'utf8',
  ),
).cases as Array<{
  caseId: string
  request: { t1: Request; rules: Record<string, unknown> }
  expected: unknown
}>
function combinedArtifactOperation(): (input: string) => string {
  const context = createContext({})
  new Script(artifact).runInContext(context, { timeout: 1000 })
  return (context.PitchlogDomain as typeof domainOperations)
    .deriveFirstPitchWithContinuation
}

describe.each([
  {
    name: 'TS単一評価接続',
    invoke: domainOperations.deriveFirstPitchWithContinuation,
  },
  { name: '同一ビルド済みartifact接続', invoke: combinedArtifactOperation() },
])('$name', ({ invoke }) => {
  it.each(continuationCases)(
    '$caseId 契約全値と一致する',
    ({ request: input, expected: result }) => {
      expect(JSON.parse(invoke(JSON.stringify(input)))).toEqual(result)
    },
  )
  it.each(['after', 't2', 'binding', 'derived'])(
    'caller供給%sを拒否する',
    (key) => {
      expect(
        JSON.parse(
          invoke(
            JSON.stringify({ ...continuationCases[0]!.request, [key]: {} }),
          ),
        ),
      ).toEqual({ ok: false, error: { code: 'INVALID_REQUEST' } })
    },
  )
  it('新操作でも既4codeを維持しpartialを成功として復元しない', () => {
    const input = structuredClone(continuationCases[0]!.request)
    expect(JSON.parse(invoke('{'))).toEqual({
      ok: false,
      error: { code: 'INVALID_JSON' },
    })
    expect(JSON.parse(invoke('{}'))).toEqual({
      ok: false,
      error: { code: 'INVALID_REQUEST' },
    })
    input.t1.before.stateFields['state.count.balls'] = '00'
    expect(JSON.parse(invoke(JSON.stringify(input)))).toEqual({
      ok: false,
      error: { code: 'INVALID_DECIMAL_INTEGER' },
    })
    const partial = JSON.parse(
      invoke(
        JSON.stringify(
          continuationCases.find((c) => c.caseId === 'VALID-R8')!.request,
        ),
      ),
    )
    expect(partial.ok).toBe(false)
    expect(partial.error.code).toBe('T2_NOT_EVALUATED')
    expect(partial.value.t1).toEqual(expected)
    expect(Object.keys(partial.value.t2).sort()).toEqual(['kind', 'reason'])
  })
})
