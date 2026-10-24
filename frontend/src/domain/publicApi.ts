import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'
import { derive } from './state'
import { STATE_RULES } from './stateRules'
import type { Derived, Runners, Scoreboard, StateFields } from './stateTypes'

type DomainErrorCode =
  | 'INVALID_JSON'
  | 'INVALID_REQUEST'
  | 'INVALID_DECIMAL_INTEGER'
  | 'INVALID_STATE'

function errorResponse(code: DomainErrorCode): string {
  return JSON.stringify({ ok: false, error: { code } })
}

/**
 * 配布物の疎通だけに使う十進整数の往復操作。
 *
 * 入出力は JSON 文字列に統一する。不正な入力は例外を外へ出さず、
 * `{"ok":false,"error":{"code":"..."}}` を返す。計算対象のロジックは持たない。
 */
function ping(requestJson: string): string {
  if (typeof requestJson !== 'string') {
    return errorResponse('INVALID_REQUEST')
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(requestJson) as unknown
  } catch {
    return errorResponse('INVALID_JSON')
  }

  if (
    typeof parsed !== 'object' ||
    parsed === null ||
    Array.isArray(parsed) ||
    !Object.prototype.hasOwnProperty.call(parsed, 'value') ||
    !Object.keys(parsed).every((key) => key === 'value')
  ) {
    return errorResponse('INVALID_REQUEST')
  }

  const value = parseDecimalInteger((parsed as Record<string, unknown>).value)
  if (value === null) {
    return errorResponse('INVALID_DECIMAL_INTEGER')
  }

  return JSON.stringify({ ok: true, value: formatDecimalInteger(value) })
}

/** JSON オブジェクトとして読む。 */
function asObject(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null) return null
  if (Array.isArray(value)) return null
  return value as Record<string, unknown>
}

/** 十進文字列のフィールドを BigInt として読む。 */
function intField(source: Record<string, unknown>, key: string): bigint | null {
  return parseDecimalInteger(source[key])
}

/** 真理値のフィールドを読む。 */
function boolField(
  source: Record<string, unknown>,
  key: string,
): boolean | null {
  const value = source[key]
  if (typeof value !== 'boolean') return null
  return value
}

/** 文字列のフィールドを読む。 */
function textField(
  source: Record<string, unknown>,
  key: string,
): string | null {
  const value = source[key]
  if (typeof value !== 'string') return null
  return value
}

/** 契約の `stateFields`（フラットなキー）を内部型へ読む。 */
function readState(source: Record<string, unknown>): StateFields | null {
  const half = textField(source, 'state.half')
  const strikes = intField(source, 'state.count.strikes')
  const balls = intField(source, 'state.count.balls')
  const outs = intField(source, 'state.outs')
  const runners = textField(source, 'state.runners')
  const battingOrder = intField(source, 'state.battingOrder')
  const tiebreakActive = boolField(source, 'state.tiebreakActive')
  const gameEnded = boolField(source, 'state.gameEnded')
  const inning = intField(source, 'state.inning')
  const score = asObject(source['state.score'])
  if (score === null) return null
  const home = intField(score, 'home')
  const away = intField(score, 'away')
  if (
    half === null ||
    strikes === null ||
    balls === null ||
    outs === null ||
    runners === null ||
    battingOrder === null ||
    tiebreakActive === null ||
    gameEnded === null ||
    inning === null ||
    home === null ||
    away === null
  ) {
    return null
  }
  if (half !== 'top' && half !== 'bottom') return null
  return {
    half: half,
    strikes: strikes,
    balls: balls,
    outs: outs,
    runners: runners as Runners,
    battingOrder: battingOrder,
    tiebreakActive: tiebreakActive,
    gameEnded: gameEnded,
    inning: inning,
    home: home,
    away: away,
  }
}

/** 契約の `scoreboard` を内部型へ読む。 */
function readBoard(source: Record<string, unknown>): Scoreboard | null {
  const innings = asObject(source.inningScores)
  if (innings === null) return null
  const home = intField(innings, 'home')
  const away = intField(innings, 'away')
  const hits = intField(source, 'hits')
  const errors = intField(source, 'errors')
  const strikeouts = intField(source, 'strikeouts')
  const walks = intField(source, 'walks')
  if (
    home === null ||
    away === null ||
    hits === null ||
    errors === null ||
    strikeouts === null ||
    walks === null
  ) {
    return null
  }
  return {
    home: home,
    away: away,
    hits: hits,
    errors: errors,
    strikeouts: strikeouts,
    walks: walks,
  }
}

/** カウント効果を JSON へ書く。 */
function countJson(kind: string, value: bigint): Record<string, unknown> {
  if (kind === 'delta') {
    return { kind: kind, value: formatDecimalInteger(value) }
  }
  return { kind: kind }
}

