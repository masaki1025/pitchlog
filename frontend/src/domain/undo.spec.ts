import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { applyUndo } from './undo'
import type {
  BoardDifference,
  CursorDifference,
  HistoryEntry,
  StateDifference,
  UndoStateEffect,
} from './undo'
import { emptyFlags } from './state'
import type { Scoreboard, StateFields } from './stateTypes'

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
  (item) => (item.rowRef as Json).layer === 'undoRows',
)

/** 契約 JSON の数値を bigint へ再帰変換する（number のまま比較しない）。 */
function toBigint(value: unknown): unknown {
  if (typeof value === 'number') return BigInt(value)
  if (Array.isArray(value)) {
    return value.map((item) => toBigint(item))
  }
  if (typeof value === 'object' && value !== null) {
    const object = value as Json
    const result: Json = {}
    for (const key of Object.keys(object)) {
      result[key] = toBigint(object[key])
    }
    return result
  }
  return value
}

/** 深い同値（bigint は値としての一致、オブジェクトはキー集合と各値で判定する）。 */
function deepEqual(left: unknown, right: unknown): boolean {
  if (left === right) return true
  if (typeof left !== 'object' || left === null) return false
  if (typeof right !== 'object' || right === null) return false
  if (Array.isArray(left) !== Array.isArray(right)) return false
  const leftKeys = Object.keys(left as Json)
  const rightKeys = Object.keys(right as Json)
  if (leftKeys.length !== rightKeys.length) return false
  for (const key of leftKeys) {
    if (!deepEqual((left as Json)[key], (right as Json)[key])) {
      return false
    }
  }
  return true
}

function span(value: unknown): { before: bigint; after: bigint } | null {
  if (typeof value !== 'object' || value === null) return null
  const pair = value as Json
  return {
    before: BigInt(pair.before as string),
    after: BigInt(pair.after as string),
  }
}

function scoreSpan(value: unknown): {
  before: { home: bigint; away: bigint }
  after: { home: bigint; away: bigint }
} | null {
  if (typeof value !== 'object' || value === null) return null
  const pair = value as Json
  const before = pair.before as Json
  const after = pair.after as Json
  return {
    before: {
      home: BigInt(before.home as string),
      away: BigInt(before.away as string),
    },
    after: {
      home: BigInt(after.home as string),
      away: BigInt(after.away as string),
    },
  }
}

/** 契約の sparse な wire 差分を内部の固定フィールドへ写す（試験補助）。 */
function internalEntry(value: Json): HistoryEntry {
  const difference = value.difference as Json
  const sf = difference.stateFields as Json
  const sb = difference.scoreboard as Json
  const cursors = difference.battingOrderBySide as Json | undefined
  const stateFields: StateDifference = {
    half:
      sf['state.half'] === undefined
        ? null
        : (sf['state.half'] as StateDifference['half']),
    strikes: span(sf['state.count.strikes']),
    balls: span(sf['state.count.balls']),
    outs: span(sf['state.outs']),
    runners:
      sf['state.runners'] === undefined
        ? null
        : (sf['state.runners'] as StateDifference['runners']),
    battingOrder: span(sf['state.battingOrder']),
    tiebreakActive:
      sf['state.tiebreakActive'] === undefined
        ? null
        : (sf['state.tiebreakActive'] as StateDifference['tiebreakActive']),
    gameEnded:
      sf['state.gameEnded'] === undefined
        ? null
        : (sf['state.gameEnded'] as StateDifference['gameEnded']),
    inning: span(sf['state.inning']),
    score: scoreSpan(sf['state.score']),
  }
  const scoreboard: BoardDifference = {
    inningScores: scoreSpan(sb.inningScores),
    hits: span(sb.hits),
    errors: span(sb.errors),
    strikeouts: span(sb.strikeouts),
    walks: span(sb.walks),
  }
  let cursorDifference: CursorDifference | null = null
  if (cursors !== undefined) {
    cursorDifference = {
      away: span(cursors.away),
      home: span(cursors.home),
    }
  }
  return {
    kind: value.kind as string,
    difference: {
      stateFields: stateFields,
      scoreboard: scoreboard,
      statFlags: difference.statFlags as Record<string, boolean>,
      battingOrderBySide: cursorDifference,
    },
  }
}

