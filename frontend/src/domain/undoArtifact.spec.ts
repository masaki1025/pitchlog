import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { describe, expect, it } from 'vitest'
import type {
  Request,
  Response,
} from '../../../contracts/state-transition/undo_v1.d.ts'

const contract = JSON.parse(
  readFileSync(
    resolve(process.cwd(), '../contracts/state-transition/undo_cases_v1.json'),
    'utf8',
  ),
) as {
  cases: Array<{ caseId: string; request: Request; expected: Response }>
  rejectionCases: Array<{
    caseId: string
    request: unknown
    expected: Response
  }>
  unavailableCases: Array<{
    caseId: string
    request: unknown
    expected: Response
  }>
  rawRejectionCases: Array<{
    caseId: string
    requestJson: string
    expected: Response
  }>
  legacy: {
    cases: Array<{ caseId: string; historyInput: unknown; expected: unknown }>
  }
}
const context = createContext({})
new Script(
  readFileSync(
    resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
    'utf8',
  ),
).runInContext(context, { timeout: 1000 })
const api = context.PitchlogDomain as Record<string, (input: string) => string>
const invoke = (op: string, request: unknown): Record<string, unknown> =>
  JSON.parse(api[op]!(JSON.stringify(request))) as Record<string, unknown>

/** 旧部分契約の整数表現だけを転記する。期待や状態を計算しない。 */
function decimalLeaves(value: unknown): unknown {
  if (typeof value === 'number') return value.toString()
  if (Array.isArray(value)) return value.map(decimalLeaves)
  if (typeof value === 'object' && value !== null)
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, decimalLeaves(item)]),
    )
  return value
}

describe('唯一ビルド済みartifactの純取消', () => {
  it('14全手例・全閉拒否・未分類3を全値で消費する', () => {
    expect(contract.cases).toHaveLength(14)
    for (const row of [
      ...contract.cases,
      ...contract.rejectionCases,
      ...contract.unavailableCases,
    ])
      expect(invoke('applyUndo', row.request), row.caseId).toEqual(row.expected)
    for (const row of contract.rawRejectionCases)
      expect(JSON.parse(api.applyUndo!(row.requestJson))).toEqual(row.expected)
  })
  it('旧10部分契約を全比較面で消費しfull-current規範へ昇格しない', () => {
    expect(contract.legacy.cases).toHaveLength(10)
    for (const row of contract.legacy.cases) {
      const history = decimalLeaves(row.historyInput) as {
        stack: Array<{
          difference: {
            stateFields: Record<string, { before: unknown; after: unknown }>
            scoreboard: Record<string, { before: unknown; after: unknown }>
          }
        }>
      }
      // legacy原典に欠けるcurrentの試験専用completion。完全入力goldenとは別。
      const current = structuredClone(contract.cases[0]!.request.current) as {
        stateFields: Record<string, unknown>
        scoreboard: Record<string, unknown>
      }
      for (const [key, pair] of Object.entries(
        history.stack[0]?.difference.stateFields ?? {},
      ))
        current.stateFields[key] = pair.after
      for (const [key, pair] of Object.entries(
        history.stack[0]?.difference.scoreboard ?? {},
      ))
        current.scoreboard[key] = pair.after
      const result = invoke('applyUndo', { current, history }) as {
        ok: boolean
        value: Record<string, unknown>
      }
      expect(result.ok, row.caseId).toBe(true)
      const expected = decimalLeaves(row.expected) as {
        guaranteeMode: string
        operationResult: unknown
        stateEffect: Record<string, unknown>
        historyEffect: unknown
        historyContext: unknown
      }
      expect(result.value.operationResult, row.caseId).toEqual(
        expected.operationResult,
      )
      expect(result.value.historyEffect, row.caseId).toEqual(
        expected.historyEffect,
      )
      if (expected.guaranteeMode === 'liveness-only') {
        expect(result.value.historyContext as unknown[]).toHaveLength(
          history.stack.length - 1,
        )
        expect(
          (result.value.stateEffect as Record<string, unknown>)
            .historyAndResult,
        ).toEqual(expected.stateEffect.historyAndResult)
      } else {
        expect(result.value.stateEffect, row.caseId).toEqual(
          expected.stateEffect,
        )
        expect(result.value.historyContext, row.caseId).toEqual(
          expected.historyContext,
        )
      }
    }
  })
  it('実前進が返した2球のafter/全履歴だけを連結して2回取消し次球を計算できる', () => {
    const initial = structuredClone(contract.cases[0]!.request.current)
    type Pitch = {
      ok: boolean
      value: { after: unknown; historyContext: unknown[] }
    }
    const pitch = (before: unknown, stack: unknown[]) =>
      invoke('deriveOrdinaryPitch', {
        eventKind: 'batting-result',
        resultId: 'batting-result.ball',
        pitchEventKind: 'pitch-event',
        before,
        history: { stack },
      }) as Pitch
    const one = pitch(initial, [])
    expect(one.ok).toBe(true)
    const two = pitch(one.value.after, one.value.historyContext)
    expect(two.ok).toBe(true)
    const undo = invoke('applyUndo', {
      current: two.value.after,
      history: { stack: two.value.historyContext },
    }) as { ok: boolean; value: { after: unknown; historyContext: unknown[] } }
    expect(undo.ok).toBe(true)
    expect(undo.value.after).toEqual(one.value.after)
    expect(undo.value.historyContext).toEqual(one.value.historyContext)
    const again = invoke('applyUndo', {
      current: undo.value.after,
      history: { stack: undo.value.historyContext },
    }) as typeof undo
    expect(again.ok).toBe(true)
    expect(again.value.after).toEqual(initial)
    expect(again.value.historyContext).toEqual([])
    expect(pitch(again.value.after, again.value.historyContext)).toEqual(one)
  })
  it('安打D01を含む旧lineup全19入力の前進結果を保持し未分類取消を成功へしない', () => {
    const rows = JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          '../contracts/state-transition/batted_hit_prefix_cases_v1.json',
        ),
        'utf8',
      ),
    ).cases as Array<{ caseId: string; request: unknown; expected: unknown }>
    expect(rows).toHaveLength(19)
    for (const row of rows) {
      const response = invoke(
        'deriveLineupPlayPrefixWithContinuation',
        row.request,
      )
      expect(response, row.caseId).toEqual(row.expected)
      const value = response.value as {
        t1: { after: unknown }
        newHistoryEntry: unknown
      }
      const result = invoke('applyUndo', {
        current: value.t1.after,
        history: { stack: [value.newHistoryEntry] },
      })
      expect(result, row.caseId).toEqual({
        ok: false,
        error: { code: 'UNSUPPORTED_T1_SCOPE' },
      })
    }
  })
})
