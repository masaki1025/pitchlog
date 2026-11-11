import type { Runners, StateFields } from './stateTypes'

/** D-8 の配置状態。正式規則の no_out_first_second は first-second へ写す。 */
export type TiebreakPlacement = 'first-second' | 'second-third'

export type TiebreakStartRule = {
  startInning: bigint | null
  runnerPlacement: TiebreakPlacement | 'no_out_first_second' | null
  leadoffRule: 'continue_lineup' | null
}

export type TiebreakStartSelection = {
  runnerPlacement: TiebreakPlacement
  leadoffBatter: bigint
  inning: bigint
}

export type TiebreakStartOutcome = {
  operationResult: 'applied' | 'rejected-precondition'
  after: StateFields
  written: {
    runners: boolean
    battingOrder: boolean
    tiebreakActive: boolean
    inning: boolean
  }
  historyEffect: { pushes: false; kind: null }
}

/** 保存規則・現在回・指定回から発動関係を導き、D-8 の状態効果だけを適用する。 */
export function deriveTiebreakStart(
  before: StateFields,
  rule: TiebreakStartRule,
  selection: TiebreakStartSelection,
): TiebreakStartOutcome {
  const rulePlacement =
    rule.runnerPlacement === 'no_out_first_second'
      ? 'first-second'
      : rule.runnerPlacement
  const applied =
    !before.gameEnded &&
    !before.tiebreakActive &&
    before.runners === 'empty' &&
    before.battingOrder >= 1n &&
    before.battingOrder <= 9n &&
    selection.leadoffBatter >= 1n &&
    selection.leadoffBatter <= 9n &&
    before.inning >= 1n &&
    rule.startInning !== null &&
    rule.startInning === before.inning &&
    selection.inning === before.inning &&
    rulePlacement === selection.runnerPlacement

  let nextRunners: Runners = before.runners
  let nextOrder = before.battingOrder
  let nextActive = before.tiebreakActive
  let nextInning = before.inning
  if (applied) {
    nextRunners = selection.runnerPlacement
    nextOrder = selection.leadoffBatter
    nextActive = true
    nextInning = selection.inning
  }
  let operationResult: 'applied' | 'rejected-precondition' =
    'rejected-precondition'
  if (applied) operationResult = 'applied'
  return {
    operationResult: operationResult,
    after: {
      half: before.half,
      strikes: before.strikes,
      balls: before.balls,
      outs: before.outs,
      runners: nextRunners,
      battingOrder: nextOrder,
      tiebreakActive: nextActive,
      gameEnded: before.gameEnded,
      inning: nextInning,
      home: before.home,
      away: before.away,
    },
    written: {
      runners: applied,
      battingOrder: applied,
      tiebreakActive: applied,
      inning: applied,
    },
    historyEffect: { pushes: false, kind: null },
  }
}

/** 試合規則に適合する配置を、記録者が確認した実選手IDで確定する。 */
export type TiebreakRestoreContext = {
  current: { stateFields: StateFields; scoreboard: unknown }
  participants: {
    batterId: string
    pitcherId: string
    catcherId: string
    battingOrder: string
  }
  runners: Array<{
    runnerId: string
    responsiblePitcherId: string
    base: '1' | '2' | '3'
    status: '継続'
    statusSource: 'auto'
  }>
  lineup: unknown
  responsibility: unknown
  substitutionState?: unknown
}

export type TiebreakRunnerSelection = {
  firstRunnerId: string
  secondRunnerId: string
}

export type TiebreakTransition =
  | { ok: true; afterContext: TiebreakRestoreContext }
  | {
      ok: false
      error:
        | 'invalid-source'
        | 'not-tiebreak-inning'
        | 'placement-mismatch'
        | 'runners-not-empty'
        | 'invalid-leadoff'
        | 'invalid-runner'
        | 'duplicate-runner'
    }

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

