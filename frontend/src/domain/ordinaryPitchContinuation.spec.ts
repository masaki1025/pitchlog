import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { domainOperations } from './publicApi'
import { inspectDomainDirectory } from '../../scripts/domain-checks/check'
import { inspectTypedDomainDirectory } from '../../scripts/domain-checks/typedCheck'

const candidate = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/ordinary37_continuation_candidate_v1.json',
    ),
    'utf8',
  ),
)
const invoke = (request: unknown) =>
  JSON.parse(
    domainOperations.deriveOrdinaryPitchWithContinuation(
      JSON.stringify(request),
    ),
  )
const copy = <T>(value: T): T => structuredClone(value)
const rejected = { ok: false, error: { code: 'T2_NOT_EVALUATED' } }

describe('通常37の有限prefix T1/T2接続', () => {
  it('候補20件を省略せず完全responseで照合する', () => {
    expect(candidate.cases).toHaveLength(20)
    for (const row of candidate.cases) {
      const before = JSON.stringify(row.request)
      expect(invoke(row.request), row.caseId).toEqual(row.expected.response)
      expect(JSON.stringify(row.request)).toBe(before)
    }
  })

  it('同じ純計算を再評価しても同じ参照/同じ1entryを返す（保存冪等性の代替ではない）', () => {
    const request = copy(candidate.cases[1].request)
    expect(invoke(request)).toEqual(invoke(request))
    expect(invoke(request).value.nextPrefixRef.length).toBe('2')
    expect(invoke(request).value).not.toHaveProperty('historyContext')
    expect(invoke(request).value.t1).not.toHaveProperty('historyContext')
  })

  it('未知/余剰/欠落形、非正準UUID/水位を閉拒否する', () => {
    const base = candidate.cases[1].request
    const requests = [
      { ...copy(base), extra: true },
      { ...copy(base), version: '2' },
      { ...copy(base), t1: { ...copy(base.t1), history: { stack: [] } } },
      { ...copy(base), prior: { ...copy(base.prior), extra: true } },
    ]
    for (const [key, value] of [
      ['tenantId', 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'],
      ['gameId', 'x'],
      ['generation', ''],
      ['generation', 'x'.repeat(129)],
      ['length', '-1'],
      ['length', '01'],
      ['length', 1],
    ] as const) {
      requests.push({
        ...copy(base),
        prefixRef: { ...copy(base.prefixRef), [key]: value },
      })
    }
    for (const request of requests)
      expect(invoke(request)).toEqual({
        ok: false,
        error: { code: 'INVALID_REQUEST' },
      })
    expect(
      JSON.parse(domainOperations.deriveOrdinaryPitchWithContinuation('{')),
    ).toEqual({ ok: false, error: { code: 'INVALID_JSON' } })
  })

  it('D4 opaqueを整数化せず、ref/rules/after/T2の付替えを拒否する', () => {
    const base = copy(candidate.cases[1].request)
    base.prefixRef.generation = 'writer-generation-A'
    base.prior.prefixRef.generation = 'writer-generation-A'
    expect(invoke(base).ok).toBe(true)
    for (const key of ['tenantId', 'gameId', 'generation', 'length']) {
      const request = copy(base)
      request.prior.prefixRef[key] =
        key === 'length'
          ? '3'
          : key === 'generation'
            ? 'other'
            : '33333333-3333-4333-8333-333333333333'
      expect(invoke(request)).toEqual(rejected)
    }
    const unknown = copy(base)
    unknown.prior.t2.basis.extra = true
    expect(invoke(unknown)).toEqual(rejected)
    for (const key of [
      'regulationInnings',
      'inning',
      'half',
      'tiebreakActive',
      'configuredExtensionLimit',
      'drawBranch',
      'priorOpen',
    ]) {
      const request = copy(base)
      request.prior.t2.basis[key] =
        key === 'priorOpen' || key === 'tiebreakActive' ? false : 'mismatch'
      if (key === 'tiebreakActive') request.prior.t2.basis[key] = true
      expect(invoke(request), key).toEqual(rejected)
    }
  })

  it('DRAW01..04相関とcold全段を検査し、終端/lockをnoendへ落とさない', () => {
    for (const change of [
      { extensionLimit: '8' },
      { coldConditions: [{ pointDifference: '10', startInning: '10' }] },
      {
        tiebreak: {
          startInning: '9',
          runnerPlacement: '無死一・二塁',
          leadoffRule: '継続打順',
        },
      },
      {
        extensionLimit: '12',
        tiebreak: {
          startInning: '13',
          runnerPlacement: '無死一・二塁',
          leadoffRule: '継続打順',
        },
      },
    ]) {
      const request = copy(candidate.cases[1].request)
      Object.assign(request.rules, change)
      request.prior.rules = copy(request.rules)
      expect(invoke(request)).toEqual(rejected)
    }
    const zero = copy(candidate.cases[1].request)
    zero.rules.coldConditions = [{ pointDifference: '0', startInning: '5' }]
    zero.prior.rules = copy(zero.rules)
    expect(invoke(zero)).toEqual({
      ok: false,
      error: { code: 'INVALID_DECIMAL_INTEGER' },
    })
    const reordered = copy(candidate.cases[7].request)
    reordered.rules.coldConditions.reverse()
    reordered.prior.rules = copy(reordered.rules)
    expect(invoke(reordered).value.t2.basis.coldBranches).toEqual([
      'COLD-01',
      'COLD-01',
    ])
  })

  it('既数学37の全出力を再計算せず保持し、旧fullstack/初球拒否を変えない', () => {
    const ordinary = JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          '../contracts/state-transition/ordinary_pitch_vectors_v1.json',
        ),
        'utf8',
      ),
    ).cases
    const foul = JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          '../contracts/state-transition/ordinary_two_strike_foul_candidate_v1.json',
        ),
        'utf8',
      ),
    ).cases
    expect([...ordinary, ...foul]).toHaveLength(37)
    for (const row of [...ordinary, ...foul]) {
      const request = copy(candidate.cases[1].request)
      const { history, ...t1 } = copy(row.request)
      expect(history.stack).toEqual([])
      request.t1 = t1
      request.prior.after = copy(t1.before)
      const actual = invoke(request)
      const { historyContext, ...expectedT1 } = copy(row.expected.value)
      expect(actual.ok, row.caseId).toBe(true)
      expect(actual.value.t1).toEqual(expectedT1)
      expect(actual.value.newHistoryEntry).toEqual(historyContext[0])
      expect(actual.value).not.toHaveProperty('historyContext')
      expect(
        JSON.parse(
          domainOperations.deriveOrdinaryPitch(JSON.stringify(row.request)),
        ),
      ).toEqual(row.expected)
    }
  })

  it('一般888数学caseのafter/flags/差分を全値保持し、前回T2の同位置へ束縛する', () => {
    const ordinary = JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          '../contracts/state-transition/recording_continuation_scope_v1.json',
        ),
        'utf8',
      ),
    ).generalStateCases
    const foul = JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          '../contracts/state-transition/ordinary_two_strike_foul_candidate_v1.json',
        ),
        'utf8',
      ),
    ).generalStateCases
    expect([...ordinary, ...foul]).toHaveLength(888)
    for (const row of [...ordinary, ...foul]) {
      const request = copy(candidate.cases[2].request)
      request.t1 = { ...copy(row.event), before: copy(row.before) }
      request.prior.after = copy(row.before)
      const actual = invoke(request)
      const { historyContext, ...t1 } = copy(row.expectedT1)
      expect(actual.ok, row.caseId).toBe(true)
      expect(actual.value.t1, row.caseId).toEqual(t1)
      expect(actual.value.newHistoryEntry, row.caseId).toEqual(
        historyContext[0],
      )
      expect(actual.value.nextPrefixRef).toEqual({
        ...request.prefixRef,
        length: '9',
      })
    }
  })

  it('旧初球T2を対応afterへ正しく束縛でき、JSON key順に依存しない', () => {
    const rows = JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          '../contracts/state-transition/t2_first_pitch_continuation_cases_v1.json',
        ),
        'utf8',
      ),
    ).cases
    const legacy = rows.find(
      (row: {
        expected: {
          ok: boolean
          value?: {
            t2?: {
              basis?: {
                regulation?: { regulation_innings?: string }
                extra_and_draw?: { configured_extension_limit?: string | null }
              }
            }
          }
        }
      }) =>
        row.expected.ok &&
        row.expected.value?.t2?.basis?.regulation?.regulation_innings === '9' &&
        row.expected.value.t2.basis.extra_and_draw
          ?.configured_extension_limit === null,
    ).expected.value.t2
    const request = copy(candidate.cases[1].request)
    request.prior.t2 = legacy
    expect(invoke(request)).toEqual(candidate.cases[1].expected.response)
    request.t1.before.stateFields = Object.fromEntries(
      Object.entries(request.t1.before.stateFields).reverse(),
    )
    expect(invoke(request)).toEqual(candidate.cases[1].expected.response)
  })

  it('既domainの禁止構文/number型検査を緩めずに通る', () => {
    const directory = resolve(process.cwd(), 'src/domain')
    expect(inspectDomainDirectory(directory)).toEqual([])
    expect(
      inspectTypedDomainDirectory(
        directory,
        resolve(process.cwd(), 'tsconfig.app.json'),
      ),
    ).toEqual([])
  })
})