/** 進塁計画を JSON へ書く。 */
function advanceJson(
  modality: string,
  destination: bigint | null,
): Record<string, unknown> {
  if (destination === null) {
    return { modality: modality, destination: null }
  }
  return { modality: modality, destination: formatDecimalInteger(destination) }
}

/** 遷移後の状態を JSON へ書く。 */
function stateJson(state: StateFields): Record<string, unknown> {
  return {
    'state.half': state.half,
    'state.count.strikes': formatDecimalInteger(state.strikes),
    'state.count.balls': formatDecimalInteger(state.balls),
    'state.outs': formatDecimalInteger(state.outs),
    'state.runners': state.runners,
    'state.battingOrder': formatDecimalInteger(state.battingOrder),
    'state.tiebreakActive': state.tiebreakActive,
    'state.gameEnded': state.gameEnded,
    'state.inning': formatDecimalInteger(state.inning),
    'state.score': {
      home: formatDecimalInteger(state.home),
      away: formatDecimalInteger(state.away),
    },
  }
}

/** スコアボードを JSON へ書く。 */
function boardJson(board: Scoreboard): Record<string, unknown> {
  return {
    inningScores: {
      home: formatDecimalInteger(board.home),
      away: formatDecimalInteger(board.away),
    },
    hits: formatDecimalInteger(board.hits),
    errors: formatDecimalInteger(board.errors),
    strikeouts: formatDecimalInteger(board.strikeouts),
    walks: formatDecimalInteger(board.walks),
  }
}

/** 導出結果を境界の JSON へ書く（整数は十進文字列）。 */
function derivedJson(derived: Derived): Record<string, unknown> {
  const destination: Record<string, unknown> = {
    kind: derived.batterDestination.kind,
  }
  if (typeof derived.batterDestination.base === 'bigint') {
    destination.base = formatDecimalInteger(derived.batterDestination.base)
  }
  const targets = derived.outEffect.targets.map((target) => {
    if (target.kind === 'batter') return 'batter' as unknown
    return { runner: formatDecimalInteger(target.base) } as unknown
  })
  return {
    countEffect: {
      strikes: countJson(
        derived.countEffect.strikes.kind,
        derived.countEffect.strikes.value,
      ),
      balls: countJson(
        derived.countEffect.balls.kind,
        derived.countEffect.balls.value,
      ),
    },
    plateAppearanceEnded: derived.plateAppearanceEnded,
    batterDestination: destination,
    runnerDefaultAdvance: {
      first: advanceJson(
        derived.runnerDefaultAdvance.first.modality,
        derived.runnerDefaultAdvance.first.destination,
      ),
      second: advanceJson(
        derived.runnerDefaultAdvance.second.modality,
        derived.runnerDefaultAdvance.second.destination,
      ),
      third: advanceJson(
        derived.runnerDefaultAdvance.third.modality,
        derived.runnerDefaultAdvance.third.destination,
      ),
    },
    outEffect: {
      count: formatDecimalInteger(derived.outEffect.count),
      targets: targets,
    },
    statFlags: derived.statFlags,
    after: {
      stateFields: stateJson(derived.after.stateFields),
      scoreboard: boardJson(derived.after.scoreboard),
    },
  }
}

/**
 * 1 球の状態遷移（T1）を JSON 文字列で受けて JSON 文字列で返す。
 *
 * 入力の整数は十進文字列に限る（JSON の数値は境界に持ち込まない）。
 * 結果 ID は規則表にあるものだけを受理する。
 */
function deriveState(requestJson: string): string {
  if (typeof requestJson !== 'string') {
    return errorResponse('INVALID_REQUEST')
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(requestJson) as unknown
  } catch {
    return errorResponse('INVALID_JSON')
  }
  const request = asObject(parsed)
  if (request === null) return errorResponse('INVALID_REQUEST')
  const before = asObject(request.before)
  if (before === null) return errorResponse('INVALID_REQUEST')
  const fields = asObject(before.stateFields)
  if (fields === null) return errorResponse('INVALID_REQUEST')
  const board = asObject(before.scoreboard)
  if (board === null) return errorResponse('INVALID_REQUEST')
  const state = readState(fields)
  const scoreboard = readBoard(board)
  const resultId = textField(request, 'resultId')
  if (state === null || scoreboard === null || resultId === null) {
    return errorResponse('INVALID_STATE')
  }
  if (!Object.prototype.hasOwnProperty.call(STATE_RULES, resultId)) {
    return errorResponse('INVALID_REQUEST')
  }
  let pitchEventKind: string | null = null
  const kind = request.pitchEventKind
  if (typeof kind === 'string') pitchEventKind = kind
  const derived = derive(state, scoreboard, resultId, pitchEventKind)
  return JSON.stringify({ ok: true, value: derivedJson(derived) })
}

/** JSON 文字列だけを境界とする操作の公開表。 */
export const domainOperations = Object.freeze({ ping, deriveState })
