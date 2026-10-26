import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { describe, expect, it } from 'vitest'
import { domainOperations } from './publicApi'

const cases = JSON.parse(
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
function api(source: string): typeof domainOperations {
  const context = createContext({})
  new Script(source).runInContext(context, { timeout: 1000 })
  return context.PitchlogDomain as typeof domainOperations
}
const built = api(artifact)

describe.each([
  { name: 'TS', invoke: domainOperations.validateInitialGameRoster },
  { name: '同artifact', invoke: built.validateInitialGameRoster },
])('$nameの初期名簿', ({ invoke }) => {
  it.each(cases)('$id 全値を一致させる', ({ request, expected }) => {
    expect(JSON.parse(invoke(JSON.stringify(request)))).toEqual(expected)
  })
})

it('artifactのDH整合guard変異を実反例が検出する', () => {
  const from = '!==10n'
  expect(artifact.split(from)).toHaveLength(2)
  const mutant = api(artifact.replace(from, '!==9n'))
  const normal = cases.find((item) => item.id === 'NORMAL-DH-true')!
  expect(
    JSON.parse(
      mutant.validateInitialGameRoster(JSON.stringify(normal.request)),
    ),
  ).not.toEqual(normal.expected)
})

it.each(['away', 'home'] as const)(
  '実artifactでも%s整数不正より対side/同entry形状を優先する',
  (side) => {
    const other = side === 'away' ? 'home' : 'away'
    const normal = cases.find((item) => item.id === 'NORMAL-DH-false')!
    for (const same of [false, true]) {
      const input = structuredClone(normal.request) as Record<
        string,
        { entries: Array<Record<string, unknown>> }
      >
      input[side]!.entries[0]!.batting_order = '01'
      delete input[same ? side : other]!.entries[0]!.player_id
      expect(
        JSON.parse(built.validateInitialGameRoster(JSON.stringify(input))),
      ).toEqual({ ok: false, error: { code: 'INVALID_REQUEST' } })
    }
  },
)
