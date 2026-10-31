import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { describe, expect, it } from 'vitest'
import { domainOperations } from './publicApi'

interface CombinedCase {
  caseId: string
  request: {
    t1: {
      eventKind: string
      resultId: string
      pitchEventKind: string
      before: {
        stateFields: Record<string, unknown>
        scoreboard: Record<string, unknown>
      }
    }
    rules: Record<string, unknown>
  }
  expected: unknown
}
const continuationCases = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/t2_first_pitch_continuation_cases_v1.json',
    ),
    'utf8',
  ),
).cases as CombinedCase[]
const rosterCases = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/initial_game_roster_cases_v1.json',
    ),
    'utf8',
  ),
).cases as Array<{ id: string; request: unknown; expected: unknown }>
const artifact = readFileSync(
  resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
  'utf8',
)
const context = createContext({})
new Script(artifact).runInContext(context, { timeout: 1000 })
const built = context.PitchlogDomain as typeof domainOperations
const first = continuationCases[0]!
const expectedFirst = first.expected as {
  ok: true
  value: { t1: unknown; t2: unknown }
}

it('単一artifactが承認済み11口を保持する', () => {
  expect(Object.keys(built)).toEqual([
    'ping',
    'deriveState',
    'deriveOrdinaryPitch',
    'deriveTerminalPitch',
    'deriveStrikeoutPitch',
    'derivePlayPrefixWithContinuation',
    'deriveLineupPlayPrefixWithContinuation',
    'deriveFirstPitchWithContinuation',
    'deriveOrdinaryPitchWithContinuation',
    'validateInitialGameRoster',
    'quantizeCourse',
  ])
  expect(Object.isFrozen(built)).toBe(true)
  expect(JSON.parse(built.ping('{"value":"9007199254740993"}'))).toEqual({
    ok: true,
    value: '9007199254740993',
  })
  expect(
    JSON.parse(built.deriveState(JSON.stringify(first.request.t1))),
  ).toEqual({
    ok: true,
    value: expectedFirst.value.t1,
  })
  expect(
    JSON.parse(
      built.deriveOrdinaryPitch(
        JSON.stringify({ ...first.request.t1, history: { stack: [] } }),
      ),
    ),
  ).toEqual({ ok: true, value: expectedFirst.value.t1 })
  expect(
    JSON.parse(
      built.validateInitialGameRoster(JSON.stringify(rosterCases[0]!.request)),
    ),
  ).toEqual(rosterCases[0]!.expected)
})

describe.each([
  {
    name: 'TS既combined body',
    invoke: domainOperations.deriveFirstPitchWithContinuation,
  },
  {
    name: '同一ビルド済みartifact',
    invoke: built.deriveFirstPitchWithContinuation,
  },
])('$name', ({ invoke }) => {
  it.each(continuationCases)(
    '$caseId 契約全値を保持する',
    ({ request, expected }) => {
      expect(JSON.parse(invoke(JSON.stringify(request)))).toEqual(expected)
    },
  )
  it.each(['after', 't2', 'binding', 'derived'])(
    'caller供給%sを拒否する',
    (key) => {
      expect(
        JSON.parse(invoke(JSON.stringify({ ...first.request, [key]: {} }))),
      ).toEqual({ ok: false, error: { code: 'INVALID_REQUEST' } })
    },
  )
  it('既4code・未評価T2の非成功を維持する', () => {
    expect(JSON.parse(invoke('{'))).toEqual({
      ok: false,
      error: { code: 'INVALID_JSON' },
    })
    expect(JSON.parse(invoke('{}'))).toEqual({
      ok: false,
      error: { code: 'INVALID_REQUEST' },
    })
    const invalid = structuredClone(first.request)
    invalid.t1.before.stateFields['state.count.balls'] = '00'
    expect(JSON.parse(invoke(JSON.stringify(invalid)))).toEqual({
      ok: false,
      error: { code: 'INVALID_DECIMAL_INTEGER' },
    })
    const partial = JSON.parse(
      invoke(
        JSON.stringify(
          continuationCases.find((value) => value.caseId === 'VALID-R8')!
            .request,
        ),
      ),
    )
    expect(partial.ok).toBe(false)
    expect(partial.error.code).toBe('T2_NOT_EVALUATED')
    expect(partial.value.t1).toEqual(expectedFirst.value.t1)
    expect(Object.keys(partial.value.t2).sort()).toEqual(['kind', 'reason'])
  })
})