function validUuid(value: unknown): value is string {
  return typeof value === 'string' && UUID.test(value)
}

function sameValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

/**
 * 半回開始時のタイブレーク配置を、規則・現半回・実選手IDへ閉じる。
 *
 * P1=A: 記録者が確認した実選手IDだけを受け、任意の塁配置は認めない。
 * P2=A: 配置走者の責任投手は、その半回開始時の実投手で固定する。
 * P3=A: 発動後の各半回で、同じ規則に従う再配置を許す。
 *
 * Args:
 *   context: 現在CPの復元文脈。
 *   rule: 保存済み規則snapshotのタイブレーク3値。
 *   selection: 記録者が確認した実選手ID（一塁・二塁）。
 *   activePlayerIds: 現在の攻撃側の実出場選手ID。
 *
 * Returns:
 *   配置後の復元文脈、又は閉じた拒否理由。
 */
export function transitionTiebreakStart(
  context: TiebreakRestoreContext,
  rule: TiebreakStartRule,
  selection: TiebreakRunnerSelection,
  activePlayerIds: readonly string[],
): TiebreakTransition {
  if (
    context === null ||
    typeof context !== 'object' ||
    !context.current ||
    !context.participants ||
    !Array.isArray(context.runners) ||
    !Array.isArray(activePlayerIds)
  )
    return { ok: false, error: 'invalid-source' }
  const before = context.current.stateFields
  const expectedPlacement =
    rule.runnerPlacement === 'no_out_first_second' ||
    rule.runnerPlacement === 'first-second'
      ? 'first-second'
      : null
  if (
    rule.startInning === null ||
    expectedPlacement === null ||
    rule.leadoffRule !== 'continue_lineup'
  )
    return { ok: false, error: 'not-tiebreak-inning' }
  if (before.gameEnded || before.inning < rule.startInning)
    return { ok: false, error: 'not-tiebreak-inning' }
  if (
    before.runners !== 'empty' ||
    before.outs !== 0n ||
    before.strikes !== 0n ||
    before.balls !== 0n ||
    context.runners.length !== 0
  )
    return { ok: false, error: 'runners-not-empty' }
  if (
    before.battingOrder < 1n ||
    before.battingOrder > 9n ||
    context.participants.battingOrder !== String(before.battingOrder)
  )
    return { ok: false, error: 'invalid-leadoff' }
  if (
    !validUuid(selection.firstRunnerId) ||
    !validUuid(selection.secondRunnerId) ||
    !activePlayerIds.includes(selection.firstRunnerId) ||
    !activePlayerIds.includes(selection.secondRunnerId) ||
    selection.firstRunnerId === context.participants.batterId ||
    selection.secondRunnerId === context.participants.batterId
  )
    return { ok: false, error: 'invalid-runner' }
  if (selection.firstRunnerId === selection.secondRunnerId)
    return { ok: false, error: 'duplicate-runner' }
  const responsiblePitcherId = context.participants.pitcherId
  if (!validUuid(responsiblePitcherId))
    return { ok: false, error: 'invalid-source' }
  const afterFields: StateFields = {
    ...before,
    runners: 'first-second',
    tiebreakActive: true,
  }
  const after: TiebreakRestoreContext = {
    ...context,
    current: {
      ...context.current,
      stateFields: afterFields,
    },
    runners: [
      {
        runnerId: selection.firstRunnerId,
        responsiblePitcherId,
        base: '1',
        status: '継続',
        statusSource: 'auto',
      },
      {
        runnerId: selection.secondRunnerId,
        responsiblePitcherId,
        base: '2',
        status: '継続',
        statusSource: 'auto',
      },
    ],
    participants: {
      ...context.participants,
      battingOrder: String(before.battingOrder),
    },
  }
  if (!sameValue(after.current.scoreboard, context.current.scoreboard))
    return { ok: false, error: 'invalid-source' }
  return { ok: true, afterContext: after }
}
