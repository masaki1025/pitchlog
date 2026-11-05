/**
 * 取消（undo・FR-006・ADR-003 D-8）の純粋計算。
 *
 * 履歴スタック（新しい順）の先頭 1 件の差分を逆適用し、遷移後の状態・
 * スコアボード・履歴文脈と比較面（stateEffect）を返す。整数はすべて
 * bigint で扱い、`number` 型・`Number` 系の変換はドメイン検査の規定により
 * 使わない。
 *
 * 起点: `feature/ux1-undo-ts@b2ed1905` の実装を、現行の `stateTypes.ts` と
 * v3 の `battingOrderBySide` 差分へ追随させたもの。契約 `undoRows` の
 * 期待値は変更しない。
 */
import { emptyFlags } from './state'
import type {
  BattingOrderBySide,
  Half,
  Runners,
  Scoreboard,
  StateFields,
} from './stateTypes'

/** 得点ペア（得点・回別のスコアのペア）。 */
export type ScorePair = { home: bigint; away: bigint }

/** カウント系 1 項目（アウト・カウント・記録数）の差分。 */
export type IntSpan = { before: bigint; after: bigint }

/** 攻守（`state.half`）の差分。 */
export type HalfSpan = { before: Half; after: Half }

/** 走者（`state.runners`）の差分。 */
export type RunnersSpan = { before: Runners; after: Runners }

/** 真偽値 1 項目の差分。 */
export type BoolSpan = { before: boolean; after: boolean }

/** 得点ペア 1 項目（`state.score`・`inningScores`）の差分。 */
export type ScoreSpan = { before: ScorePair; after: ScorePair }

/**
 * 履歴差分の状態面。契約は変化したフィールドだけを保持するため、
 * 存在しないフィールドは null にする（`undefined` は許可構文にない）。
 */
export type StateDifference = {
  half: HalfSpan | null
  strikes: IntSpan | null
  balls: IntSpan | null
  outs: IntSpan | null
  runners: RunnersSpan | null
  battingOrder: IntSpan | null
  tiebreakActive: BoolSpan | null
  gameEnded: BoolSpan | null
  inning: IntSpan | null
  score: ScoreSpan | null
}

/** 履歴差分のスコアボード面（先頭差分に限り `home`/`away` は `inningScores`）。 */
export type BoardDifference = {
  inningScores: ScoreSpan | null
  hits: IntSpan | null
  errors: IntSpan | null
  strikeouts: IntSpan | null
  walks: IntSpan | null
}

/** v3 の両打順 cursor 差分。 */
export type CursorDifference = {
  away: IntSpan | null
  home: IntSpan | null
}

/** 履歴が積んだ行 1 件の差分。成績計上フラグは値をそのまま保持する。 */
export type HistoryDifference = {
  stateFields: StateDifference
  scoreboard: BoardDifference
  statFlags: Record<string, boolean>
  battingOrderBySide: CursorDifference | null
}

/** 履歴スタックの要素（新しい順）。種別は確定プレイや補正の分類。 */
export type HistoryEntry = { kind: string; difference: HistoryDifference }

/** 文字列値 1 項目の効果（契約の `fieldEffect` と同じ形）。 */
export type TextFieldEffect =
  { kind: 'unchanged' } | { kind: 'set'; value: string }

/** 真偽値 1 項目の効果（契約の `fieldEffect` と同じ形）。 */
export type BoolFieldEffect =
  { kind: 'unchanged' } | { kind: 'set'; value: boolean }

/** 整数值 1 項目の効果。取消の `delta` は契約・本規約ともマイナス方向に限る。 */
export type IntFieldEffect =
  | { kind: 'unchanged' }
  | { kind: 'set'; value: bigint }
  | { kind: 'delta'; value: bigint }

/** 得点ペア 1 項目の効果（取消では `set` で変化前を置く）。 */
export type ScoreFieldEffect =
  { kind: 'unchanged' } | { kind: 'set'; value: ScorePair }

/** 成績計上フラグ 1 項目の効果。取消では D-8 のとおり常に `unchanged`。 */
export type StatFlagEffect =
  { kind: 'unchanged' } | { kind: 'set'; value: boolean }

