import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { derive } from './state'
import type { Advance, Derived, Scoreboard, StateFields } from './stateTypes'

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
  (item) => (item.rowRef as Json).layer === 'matrixRows',
)

/** 契約の `stateFields`（フラットなキー）を内部型へ写す。 */
function toState(fields: Json): StateFields {
  return {
    half: fields['state.half'] as StateFields['half'],
    strikes: BigInt(fields['state.count.strikes'] as number),
    balls: BigInt(fields['state.count.balls'] as number),
    outs: BigInt(fields['state.outs'] as number),
    runners: fields['state.runners'] as StateFields['runners'],
    battingOrder: BigInt(fields['state.battingOrder'] as number),
    tiebreakActive: fields['state.tiebreakActive'] as boolean,
    gameEnded: fields['state.gameEnded'] as boolean,
    inning: BigInt(fields['state.inning'] as number),
    home: BigInt((fields['state.score'] as Json).home as number),
    away: BigInt((fields['state.score'] as Json).away as number),
  }
}

/** 契約の `scoreboard` を内部型へ写す。 */
function toBoard(board: Json): Scoreboard {
  const innings = board.inningScores as Json
  return {
    home: BigInt(innings.home as number),
    away: BigInt(innings.away as number),
    hits: BigInt(board.hits as number),
    errors: BigInt(board.errors as number),
    strikeouts: BigInt(board.strikeouts as number),
    walks: BigInt(board.walks as number),
  }
}

/** 内部型を契約の形（number）へ戻す。 */
function stateJson(state: StateFields): Json {
  return {
    'state.half': state.half,
    'state.count.strikes': Number(state.strikes),
    'state.count.balls': Number(state.balls),
    'state.outs': Number(state.outs),
    'state.runners': state.runners,
    'state.battingOrder': Number(state.battingOrder),
    'state.tiebreakActive': state.tiebreakActive,
    'state.gameEnded': state.gameEnded,
    'state.inning': Number(state.inning),
    'state.score': { home: Number(state.home), away: Number(state.away) },
  }
}

/** 進塁計画を契約の形へ戻す。 */
function advanceJson(advance: Advance): Json {
  const destination: number | null =
    advance.destination === null ? null : Number(advance.destination)
  return { modality: advance.modality, destination }
}

/** 導出結果を契約の `expected` と同じ形へ戻す。 */
function derivedJson(derived: Derived): Json {
  const strikes: Json = { kind: derived.countEffect.strikes.kind }
  if (derived.countEffect.strikes.kind === 'delta') {
    strikes.value = Number(derived.countEffect.strikes.value)
  }
  const balls: Json = { kind: derived.countEffect.balls.kind }
  if (derived.countEffect.balls.kind === 'delta') {
    balls.value = Number(derived.countEffect.balls.value)
  }
  const destination: Json = { kind: derived.batterDestination.kind }
  if (derived.batterDestination.base !== undefined) {
    destination.base = Number(derived.batterDestination.base)
  }
  const targets = derived.outEffect.targets.map((target) => {
    if (target.kind === 'batter') return 'batter'
    return { runner: Number(target.base) }
  })
  return {
    countEffect: { strikes, balls },
    plateAppearanceEnded: derived.plateAppearanceEnded,
    batterDestination: destination,
    runnerDefaultAdvance: {
      first: advanceJson(derived.runnerDefaultAdvance.first),
      second: advanceJson(derived.runnerDefaultAdvance.second),
      third: advanceJson(derived.runnerDefaultAdvance.third),
    },
    outEffect: {
      count: Number(derived.outEffect.count),
      targets,
    },
    statFlags: derived.statFlags,
  }
}

describe('T1 状態計算の契約照合', () => {
  it('matrixRows を 89 件読む', () => {
    expect(rows).toHaveLength(89)
  })

  it('5 面と 23 フラグが全 89 件で契約と一致する', () => {
    const mismatches: Array<string> = []
    for (const item of rows) {
      const coordinate = item.inputCoordinate as Json
      const before = (item.historyInput as Json).before as Json
      const derived = derive(
        toState(before.stateFields as Json),
        toBoard(before.scoreboard as Json),
        coordinate.resultId as string,
        coordinate['event.perPitch.pitchEventKind'] as string | null,
      )
      const actual = derivedJson(derived)
      const expected = item.expected as Json
      for (const key of Object.keys(actual)) {
        const left = JSON.stringify(actual[key])
        const right = JSON.stringify(expected[key])
        if (left !== right) {
          mismatches.push(`${item.caseId as string}:${key}`)
        }
      }
    }
    expect(mismatches).toEqual([])
  })

  it('遷移後の状態は契約の after と既知の 34 行差分だけが残る', () => {
    const diffs: Array<string> = []
    for (const item of rows) {
      const coordinate = item.inputCoordinate as Json
      const history = item.historyInput as Json
      const before = history.before as Json
      const derived = derive(
        toState(before.stateFields as Json),
        toBoard(before.scoreboard as Json),
        coordinate.resultId as string,
        coordinate['event.perPitch.pitchEventKind'] as string | null,
      )
      const expected = history.after as Json
      const actualState = JSON.stringify(stateJson(derived.after.stateFields))
      const actualBoard = JSON.stringify({
        inningScores: {
          home: Number(derived.after.scoreboard.home),
          away: Number(derived.after.scoreboard.away),
        },
        hits: Number(derived.after.scoreboard.hits),
        errors: Number(derived.after.scoreboard.errors),
        strikeouts: Number(derived.after.scoreboard.strikeouts),
        walks: Number(derived.after.scoreboard.walks),
      })
      if (
        actualState !== JSON.stringify(expected.stateFields) ||
        actualBoard !== JSON.stringify(expected.scoreboard)
      ) {
        diffs.push(item.caseId as string)
      }
    }
    expect(diffs).toHaveLength(34)
  })
})
