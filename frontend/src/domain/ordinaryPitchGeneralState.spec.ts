import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { inspectDomainDirectory } from '../../scripts/domain-checks/check'
import { inspectTypedDomainDirectory } from '../../scripts/domain-checks/typedCheck'
import { domainOperations } from './publicApi'
const scope = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/recording_continuation_scope_v1.json',
    ),
    'utf8',
  ),
)
const vectors = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/ordinary_pitch_vectors_v1.json',
    ),
    'utf8',
  ),
)
const invoke = (request: unknown) =>
  JSON.parse(domainOperations.deriveOrdinaryPitch(JSON.stringify(request)))
const general = () => ({
  ...structuredClone(scope.generalStateCases[0].event),
  before: structuredClone(scope.generalStateCases[0].before),
  history: { stack: [] },
})

it('33×3out×8塁配置の792候補を全8member/全23flag/全履歴/afterで完全比較する', () => {
  expect(scope.generalStateCases).toHaveLength(792)
  for (const row of scope.generalStateCases) {
    const request = { ...row.event, before: row.before, history: { stack: [] } }
    expect(invoke(request), row.caseId).toEqual({
      ok: true,
      value: row.expectedT1,
    })
  }
})
it('回・表裏・得点・打順・TB・scoreboardを固定せず全値保持する', () => {
  const start = general()
  for (const half of ['top', 'bottom'])
    for (const inning of ['1', '7', '9', '10', '9999999999999999999999999'])
      for (const order of ['1', '5', '9'])
        for (const tb of [false, true]) {
          const request = structuredClone(start)
          Object.assign(request.before.stateFields, {
            'state.half': half,
            'state.inning': inning,
            'state.battingOrder': order,
            'state.tiebreakActive': tb,
            'state.score': { home: '9999999999999999999999999', away: '11' },
          })
          Object.assign(request.before.scoreboard, {
            inningScores: { home: '3', away: '4' },
            hits: '12',
            errors: '2',
            strikeouts: '9',
            walks: '7',
          })
          const original = JSON.stringify(request),
            actual = invoke(request)
          expect(actual.ok).toBe(true)
          expect(actual.value.after).toEqual({
            ...request.before,
            stateFields: {
              ...request.before.stateFields,
              'state.count.strikes': '1',
            },
          })
          expect(actual.value.statFlags).toEqual(
            scope.generalStateCases[0].expectedT1.statFlags,
          )
          expect(JSON.stringify(request)).toBe(original)
        }
})
it('一般状態の履歴tailを全件・全値・順序のままpush後へ保持する', () => {
  const request = general(),
    tail = structuredClone(
      vectors.historyTailCases[0].second.request.history.stack,
    )
  request.history.stack = tail
  const actual = invoke(request)
  expect(actual.ok).toBe(true)
  expect(actual.value.historyContext.slice(1)).toEqual(tail)
  expect(actual.value.historyContext[0]).toEqual(
    scope.generalStateCases[0].expectedT1.historyContext[0],
  )
})
describe('一般化後も有効な局所状態だけを受ける', () => {
  it.each([
    ['state.inning', '0'],
    ['state.inning', '-1'],
    ['state.outs', '-1'],
    ['state.outs', '3'],
    ['state.battingOrder', '0'],
    ['state.battingOrder', '10'],
    ['state.runners', 'unknown'],
    ['state.gameEnded', true],
  ])('不正state %s=%sを拒否する', (field, value) => {
    const r = general()
    r.before.stateFields[field] = value
    expect(invoke(r)).toEqual({
      ok: false,
      error: { code: 'UNSUPPORTED_T1_SCOPE' },
    })
  })
  it.each(['hits', 'errors', 'strikeouts', 'walks'])(
    '負のscoreboard %sを拒否する',
    (field) => {
      const r = general()
      r.before.scoreboard[field] = '-1'
      expect(invoke(r)).toEqual({
        ok: false,
        error: { code: 'UNSUPPORTED_T1_SCOPE' },
      })
    },
  )
  it('負の得点/イニング得点、未知half、boolean型違い、非正準十進を成功にしない', () => {
    const r1 = general()
    r1.before.stateFields['state.score'].home = '-1'
    expect(invoke(r1).ok).toBe(false)
    const r2 = general()
    r2.before.scoreboard.inningScores.away = '-1'
    expect(invoke(r2).ok).toBe(false)
    const r3 = general()
    r3.before.stateFields['state.half'] = 'sideways'
    expect(invoke(r3)).toEqual({
      ok: false,
      error: { code: 'INVALID_REQUEST' },
    })
    const r4 = general()
    r4.before.stateFields['state.tiebreakActive'] = 'false'
    expect(invoke(r4)).toEqual({
      ok: false,
      error: { code: 'INVALID_REQUEST' },
    })
    const r5 = general()
    r5.before.stateFields['state.inning'] = '01'
    expect(invoke(r5)).toEqual({
      ok: false,
      error: { code: 'INVALID_DECIMAL_INTEGER' },
    })
  })
})
it('旧deriveState/初球公開口の有効状態を無断拡張しない', () => {
  for (const change of [
    { 'state.half': 'bottom' },
    { 'state.outs': '1' },
    { 'state.runners': 'first' },
    { 'state.inning': '2' },
    { 'state.battingOrder': '2' },
    { 'state.tiebreakActive': true },
    { 'state.score': { home: '1', away: '0' } },
  ]) {
    const request = structuredClone(
      vectors.cases.find(
        (x: {
          request: {
            resultId: string
            before: { stateFields: Record<string, unknown> }
          }
        }) =>
          x.request.resultId === 'batting-result.ball' &&
          x.request.before.stateFields['state.count.balls'] === '0' &&
          x.request.before.stateFields['state.count.strikes'] === '0',
      ).request,
    )
    delete request.history
    Object.assign(request.before.stateFields, change)
    expect(
      JSON.parse(domainOperations.deriveState(JSON.stringify(request))),
    ).toEqual({ ok: false, error: { code: 'UNSUPPORTED_T1_SCOPE' } })
    expect(
      JSON.parse(
        domainOperations.deriveFirstPitchWithContinuation(
          JSON.stringify({
            t1: request,
            rules: {
              regulationInnings: '9',
              coldConditions: [],
              extensionLimit: '9',
              tiebreak: null,
              dh: true,
            },
          }),
        ),
      ).ok,
    ).toBe(false)
  }
})
it('未実装の終端球/2Sファウルと未知結果は計算成功へ補完しない', () => {
  for (const [resultId, balls, strikes] of [
    ['batting-result.ball', '3', '1'],
    ['batting-result.called-pitch', '0', '2'],
    ['batting-result.swinging-strike', '1', '2'],
    ['batting-result.k3', '2', '2'],
    ['batting-result.homerun', '0', '0'],
  ]) {
    const request = general()
    request.resultId = resultId
    request.before.stateFields['state.count.balls'] = balls
    request.before.stateFields['state.count.strikes'] = strikes
    expect(invoke(request)).toEqual({
      ok: false,
      error: { code: 'UNSUPPORTED_T1_SCOPE' },
    })
  }
})
it('既構文/型拒否を変えずnumber/禁止構文を追加しない', () => {
  const directory = resolve(process.cwd(), 'src/domain')
  expect(inspectDomainDirectory(directory)).toEqual([])
  expect(
    inspectTypedDomainDirectory(
      directory,
      resolve(process.cwd(), 'tsconfig.app.json'),
    ),
  ).toEqual([])
})