/** 取消前の状態の基底（試合開始時の状態。整数は bigint）。 */
function baseState(): StateFields {
  return {
    half: 'top',
    strikes: 0n,
    balls: 0n,
    outs: 0n,
    runners: 'empty',
    battingOrder: 1n,
    tiebreakActive: false,
    gameEnded: false,
    inning: 1n,
    home: 0n,
    away: 0n,
  }
}

/** 取消前のスコアボードの基底（全欄 0）。 */
function baseBoard(): Scoreboard {
  return {
    home: 0n,
    away: 0n,
    hits: 0n,
    errors: 0n,
    strikeouts: 0n,
    walks: 0n,
  }
}

/**
 * 現在状態（取消前）を先頭差分の `after` から再構成する。
 *
 * 契約の行は現在状態を持たず `historyInput.stack` だけを持つため、
 * 基底（試合開始時）に先頭差分の `stateFields` / `scoreboard` の `after`
 * を上書きする。これで undoRows 10 件すべてが期待値に到達する。
 */
function currentState(stack: Array<HistoryEntry>): {
  stateFields: StateFields
  scoreboard: Scoreboard
} {
  const stateFields = baseState()
  const scoreboard = baseBoard()
  if (stack.length === 0) {
    return { stateFields: stateFields, scoreboard: scoreboard }
  }
  const spans = stack[0].difference.stateFields
  if (spans.half !== null) stateFields.half = spans.half.after
  if (spans.strikes !== null) stateFields.strikes = spans.strikes.after
  if (spans.balls !== null) stateFields.balls = spans.balls.after
  if (spans.outs !== null) stateFields.outs = spans.outs.after
  if (spans.runners !== null) stateFields.runners = spans.runners.after
  if (spans.battingOrder !== null)
    stateFields.battingOrder = spans.battingOrder.after
  if (spans.tiebreakActive !== null)
    stateFields.tiebreakActive = spans.tiebreakActive.after
  if (spans.gameEnded !== null) stateFields.gameEnded = spans.gameEnded.after
  if (spans.inning !== null) stateFields.inning = spans.inning.after
  if (spans.score !== null) {
    stateFields.home = spans.score.after.home
    stateFields.away = spans.score.after.away
  }
  const boards = stack[0].difference.scoreboard
  if (boards.inningScores !== null) {
    scoreboard.home = boards.inningScores.after.home
    scoreboard.away = boards.inningScores.after.away
  }
  if (boards.hits !== null) scoreboard.hits = boards.hits.after
  if (boards.errors !== null) scoreboard.errors = boards.errors.after
  if (boards.strikeouts !== null)
    scoreboard.strikeouts = boards.strikeouts.after
  if (boards.walks !== null) scoreboard.walks = boards.walks.after
  return { stateFields: stateFields, scoreboard: scoreboard }
}

/** 内部の固定フィールドを契約と同じ sparse 表現へ戻す（比較専用）。 */
function comparableEntry(entry: HistoryEntry): Json {
  const sf: Json = {}
  const state = entry.difference.stateFields
  if (state.half !== null) sf['state.half'] = state.half
  if (state.strikes !== null) sf['state.count.strikes'] = state.strikes
  if (state.balls !== null) sf['state.count.balls'] = state.balls
  if (state.outs !== null) sf['state.outs'] = state.outs
  if (state.runners !== null) sf['state.runners'] = state.runners
  if (state.battingOrder !== null) sf['state.battingOrder'] = state.battingOrder
  if (state.tiebreakActive !== null)
    sf['state.tiebreakActive'] = state.tiebreakActive
  if (state.gameEnded !== null) sf['state.gameEnded'] = state.gameEnded
  if (state.inning !== null) sf['state.inning'] = state.inning
  if (state.score !== null) sf['state.score'] = state.score
  const sb: Json = {}
  const board = entry.difference.scoreboard
  if (board.inningScores !== null) sb.inningScores = board.inningScores
  if (board.hits !== null) sb.hits = board.hits
  if (board.errors !== null) sb.errors = board.errors
  if (board.strikeouts !== null) sb.strikeouts = board.strikeouts
  if (board.walks !== null) sb.walks = board.walks
  const difference: Json = {
    stateFields: sf,
    scoreboard: sb,
    statFlags: entry.difference.statFlags,
  }
  const cursors = entry.difference.battingOrderBySide
  if (cursors !== null) {
    const cd: Json = {}
    if (cursors.away !== null) cd.away = cursors.away
    if (cursors.home !== null) cd.home = cursors.home
    difference.battingOrderBySide = cd
  }
  return { kind: entry.kind, difference: difference }
}