/** プレイ履歴 1 件分の効果（undo では 1 件対象なら `pop`）。 */
export type HistoryEffect =
  { kind: 'unchanged' } | { kind: 'pop'; count: bigint }

/**
 * 取消の比較面（契約 `stateEffect` と同じ形・整数は bigint）。
 *
 * キー順は契約の `stateFieldEffects` / `scoreboardFieldEffects` /
 * `statFlagEffects` の必須列の順に合わせる。
 */
export type UndoStateEffect = {
  stateFields: {
    'state.half': TextFieldEffect
    'state.count.strikes': IntFieldEffect
    'state.count.balls': IntFieldEffect
    'state.outs': IntFieldEffect
    'state.runners': TextFieldEffect
    'state.battingOrder': IntFieldEffect
    'state.tiebreakActive': BoolFieldEffect
    'state.gameEnded': BoolFieldEffect
    'state.inning': IntFieldEffect
    'state.score': ScoreFieldEffect
  }
  scoreboard: {
    inningScores: ScoreFieldEffect
    hits: IntFieldEffect
    errors: IntFieldEffect
    strikeouts: IntFieldEffect
    walks: IntFieldEffect
  }
  statFlags: Record<string, StatFlagEffect>
  historyAndResult: {
    history: HistoryEffect
    operationResult: { kind: 'set'; value: 'applied' | 'nothing-to-undo' }
  }
}

/** applyUndo の結果。 */
export type UndoOutcome = {
  operationResult: 'applied' | 'nothing-to-undo'
  after: {
    stateFields: StateFields
    scoreboard: Scoreboard
    battingOrderBySide: BattingOrderBySide | null
  }
  stateEffect: UndoStateEffect
  historyEffect: { pops: bigint }
  historyContext: Array<HistoryEntry>
}

/**
 * 履歴差分の状態面を遷移後の状態へ逆適用し、比較面を返す。
 *
 * 契約はフィールドごとの `delta`/`set` の分類を持たないため、本実装は
 * supportedHeadで受理済みの構造profileだけを逆適用する。分類は次のとおり
 * （`undoRows`10件と採用済みundo_casesの拘束範囲）。未分類の組合せは先に拒む。
 *
 * - `set`（差分の `before` を置く）: `state.half` / `state.inning` /
 *   `state.runners` / `state.battingOrder` / `state.tiebreakActive` /
 *   `state.gameEnded` / `state.score`
 * - `delta`（`before - after` を現在値へ適用する）:
 *   `state.count.strikes` / `state.count.balls` / `state.outs`
 * - 例外: `state.outs` は同じ先頭差分で `state.half` または `state.inning`
 *   も変化しているときだけ `set`（半イニングの境界を跨ぐ差分に一致）。
 */
