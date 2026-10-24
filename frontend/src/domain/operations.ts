import type { Runners, StateFields } from './stateTypes'

/** 打席に属さない操作の種類（FR-009/010/011/015）。 */
export type OperationKind =
  | 'substitution'
  | 'game-end-declaration'
  | 'adhoc-registration'
  | 'tiebreak-start'

/** タイブレーク開始の指定内容。 */
export type TiebreakSpec = {
  runnerPlacement: Runners
  leadoffBatter: bigint
  inning: bigint
  activationRelation: 'ready' | 'not-ready'
}

/** 操作の適用結果。 */
export type OperationOutcome = {
  operationResult: 'applied' | 'rejected-precondition'
  after: StateFields
  /** 操作が明示的に書いた状態項目（差分表現の `set` に対応）。 */
  written: {
    gameEnded: boolean
    runners: boolean
    battingOrder: boolean
    tiebreakActive: boolean
    inning: boolean
  }
  historyEffect: { pushes: boolean; kind: string | null }
  historyContext: Array<unknown>
}

/** 状態を複製する（spread は許可構文にないため明示的に写す）。 */
export function copyState(state: StateFields): StateFields {
  return {
    half: state.half,
    strikes: state.strikes,
    balls: state.balls,
    outs: state.outs,
    runners: state.runners,
    battingOrder: state.battingOrder,
    tiebreakActive: state.tiebreakActive,
    gameEnded: state.gameEnded,
    inning: state.inning,
    home: state.home,
    away: state.away,
  }
}

/**
 * 操作 1 件を状態へ適用する（FR-009/010/011/015）。
 *
 * 事前条件を満たさない操作は `rejected-precondition` とし、状態は変えない。
 * 操作は履歴の行（プレイ）を積まないため `historyEffect.pushes` は常に false。
 * タイブレークの発動可否は呼び出し側が導出した `activationRelation` を信頼する
 * （導出元は指定回・規則の開始回・現在回。`ready` 以外は適用しない）。
 */
export function applyOperation(
  before: StateFields,
  kind: OperationKind,
  spec: TiebreakSpec,
): OperationOutcome {
  const after = copyState(before)
  let applied = true
  let wroteGameEnded = false
  let wroteRunners = false
  let wroteBattingOrder = false
  let wroteTiebreakActive = false
  let wroteInning = false
  if (before.gameEnded) applied = false
  if (kind === 'game-end-declaration') {
    if (before.gameEnded) applied = false
    if (applied) {
      after.gameEnded = true
      wroteGameEnded = true
    }
  }
  if (kind === 'tiebreak-start') {
    if (before.tiebreakActive) applied = false
    if (spec.activationRelation !== 'ready') applied = false
    if (applied) {
      after.runners = spec.runnerPlacement
      after.battingOrder = spec.leadoffBatter
      after.tiebreakActive = true
      after.inning = spec.inning
      wroteRunners = true
      wroteBattingOrder = true
      wroteTiebreakActive = true
      wroteInning = true
    }
  }
  let operationResult: 'applied' | 'rejected-precondition' = 'applied'
  if (!applied) operationResult = 'rejected-precondition'
  return {
    operationResult: operationResult,
    after: after,
    written: {
      gameEnded: wroteGameEnded,
      runners: wroteRunners,
      battingOrder: wroteBattingOrder,
      tiebreakActive: wroteTiebreakActive,
      inning: wroteInning,
    },
    historyEffect: { pushes: false, kind: null },
    historyContext: [],
  }
}