describe('T1 取消行の契約照合', () => {
  it('undoRows を 10 件読む', () => {
    expect(rows).toHaveLength(10)
  })

  it('比較面（stateEffect）が全 10 状態欄・5 スコアボード・23 statFlags・履歴と結果の面を備える', () => {
    const outcome = applyUndo(baseState(), baseBoard(), [], null)
    if (typeof outcome === 'string') throw new Error(outcome)
    expect(Object.keys(outcome.stateEffect.stateFields)).toEqual([
      'state.half',
      'state.count.strikes',
      'state.count.balls',
      'state.outs',
      'state.runners',
      'state.battingOrder',
      'state.tiebreakActive',
      'state.gameEnded',
      'state.inning',
      'state.score',
    ])
    expect(Object.keys(outcome.stateEffect.scoreboard)).toEqual([
      'inningScores',
      'hits',
      'errors',
      'strikeouts',
      'walks',
    ])
    expect(Object.keys(outcome.stateEffect.statFlags)).toEqual(
      Object.keys(emptyFlags()),
    )
    expect(Object.keys(outcome.stateEffect.historyAndResult)).toEqual([
      'history',
      'operationResult',
    ])
  })

  it('10 件すべてで operationResult と比較面・履歴効果・履歴文脈が契約と一致する', () => {
    const mismatches: Array<string> = []
    for (const item of rows) {
      const caseId = item.caseId as string
      const expected = toBigint(item.expected) as Json & {
        guaranteeMode: string
        operationResult: string
        stateEffect: UndoStateEffect
        historyEffect: { pops: bigint }
        historyContext: Array<Json> | null
      }
      const historyInput = item.historyInput as { stack: Array<Json> }
      const stack = historyInput.stack.map(internalEntry)
      const current = currentState(stack)
      const outcome = applyUndo(
        current.stateFields,
        current.scoreboard,
        stack,
        null,
      )
      if (typeof outcome === 'string') throw new Error(outcome)
      if (expected.guaranteeMode === 'liveness-only') {
        // liveness-only（XC-09・x-pitchlog-undo-liveness-comparison）:
        // 適用結果と履歴量（pops=1、履歴長 -1）だけを要求する。
        // stateEffect と historyContext[*] は無視（= 緩めではなく規定どおり）。
        if (outcome.operationResult !== 'applied') {
          mismatches.push(`${caseId}:operationResult`)
        }
        if (outcome.historyEffect.pops !== 1n) {
          mismatches.push(`${caseId}:historyEffect`)
        }
        if (outcome.historyContext.length !== stack.length - 1) {
          mismatches.push(`${caseId}:historyContext.length`)
        }
        // ignoredOutputPaths は stateEffect の状態・スコアボード・statFlags と
        // historyContext[*] だけなので、historyAndResult は比較する。
        if (
          !deepEqual(
            outcome.stateEffect.historyAndResult,
            expected.stateEffect.historyAndResult,
          )
        ) {
          mismatches.push(`${caseId}:stateEffect.historyAndResult`)
        }
      } else if (expected.guaranteeMode === 'full-equality') {
        // full-equality: 全比較面を一致させる（部分一致にしない）。
        if (outcome.operationResult !== expected.operationResult) {
          mismatches.push(`${caseId}:operationResult`)
        }
        if (!deepEqual(outcome.stateEffect, expected.stateEffect)) {
          mismatches.push(`${caseId}:stateEffect`)
        }
        if (!deepEqual(outcome.historyEffect, expected.historyEffect)) {
          mismatches.push(`${caseId}:historyEffect`)
        }
        if (
          !deepEqual(
            outcome.historyContext.map(comparableEntry),
            expected.historyContext,
          )
        ) {
          mismatches.push(`${caseId}:historyContext`)
        }
      } else {
        mismatches.push(`${caseId}:guaranteeMode`)
      }
    }
    expect(mismatches).toEqual([])
  })
})

// 旧10のcurrentは契約が欠く部分を比較試験だけで構成する。新14 full入力とは区別する。
const accepted = JSON.parse(
  readFileSync(
    resolve(process.cwd(), '../contracts/state-transition/undo_cases_v1.json'),
    'utf8',
  ),
) as {
  cases: Array<{ caseId: string; request: unknown; expected: unknown }>
  rejectionCases: Array<{ caseId: string; request: unknown; expected: unknown }>
  unavailableCases: Array<{
    caseId: string
    request: unknown
    expected: unknown
  }>
  rawRejectionCases: Array<{
    caseId: string
    requestJson: string
    expected: unknown
  }>
}