function reverseStateFields(
  difference: StateDifference,
  after: StateFields,
  effect: UndoStateEffect,
): UndoStateEffect {
  if (difference.half !== null) {
    after.half = difference.half.before
    Object.assign(effect.stateFields, {
      'state.half': { kind: 'set', value: difference.half.before },
    })
  }
  if (difference.strikes !== null) {
    after.strikes =
      after.strikes + (difference.strikes.before - difference.strikes.after)
    Object.assign(effect.stateFields, {
      'state.count.strikes': deltaEffect(difference.strikes),
    })
  }
  if (difference.balls !== null) {
    after.balls =
      after.balls + (difference.balls.before - difference.balls.after)
    Object.assign(effect.stateFields, {
      'state.count.balls': deltaEffect(difference.balls),
    })
  }
  if (difference.outs !== null) {
    if (difference.half !== null || difference.inning !== null) {
      after.outs = difference.outs.before
      Object.assign(effect.stateFields, {
        'state.outs': { kind: 'set', value: difference.outs.before },
      })
    } else {
      after.outs = after.outs + (difference.outs.before - difference.outs.after)
      Object.assign(effect.stateFields, {
        'state.outs': deltaEffect(difference.outs),
      })
    }
  }
  if (difference.runners !== null) {
    after.runners = difference.runners.before
    Object.assign(effect.stateFields, {
      'state.runners': { kind: 'set', value: difference.runners.before },
    })
  }
  if (difference.battingOrder !== null) {
    after.battingOrder = difference.battingOrder.before
    Object.assign(effect.stateFields, {
      'state.battingOrder': {
        kind: 'set',
        value: difference.battingOrder.before,
      },
    })
  }
  if (difference.tiebreakActive !== null) {
    after.tiebreakActive = difference.tiebreakActive.before
    Object.assign(effect.stateFields, {
      'state.tiebreakActive': {
        kind: 'set',
        value: difference.tiebreakActive.before,
      },
    })
  }
  if (difference.gameEnded !== null) {
    after.gameEnded = difference.gameEnded.before
    Object.assign(effect.stateFields, {
      'state.gameEnded': {
        kind: 'set',
        value: difference.gameEnded.before,
      },
    })
  }
  if (difference.inning !== null) {
    after.inning = difference.inning.before
    Object.assign(effect.stateFields, {
      'state.inning': { kind: 'set', value: difference.inning.before },
    })
  }
  if (difference.score !== null) {
    after.home = difference.score.before.home
    after.away = difference.score.before.away
    Object.assign(effect.stateFields, {
      'state.score': scoreEffect(difference.score),
    })
  }
  return effect
}

/**
 * v3 の両打順 cursor を逆適用する。
 *
 * cursor は契約 `undoRows` の比較面には無いため `stateEffect` へは足さず、
 * 遷移後の状態だけを戻す（製品 v3 の状態復元に必要）。
 */
function reverseCursors(
  difference: CursorDifference,
  after: BattingOrderBySide,
) {
  if (difference.away !== null) after.away = difference.away.before
  if (difference.home !== null) after.home = difference.home.before
}

/**
 * 履歴差分のスコアボード面を遷移後のスコアボードへ逆適用し、比較面を返す。
 *
 * `inningScores` は `set`（差分の `before` を置き、得点ペアも同じ値へ写す）。
 * `hits` / `errors` / `strikeouts` / `walks` はカウント系のため `delta`
 * （`before - after` を現在値へ適用する）。
 */
function reverseScoreboard(
  difference: BoardDifference,
  afterBoard: Scoreboard,
  effect: UndoStateEffect,
): UndoStateEffect {
  if (difference.inningScores !== null) {
    afterBoard.home = difference.inningScores.before.home
    afterBoard.away = difference.inningScores.before.away
    Object.assign(effect.scoreboard, {
      inningScores: scoreEffect(difference.inningScores),
    })
  }
  if (difference.hits !== null) {
    afterBoard.hits =
      afterBoard.hits + (difference.hits.before - difference.hits.after)
    Object.assign(effect.scoreboard, { hits: deltaEffect(difference.hits) })
  }
  if (difference.errors !== null) {
    afterBoard.errors =
      afterBoard.errors + (difference.errors.before - difference.errors.after)
    Object.assign(effect.scoreboard, {
      errors: deltaEffect(difference.errors),
    })
  }
  if (difference.strikeouts !== null) {
    afterBoard.strikeouts =
      afterBoard.strikeouts +
      (difference.strikeouts.before - difference.strikeouts.after)
    Object.assign(effect.scoreboard, {
      strikeouts: deltaEffect(difference.strikeouts),
    })
  }
  if (difference.walks !== null) {
    afterBoard.walks =
      afterBoard.walks + (difference.walks.before - difference.walks.after)
    Object.assign(effect.scoreboard, { walks: deltaEffect(difference.walks) })
  }
  return effect
}

/** カウント系の差分を符号反転して 1 項目の効果へ写す（`delta` は符号を反転）。 */
function deltaEffect(span: IntSpan): IntFieldEffect {
  return { kind: 'delta', value: span.before - span.after }
}

/** 得点ペアの差分の変化前を `set` に写す（得点・回別スコア共通）。 */
function scoreEffect(span: ScoreSpan): ScoreFieldEffect {
  return {
    kind: 'set',
    value: { home: span.before.home, away: span.before.away },
  }
}