const foulCandidates = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/ordinary_two_strike_foul_candidate_v1.json',
    ),
    'utf8',
  ),
)
it('旧33不変に加え、明示通常非バントS2ファウル4個と一般96例を全値照合する', () => {
  expect(foulCandidates.cases).toHaveLength(4)
  expect(foulCandidates.generalStateCases).toHaveLength(96)
  for (const row of foulCandidates.cases)
    expect(invoke(row.request), row.caseId).toEqual(row.expected)
  for (const row of foulCandidates.generalStateCases)
    expect(
      invoke({ ...row.event, before: row.before, history: { stack: [] } }),
      row.caseId,
    ).toEqual({ ok: true, value: row.expectedT1 })
})
it('据置ファウルでも毎回投球flagと履歴pushを保持し、10球で打ち切らない', () => {
  let request = structuredClone(foulCandidates.cases[3].request)
  for (let i = 0; i < 10; i++) {
    const result = invoke(request)
    expect(result.ok).toBe(true)
    expect(result.value.after).toEqual(request.before)
    expect(result.value.statFlags.投球数).toBe(true)
    expect(result.value.historyContext).toHaveLength(i + 1)
    expect(result.value.historyContext.slice(1)).toEqual(request.history.stack)
    expect(result.value.historyContext[0].difference.stateFields).toEqual({})
    request = {
      ...request,
      before: result.value.after,
      history: { stack: result.value.historyContext },
    }
  }
  for (const resultId of [
    'K3',
    'SO-04',
    'batting-result.k3',
    'batting-result.bunt-foul',
  ])
    expect(invoke({ ...request, resultId })).toEqual({
      ok: false,
      error: { code: 'UNSUPPORTED_T1_SCOPE' },
    })
})