import { domainOperations } from './publicApi'

describe('採用済み純undoの完全入力と閉拒否', () => {
  it('新14手例と全拒否を期待の全値で比較し入力を変更しない', () => {
    expect(accepted.cases).toHaveLength(14)
    expect(accepted.rejectionCases).toHaveLength(13)
    expect(accepted.unavailableCases).toHaveLength(3)
    for (const row of [
      ...accepted.cases,
      ...accepted.rejectionCases,
      ...accepted.unavailableCases,
    ]) {
      const before = JSON.stringify(row.request)
      expect(
        JSON.parse(domainOperations.applyUndo(before)),
        row.caseId,
      ).toEqual(row.expected)
      expect(JSON.stringify(row.request)).toBe(before)
    }
    for (const row of accepted.rawRejectionCases)
      expect(
        JSON.parse(domainOperations.applyUndo(row.requestJson)),
        row.caseId,
      ).toEqual(row.expected)
  })
  it('現在値の全提示state/board/cursor葉を個別に破壊すると拒否する', () => {
    const selected = accepted.cases.find(
      (r) => r.caseId === 'UNDO-V3-CURSOR-BOUNDARY',
    )
    expect(selected).toBeDefined()
    const value = selected!.request as { current: Record<string, unknown> }
    for (const [surface, key, changed] of [
      ['stateFields', 'state.half', 'bottom'],
      ['stateFields', 'state.outs', '1'],
      ['stateFields', 'state.inning', '11'],
      ['battingOrderBySide', 'home', '3'],
    ] as const) {
      const request = structuredClone(value)
      ;(request.current[surface] as Record<string, unknown>)[key] = changed
      expect(
        JSON.parse(domainOperations.applyUndo(JSON.stringify(request))),
      ).toEqual({ ok: false, error: { code: 'INVALID_REQUEST' } })
    }
  })
  it('5001桁の未変化得点と257件を超える整合履歴を制限しない', () => {
    const row = accepted.cases.find(
      (r) => r.caseId === 'UNDO-ORDINARY-FOUL-NO-CHANGE',
    )!
    const request = structuredClone(row.request) as {
      current: {
        stateFields: Record<string, unknown>
        scoreboard: Record<string, unknown>
      }
      history: { stack: unknown[] }
    }
    const score = { home: '1' + '0'.repeat(5000), away: '0' }
    request.current.stateFields['state.score'] = score
    request.current.scoreboard.inningScores = score
    request.history.stack = Array.from({ length: 513 }, () =>
      structuredClone(request.history.stack[0]),
    )
    const result = JSON.parse(
      domainOperations.applyUndo(JSON.stringify(request)),
    )
    expect(result.ok).toBe(true)
    expect(result.value.after).toEqual(request.current)
    expect(result.value.historyContext).toEqual(request.history.stack.slice(1))
    expect(result.value.historyEffect).toEqual({ pops: '1' })
  })
  it('number・非有限JSON・復号後重複・正準decimal末尾LFを補修しない', () => {
    const row = accepted.cases[0]
    expect(
      JSON.parse(
        domainOperations.applyUndo(
          '{"current":{},"\\u0063urrent":{},"history":{"stack":[]}}',
        ),
      ),
    ).toEqual({ ok: false, error: { code: 'INVALID_JSON' } })
    expect(
      JSON.parse(
        domainOperations.applyUndo(
          JSON.stringify(row.request).replace(
            '"state.inning":"1"',
            '"state.inning":1e999',
          ),
        ),
      ),
    ).toEqual({ ok: false, error: { code: 'INVALID_JSON' } })
    expect(
      JSON.parse(
        domainOperations.applyUndo(
          JSON.stringify(row.request).replace(
            '"state.inning":"1"',
            '"state.inning":"1\\n"',
          ),
        ),
      ),
    ).toEqual({ ok: false, error: { code: 'INVALID_DECIMAL_INTEGER' } })
  })
})

