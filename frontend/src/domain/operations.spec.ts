import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { applyOperation } from './operations'
import type { OperationKind, TiebreakSpec } from './operations'
import { emptyFlags } from './state'
import type { Runners, StateFields } from './stateTypes'

type Json = Record<string, unknown>

const contract = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/state_transition_contract_v1.json',
    ),
    'utf8',
  ),
) as { cases: Array<Json> }

const rows = contract.cases.filter(
  (item) => (item.rowRef as Json).layer === 'operationRows',
)

/** 契約の入力軸から事前状態を組み立てる。 */
function beforeState(item: Json): StateFields {
  const coordinate = item.inputCoordinate as Json
  const history = item.historyInput as Json
  const historyBefore = history.before as Json | null
  let inning = 1n
  if (typeof historyBefore === 'object' && historyBefore !== null) {
    const fields = (historyBefore as Json).stateFields as Json
    if (typeof fields['state.inning'] === 'number') {
      inning = BigInt(fields['state.inning'] as number)
    }
  }
  let runners: Runners = 'empty'
  if (typeof coordinate['state.runners'] === 'string') {
    runners = coordinate['state.runners'] as Runners
  }
  let battingOrder = 1n
  if (typeof coordinate['state.battingOrder'] === 'number') {
    battingOrder = BigInt(coordinate['state.battingOrder'] as number)
  }
  return {
    half: 'top',
    strikes: 0n,
    balls: 0n,
    outs: 0n,
    runners: runners,
    battingOrder: battingOrder,
    tiebreakActive: coordinate['state.tiebreakActive'] === true,
    gameEnded: coordinate['state.gameEnded'] === true,
    inning: inning,
    home: 0n,
    away: 0n,
  }
}

/** タイブレーク開始の指定内容を読む。 */
function tiebreakSpec(item: Json): TiebreakSpec {
  const coordinate = item.inputCoordinate as Json
  return {
    runnerPlacement: (coordinate['event.tiebreakStart.runnerPlacement'] ??
      'empty') as Runners,
    leadoffBatter: BigInt(
      (coordinate['event.tiebreakStart.leadoffBatter'] as number) ?? 1,
    ),
    inning: BigInt((coordinate['event.tiebreakStart.inning'] as number) ?? 1),
    activationRelation: (coordinate['event.tiebreakStart.activationRelation'] ??
      'not-ready') as 'ready' | 'not-ready',
  }
}

/** 1 項目の差分を契約の形（unchanged / set）へ写す。 */
function field(before: unknown, after: unknown): Json {
  if (JSON.stringify(before) === JSON.stringify(after)) {
    return { kind: 'unchanged' }
  }
  return { kind: 'set', value: after }
}

/** 操作が書いた項目は `set`、書いていない項目は `unchanged` にする。 */
function mark(written: boolean, value: unknown): Json {
  if (written) return { kind: 'set', value: value }
  return { kind: 'unchanged' }
}

/** 事前・事後の状態から契約の `stateEffect` を組み立てる。 */
function stateEffect(
  before: StateFields,
  after: StateFields,
  written: {
    gameEnded: boolean
    runners: boolean
    battingOrder: boolean
    tiebreakActive: boolean
    inning: boolean
  },
  result: string,
): Json {
  const flags: Json = {}
  for (const key of Object.keys(emptyFlags())) {
    flags[key] = { kind: 'unchanged' }
  }
  return {
    stateFields: {
      'state.half': field(before.half, after.half),
      'state.count.strikes': field(
        Number(before.strikes),
        Number(after.strikes),
      ),
      'state.count.balls': field(Number(before.balls), Number(after.balls)),
      'state.outs': field(Number(before.outs), Number(after.outs)),
      'state.runners': mark(written.runners, after.runners),
      'state.battingOrder': mark(
        written.battingOrder,
        Number(after.battingOrder),
      ),
      'state.tiebreakActive': mark(
        written.tiebreakActive,
        after.tiebreakActive,
      ),
      'state.gameEnded': mark(written.gameEnded, after.gameEnded),
      'state.inning': mark(written.inning, Number(after.inning)),
      'state.score': field(
        { home: Number(before.home), away: Number(before.away) },
        { home: Number(after.home), away: Number(after.away) },
      ),
    },
    // 交代・終了宣言・その場登録・タイブレーク開始はスコアボードを動かさない。
    scoreboard: {
      inningScores: { kind: 'unchanged' },
      hits: { kind: 'unchanged' },
      errors: { kind: 'unchanged' },
      strikeouts: { kind: 'unchanged' },
      walks: { kind: 'unchanged' },
    },
    statFlags: flags,
    historyAndResult: {
      history: { kind: 'unchanged' },
      operationResult: { kind: 'set', value: result },
    },
  }
}

describe('T1 操作行の契約照合', () => {
  it('operationRows を 10 件読む', () => {
    expect(rows).toHaveLength(10)
  })

  it('適用可否と状態差分が全 10 件で契約と一致する', () => {
    const mismatches: Array<string> = []
    for (const item of rows) {
      const coordinate = item.inputCoordinate as Json
      const expected = item.expected as Json
      const before = beforeState(item)
      const outcome = applyOperation(
        before,
        coordinate.operationKind as OperationKind,
        tiebreakSpec(item),
      )
      if (outcome.operationResult !== expected.operationResult) {
        mismatches.push(`${item.caseId as string}:operationResult`)
      }
      const actualEffect = stateEffect(
        before,
        outcome.after,
        outcome.written,
        outcome.operationResult,
      )
      if (
        JSON.stringify(actualEffect) !== JSON.stringify(expected.stateEffect)
      ) {
        mismatches.push(`${item.caseId as string}:stateEffect`)
      }
      if (
        JSON.stringify(outcome.historyEffect) !==
        JSON.stringify(expected.historyEffect)
      ) {
        mismatches.push(`${item.caseId as string}:historyEffect`)
      }
      if (
        JSON.stringify(outcome.historyContext) !==
        JSON.stringify(expected.historyContext)
      ) {
        mismatches.push(`${item.caseId as string}:historyContext`)
      }
    }
    expect(mismatches).toEqual([])
  })
})