/**
 * 比較面（stateEffect）の台形を作る。
 *
 * 全項目を `unchanged` にし、`statFlags` は `emptyFlags()` のキー順
 * （= 契約の 23 項目の並び）で 23 項目を置く。履歴と結果の面は引数の値を
 * そのまま組む。
 */
function effectShell(
  history: HistoryEffect,
  operationResult: 'applied' | 'nothing-to-undo',
): UndoStateEffect {
  const flags: Record<string, StatFlagEffect> = {}
  for (const key of Object.keys(emptyFlags())) {
    Object.assign(flags, Object.fromEntries([[key, { kind: 'unchanged' }]]))
  }
  return {
    stateFields: {
      'state.half': { kind: 'unchanged' },
      'state.count.strikes': { kind: 'unchanged' },
      'state.count.balls': { kind: 'unchanged' },
      'state.outs': { kind: 'unchanged' },
      'state.runners': { kind: 'unchanged' },
      'state.battingOrder': { kind: 'unchanged' },
      'state.tiebreakActive': { kind: 'unchanged' },
      'state.gameEnded': { kind: 'unchanged' },
      'state.inning': { kind: 'unchanged' },
      'state.score': { kind: 'unchanged' },
    },
    scoreboard: {
      inningScores: { kind: 'unchanged' },
      hits: { kind: 'unchanged' },
      errors: { kind: 'unchanged' },
      strikeouts: { kind: 'unchanged' },
      walks: { kind: 'unchanged' },
    },
    statFlags: flags,
    historyAndResult: {
      history: history,
      operationResult: { kind: 'set', value: operationResult },
    },
  }
}