describe('全提示面のhead束縛とpure入力不変', () => {
  it('全14例のstate/board/cursor提示葉を個別に破壊し、健全な型のまま拒否する', () => {
    let checked = 0
    for (const row of accepted.cases) {
      const input = row.request as {
        current: Record<string, Record<string, unknown>>
        history: {
          stack: Array<{ difference: Record<string, Record<string, unknown>> }>
        }
      }
      const head = input.history.stack[0]
      if (head === undefined) continue
      for (const surface of [
        'stateFields',
        'scoreboard',
        'battingOrderBySide',
      ]) {
        for (const key of Object.keys(head.difference[surface] ?? {})) {
          const request = structuredClone(input)
          const current = request.current[surface]!
          const old = current[key]
          let changed: unknown
          if (typeof old === 'boolean') changed = !old
          else if (typeof old === 'object' && old !== null)
            changed = { ...old, home: '999' }
          else if (old === 'top') changed = 'bottom'
          else if (old === 'bottom') changed = 'top'
          else changed = old === '1' ? '2' : '1'
          current[key] = changed
          expect(
            JSON.parse(domainOperations.applyUndo(JSON.stringify(request))),
            `${row.caseId}/${surface}/${key}`,
          ).toEqual({ ok: false, error: { code: 'INVALID_REQUEST' } })
          checked++
        }
      }
    }
    expect(checked).toBe(18)
  })
  it('pure核のcurrent/board/stack/23flagをdeep freezeしても逆適用できる', () => {
    const entry = internalEntry(
      toBigint(
        (
          accepted.cases.find((r) => r.caseId === 'UNDO-ORDINARY-BALL-TWO')!
            .request as { history: { stack: Json[] } }
        ).history.stack[0],
      ) as Json,
    )
    const stack = [entry]
    const current = currentState(stack)
    const before = JSON.stringify({ stack, current }, (_, v: unknown) =>
      typeof v === 'bigint' ? v.toString() : v,
    )
    function freeze(value: unknown): void {
      if (typeof value !== 'object' || value === null) return
      Object.values(value).forEach(freeze)
      Object.freeze(value)
    }
    freeze(stack)
    freeze(current)
    const result = applyUndo(
      current.stateFields,
      current.scoreboard,
      stack,
      null,
    )
    if (typeof result === 'string') throw new Error(result)
    expect(result.after.stateFields.balls).toBe(1n)
    expect(result.historyContext).toEqual([])
    expect(
      JSON.stringify({ stack, current }, (_, v: unknown) =>
        typeof v === 'bigint' ? v.toString() : v,
      ),
    ).toBe(before)
  })
})

describe('23flag profileと全tailの閉検査', () => {
  it('各flagを単独反転した未知profileを推測で通さない', () => {
    const input = accepted.cases.find(
      (r) => r.caseId === 'UNDO-ORDINARY-BALL-ONE',
    )!.request as {
      history: {
        stack: Array<{ difference: { statFlags: Record<string, boolean> } }>
      }
    }
    const keys = Object.keys(input.history.stack[0]!.difference.statFlags)
    expect(keys).toHaveLength(23)
    for (const key of keys) {
      const changed = structuredClone(input)
      const flags = changed.history.stack[0]!.difference.statFlags
      flags[key] = !flags[key]
      expect(
        JSON.parse(domainOperations.applyUndo(JSON.stringify(changed))),
        key,
      ).toEqual({ ok: false, error: { code: 'UNSUPPORTED_T1_SCOPE' } })
    }
  })
  it('tailはwellformedなら未分類でも全値保持し、欠落/異型/非正準は拒否する', () => {
    const input = structuredClone(
      accepted.cases.find((r) => r.caseId === 'UNDO-ORDINARY-BALL-ONE')!
        .request,
    ) as { history: { stack: unknown[] } }
    const unknown = structuredClone(
      (
        accepted.unavailableCases[0]!.request as {
          history: { stack: unknown[] }
        }
      ).history.stack[0],
    )
    input.history.stack.push(unknown)
    const output = JSON.parse(domainOperations.applyUndo(JSON.stringify(input)))
    expect(output.ok).toBe(true)
    expect(output.value.historyContext).toEqual([unknown])
    const changed = structuredClone(input) as {
      history: {
        stack: Array<{ difference: { statFlags: Record<string, boolean> } }>
      }
    }
    delete changed.history.stack[1]!.difference.statFlags.投球数
    expect(
      JSON.parse(domainOperations.applyUndo(JSON.stringify(changed))),
    ).toEqual({ ok: false, error: { code: 'INVALID_REQUEST' } })
  })
})
