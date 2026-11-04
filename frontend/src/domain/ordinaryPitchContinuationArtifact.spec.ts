import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { expect, it } from 'vitest'

const read = (name: string) =>
  JSON.parse(
    readFileSync(
      resolve(process.cwd(), '../contracts/state-transition', name),
      'utf8',
    ),
  )
const candidate = read('ordinary37_continuation_candidate_v1.json')
const bytes = readFileSync(
  resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
)
const declaration = JSON.parse(
  readFileSync(
    resolve(process.cwd(), 'public/domain/pitchlog-domain.json'),
    'utf8',
  ),
)
const context = createContext({})
new Script(bytes.toString('utf8')).runInContext(context, { timeout: 1000 })
const built = context.PitchlogDomain as {
  deriveOrdinaryPitchWithContinuation: (request: string) => string
  deriveOrdinaryPitch: (request: string) => string
}
const invoke = (request: unknown) =>
  JSON.parse(built.deriveOrdinaryPitchWithContinuation(JSON.stringify(request)))

it('宣言SHA一致のビルド済み公開9口を実行する', () => {
  expect(createHash('sha256').update(bytes).digest('hex')).toBe(
    declaration.sha256,
  )
  expect(Object.isFrozen(built)).toBe(true)
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
})

it('全20件の完全期待値をTS実装importなしでartifact経由照合する', () => {
  expect(candidate.cases).toHaveLength(20)
  for (const row of candidate.cases)
    expect(invoke(row.request), row.caseId).toEqual(row.expected.response)
})

it('一般888caseの全T1/今回entryと旧数学口を同じartifactで保持する', () => {
  const rows = [
    ...read('recording_continuation_scope_v1.json').generalStateCases,
    ...read('ordinary_two_strike_foul_candidate_v1.json').generalStateCases,
  ]
  expect(rows).toHaveLength(888)
  for (const row of rows) {
    const request = structuredClone(candidate.cases[2].request)
    request.t1 = {
      ...structuredClone(row.event),
      before: structuredClone(row.before),
    }
    request.prior.after = structuredClone(row.before)
    const actual = invoke(request)
    const { historyContext, ...expectedT1 } = row.expectedT1
    expect(actual.ok, row.caseId).toBe(true)
    expect(actual.value.t1, row.caseId).toEqual(expectedT1)
    expect(actual.value.newHistoryEntry, row.caseId).toEqual(historyContext[0])
    expect(actual.value.previousPrefixRef).toEqual(request.prefixRef)
    expect(actual.value.nextPrefixRef).toEqual({
      ...request.prefixRef,
      length: '9',
    })
    expect(actual.value.t1).not.toHaveProperty('historyContext')
    expect(
      JSON.parse(
        built.deriveOrdinaryPitch(
          JSON.stringify({ ...request.t1, history: { stack: [] } }),
        ),
      ),
    ).toEqual({ ok: true, value: row.expectedT1 })
  }
})