/** 状態を複製する（spread は許可構文にないため明示的に写す）。 */
function copyState(state: StateFields): StateFields {
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

/** スコアボードを複製する（spread は許可構文にないため明示的に写す）。 */
function copyBoard(board: Scoreboard): Scoreboard {
  return {
    home: board.home,
    away: board.away,
    hits: board.hits,
    errors: board.errors,
    strikeouts: board.strikeouts,
    walks: board.walks,
  }
}

/** 両cursorを複製する。 */
function copyCursors(cursors: BattingOrderBySide): BattingOrderBySide {
  return { away: cursors.away, home: cursors.home }
}

/** null を保ったまま両cursorを複製する（条件式を境界の許可構文に置き換える）。 */
function copyCursorsOrNull(
  cursors: BattingOrderBySide | null,
): BattingOrderBySide | null {
  if (cursors === null) return null
  return copyCursors(cursors)
}

/**
 * 取消（FR-006・ADR-003 D-8）を現在状態へ適用する。
 *
 * Args:
 *   current: 取消前の状態。
 *   board: 取消前のスコアボード。
 *   stack: 履歴スタック（新しい順）。要素は種別とフィールドごとの差分。
 *   cursors: v3 の両打順 cursor。null なら cursor を変更しない。
 *
 * Returns:
 *   操作結果、遷移後の状態とスコアボード、比較面（stateEffect・整数は
 *   bigint）、履歴効果、および先頭を除いた残りの履歴文脈（新しい順）。
 *
 * スタックが空なら `nothing-to-undo` とし、状態・スコアボード・履歴を
 * 変えない。非空なら先頭 1 件だけ `pop` する（undo 自身は対象に積まない）。
 * 成績計上フラグ（statFlags）は取消で変更しないため比較面も常に
 * `unchanged` である（D-8）。
 */
export function applyUndo(
  current: StateFields,
  board: Scoreboard,
  stack: Array<HistoryEntry>,
  cursors: BattingOrderBySide | null,
): UndoOutcome | 'INVALID_REQUEST' | 'UNSUPPORTED_T1_SCOPE' {
  const context = stack.concat()
  const top = context.shift() ?? null
  // 先頭が取れない（空スタック）ときは取り消す対象が無いため、
  // 状態・スコアボード・履歴は元のまま（FR-006 の空履歴の受入基準）。
  if (top === null) {
    return {
      operationResult: 'nothing-to-undo',
      after: {
        stateFields: copyState(current),
        scoreboard: copyBoard(board),
        battingOrderBySide: copyCursorsOrNull(cursors),
      },
      stateEffect: effectShell({ kind: 'unchanged' }, 'nothing-to-undo'),
      historyEffect: { pops: 0n },
      historyContext: [],
    }
  }
  if (!headMatches(top.difference, current, board, cursors))
    return 'INVALID_REQUEST'
  if (!supportedHead(top.difference)) return 'UNSUPPORTED_T1_SCOPE'
  const after = copyState(current)
  const afterBoard = copyBoard(board)
  // 逆適用の前提は、現在状態が先頭差分の `after` と一致していること。
  // 前進計算の再構成は行わず、差分が持つ `before` と `delta` でそのまま戻す。
  const effect = reverseScoreboard(
    top.difference.scoreboard,
    afterBoard,
    reverseStateFields(
      top.difference.stateFields,
      after,
      effectShell({ kind: 'pop', count: 1n }, 'applied'),
    ),
  )
  let afterCursors: BattingOrderBySide | null = null
  if (cursors !== null) {
    afterCursors = copyCursors(cursors)
    if (top.difference.battingOrderBySide !== null)
      reverseCursors(top.difference.battingOrderBySide, afterCursors)
  }
  return {
    operationResult: 'applied',
    after: {
      stateFields: after,
      scoreboard: afterBoard,
      battingOrderBySide: afterCursors,
    },
    stateEffect: effect,
    historyEffect: { pops: 1n },
    historyContext: context,
  }
}

/** 提示された整数差分が現在値と整合することを確認する。 */
function intMatches(span: IntSpan | null, current: bigint): boolean {
  return span === null || (span.before !== span.after && span.after === current)
}

/** 提示された得点差分を両側とも比較する。 */
function scoreMatches(
  span: ScoreSpan | null,
  home: bigint,
  away: bigint,
): boolean {
  return (
    span === null ||
    ((span.before.home !== span.after.home ||
      span.before.away !== span.after.away) &&
      span.after.home === home &&
      span.after.away === away)
  )
}

/** 逆適用前にstate/board/cursorの全提示afterを実currentへ束縛する。 */
function headMatches(
  d: HistoryDifference,
  current: StateFields,
  board: Scoreboard,
  cursors: BattingOrderBySide | null,
): boolean {
  const s = d.stateFields
  const b = d.scoreboard
  if (
    !intMatches(s.strikes, current.strikes) ||
    !intMatches(s.balls, current.balls) ||
    !intMatches(s.outs, current.outs) ||
    !intMatches(s.battingOrder, current.battingOrder) ||
    !intMatches(s.inning, current.inning) ||
    !scoreMatches(s.score, current.home, current.away) ||
    !scoreMatches(b.inningScores, board.home, board.away) ||
    !intMatches(b.hits, board.hits) ||
    !intMatches(b.errors, board.errors) ||
    !intMatches(b.strikeouts, board.strikeouts) ||
    !intMatches(b.walks, board.walks)
  )
    return false
  if (
    s.half !== null &&
    (s.half.before === s.half.after || s.half.after !== current.half)
  )
    return false
  if (
    s.runners !== null &&
    (s.runners.before === s.runners.after ||
      s.runners.after !== current.runners)
  )
    return false
  if (
    s.tiebreakActive !== null &&
    (s.tiebreakActive.before === s.tiebreakActive.after ||
      s.tiebreakActive.after !== current.tiebreakActive)
  )
    return false
  if (
    s.gameEnded !== null &&
    (s.gameEnded.before === s.gameEnded.after ||
      s.gameEnded.after !== current.gameEnded)
  )
    return false
  const c = d.battingOrderBySide
  if (c !== null) {
    if (cursors === null) return c.away === null && c.home === null
    if (!intMatches(c.away, cursors.away) || !intMatches(c.home, cursors.home))
      return false
  }
  return true
}

/** nullでない欄だけを列挙し、未分類の複合差分を成功へ補完しない。 */
function activeFields(value: StateDifference | BoardDifference): Array<string> {
  return Object.entries(value)
    .filter((pair) => pair.pop() !== null)
    .map((pair) => pair.shift() as string)
}

/** 欄集合の完全一致。値やcaseIDから期待を検索しない。 */
function fieldsAre(actual: Array<string>, expected: Array<string>): boolean {
  return (
    expected.every((key) => actual.includes(key)) &&
    actual.every((key) => expected.includes(key))
  )
}

/** 計上寄与の全23値を構造profileへ照合する。算入量は再計算しない。 */
function flagsAre(
  actual: Record<string, boolean>,
  expected: Array<string>,
): boolean {
  if (!fieldsAre(Object.keys(actual), Object.keys(emptyFlags()))) return false
  return Object.entries(actual).every((pair) => {
    const key = pair.shift()
    const value = pair.pop()
    return typeof key === 'string' && value === expected.includes(key)
  })
}

/** 完全なspan同値。得点/打点の観測値を新しく推測しない。 */
function sameScoreSpan(a: ScoreSpan, b: ScoreSpan): boolean {
  return (
    a.before.home === b.before.home &&
    a.before.away === b.before.away &&
    a.after.home === b.after.home &&
    a.after.away === b.after.away
  )
}

/** 既規範から閉じた6構造profileだけを提供する。深さ/桁数に上限を置かない。 */
function supportedHead(d: HistoryDifference): boolean {
  const s = d.stateFields
  const b = d.scoreboard
  const sk = activeFields(s)
  const bk = activeFields(b)
  if (fieldsAre(bk, []) && flagsAre(d.statFlags, ['投球数'])) {
    if (
      fieldsAre(sk, ['balls']) &&
      s.balls !== null &&
      s.balls.before >= 0n &&
      s.balls.after === s.balls.before + 1n &&
      s.balls.after <= 3n
    )
      return true
    if (
      fieldsAre(sk, ['strikes']) &&
      s.strikes !== null &&
      s.strikes.before >= 0n &&
      s.strikes.after === s.strikes.before + 1n &&
      s.strikes.after <= 2n
    )
      return true
    const c = d.battingOrderBySide
    if (
      fieldsAre(sk, []) &&
      (c === null || (c.away === null && c.home === null))
    )
      return true
  }
  if (
    fieldsAre(bk, []) &&
    flagsAre(d.statFlags, ['投球数', '投球回算入アウト'])
  ) {
    if (
      fieldsAre(sk, ['outs']) &&
      s.outs !== null &&
      s.outs.before >= 0n &&
      s.outs.after > s.outs.before &&
      s.outs.after <= 2n
    )
      return true
    if (
      s.outs !== null &&
      s.outs.before === 2n &&
      s.outs.after === 0n &&
      s.half !== null
    ) {
      if (
        fieldsAre(sk, ['outs', 'half']) &&
        s.half.before === 'top' &&
        s.half.after === 'bottom'
      )
        return true
      if (
        fieldsAre(sk, ['outs', 'half', 'inning']) &&
        s.half.before === 'bottom' &&
        s.half.after === 'top' &&
        s.inning !== null &&
        s.inning.before >= 1n &&
        s.inning.after === s.inning.before + 1n
      )
        return true
    }
  }
  if (
    b.hits !== null &&
    b.hits.before >= 0n &&
    b.hits.after === b.hits.before + 1n
  ) {
    if (
      fieldsAre(sk, []) &&
      fieldsAre(bk, ['hits']) &&
      flagsAre(d.statFlags, ['投球数', '安打', '被安打'])
    )
      return true
    if (
      fieldsAre(sk, ['score']) &&
      fieldsAre(bk, ['hits', 'inningScores']) &&
      s.score !== null &&
      b.inningScores !== null &&
      sameScoreSpan(s.score, b.inningScores) &&
      flagsAre(d.statFlags, ['投球数', '安打', '被安打', '得点', '打点'])
    ) {
      const p = s.score
      return (
        (p.before.home === p.after.home && p.after.away > p.before.away) ||
        (p.before.away === p.after.away && p.after.home > p.before.home)
      )
    }
  }
  return false
}
