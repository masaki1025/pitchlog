import { quantizeCourse } from './courseQuantization'
import { validateInitialGameRoster } from './initialGameRoster'
import {
  evaluateFirstPitchContinuation,
  readContinuationRules,
} from './firstPitchContinuation'
import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'
import { derive, deriveOrdinary, emptyFlags } from './state'
import type { Derived, Runners, Scoreboard, StateFields } from './stateTypes'

type DomainErrorCode =
  | 'INVALID_JSON'
  | 'INVALID_REQUEST'
  | 'INVALID_DECIMAL_INTEGER'
  | 'UNSUPPORTED_T1_SCOPE'

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

/** 入力objectを変更せず、固定キーの値を順次読む。 */
function fieldValue(source: Record<string, unknown>, key: string): unknown {
  // entriesの各pairは新しい配列であり、shift/popは元入力を変更しない。
  for (const pair of Object.entries(source)) {
    if (pair.shift() === key) return pair.pop()
  }
  return null
}

/** 十進文字列の値をBigIntとして読む。 */
function intField(value: unknown): bigint | null {
  return parseDecimalInteger(value)
}

/** 真理値を型変換せず読む。 */
function boolField(value: unknown): boolean | null {
  if (typeof value !== 'boolean') return null
  return value
}

/** 文字列を型変換せず読む。 */
function textField(value: unknown): string | null {
  if (typeof value !== 'string') return null
  return value
}

/** 契約の `stateFields`（フラットなキー）を内部型へ読む。 */
function readState(source: Record<string, unknown>): StateFields | null {
  const half = textField(fieldValue(source, 'state.half'))
  const strikes = intField(fieldValue(source, 'state.count.strikes'))
  const balls = intField(fieldValue(source, 'state.count.balls'))
  const outs = intField(fieldValue(source, 'state.outs'))
  const runners = textField(fieldValue(source, 'state.runners'))
  const battingOrder = intField(fieldValue(source, 'state.battingOrder'))
  const tiebreakActive = boolField(fieldValue(source, 'state.tiebreakActive'))
  const gameEnded = boolField(fieldValue(source, 'state.gameEnded'))
  const inning = intField(fieldValue(source, 'state.inning'))
  const score = asObject(fieldValue(source, 'state.score'))
  if (score === null) return null
  const home = intField(fieldValue(score, 'home'))
  const away = intField(fieldValue(score, 'away'))
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
  const home = intField(innings.home)
  const away = intField(innings.away)
  const hits = intField(fieldValue(source, 'hits'))
  const errors = intField(fieldValue(source, 'errors'))
  const strikeouts = intField(fieldValue(source, 'strikeouts'))
  const walks = intField(fieldValue(source, 'walks'))
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
function derivedJson(
  derived: Derived,
  stack: Array<unknown> = [],
): Record<string, unknown> {
  const differences: Record<string, unknown> = {}
  if (derived.history.ballsBefore !== derived.history.ballsAfter) {
    Object.assign(differences, {
      'state.count.balls': {
        before: formatDecimalInteger(derived.history.ballsBefore),
        after: formatDecimalInteger(derived.history.ballsAfter),
      },
    })
  }
  if (derived.history.strikesBefore !== derived.history.strikesAfter) {
    Object.assign(differences, {
      'state.count.strikes': {
        before: formatDecimalInteger(derived.history.strikesBefore),
        after: formatDecimalInteger(derived.history.strikesAfter),
      },
    })
  }
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
    historyContext: (
      [
        {
          kind: 'confirmed-play',
          difference: {
            stateFields: differences,
            scoreboard: {},
            statFlags: derived.statFlags,
          },
        },
      ] as Array<unknown>
    ).concat(stack),
    after: {
      stateFields: stateJson(derived.after.stateFields),
      scoreboard: boardJson(derived.after.scoreboard),
    },
  }
}

/** 閉じたobjectの全必須キーと余剰キーを検査する。 */
function exactKeys(
  source: Record<string, unknown>,
  keys: Array<string>,
): boolean {
  return (
    Object.keys(source).every((key) => keys.includes(key)) &&
    keys.every((key) => Object.prototype.hasOwnProperty.call(source, key))
  )
}

/** 履歴の前後値を閉じた型として検査する。真正性や過去計算は推測しない。 */
function historyScalar(value: unknown, kind: string): DomainErrorCode | null {
  if (kind === 'integer') {
    if (parseDecimalInteger(value) === null) return 'INVALID_DECIMAL_INTEGER'
    return null
  }
  if (kind === 'boolean') {
    if (typeof value !== 'boolean') return 'INVALID_REQUEST'
    return null
  }
  if (kind === 'half') {
    if (value !== 'top' && value !== 'bottom') return 'INVALID_REQUEST'
    return null
  }
  if (kind === 'runners') {
    if (
      typeof value !== 'string' ||
      ![
        'empty',
        'first',
        'second',
        'third',
        'first-second',
        'first-third',
        'second-third',
        'loaded',
      ].includes(value)
    )
      return 'INVALID_REQUEST'
    return null
  }
  const score = asObject(value)
  if (score === null || !exactKeys(score, ['home', 'away']))
    return 'INVALID_REQUEST'
  if (
    parseDecimalInteger(score.home) === null ||
    parseDecimalInteger(score.away) === null
  )
    return 'INVALID_DECIMAL_INTEGER'
  return null
}

/** optional差分欄を落とさず全件検査し、未知欄を拒否する。 */
function historyFields(
  source: unknown,
  state: boolean,
): DomainErrorCode | null {
  const fields = asObject(source)
  if (fields === null) return 'INVALID_REQUEST'
  let keys = ['inningScores', 'hits', 'errors', 'strikeouts', 'walks']
  if (state)
    keys = [
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
    ]
  for (const item of Object.entries(fields)) {
    const key = item.shift()
    const value = item.pop()
    if (typeof key !== 'string' || !keys.includes(key)) return 'INVALID_REQUEST'
    const pair = asObject(value)
    if (pair === null || !exactKeys(pair, ['before', 'after']))
      return 'INVALID_REQUEST'
    let kind = 'integer'
    if (key === 'state.half') kind = 'half'
    if (key === 'state.runners') kind = 'runners'
    if (key === 'state.tiebreakActive' || key === 'state.gameEnded')
      kind = 'boolean'
    if (key === 'state.score' || key === 'inningScores') kind = 'score'
    const beforeError = historyScalar(pair.before, kind)
    if (beforeError !== null) return beforeError
    const afterError = historyScalar(pair.after, kind)
    if (afterError !== null) return afterError
  }
  return null
}

/** 履歴の欠落・余剰・型を検査する。既定stackやflagは生成しない。 */
function validateHistoryEntry(value: unknown): DomainErrorCode | null {
  const entry = asObject(value)
  if (
    entry === null ||
    !exactKeys(entry, ['kind', 'difference']) ||
    entry.kind !== 'confirmed-play'
  )
    return 'INVALID_REQUEST'
  const difference = asObject(entry.difference)
  if (
    difference === null ||
    !exactKeys(difference, ['stateFields', 'scoreboard', 'statFlags'])
  )
    return 'INVALID_REQUEST'
  const stateError = historyFields(difference.stateFields, true)
  if (stateError !== null) return stateError
  const boardError = historyFields(difference.scoreboard, false)
  if (boardError !== null) return boardError
  const flags = asObject(difference.statFlags)
  if (
    flags === null ||
    !exactKeys(flags, Object.keys(emptyFlags())) ||
    Object.values(flags).some((flag) => typeof flag !== 'boolean')
  )
    return 'INVALID_REQUEST'
  return null
}

/** 正規化済み一球だけを単一の数学核へ渡す。認可や保存ACKは返さない。 */
function evaluatePitch(requestJson: string, ordinary: boolean): string {
  if (typeof requestJson !== 'string') return errorResponse('INVALID_REQUEST')
  let parsed: unknown
  try {
    parsed = JSON.parse(requestJson) as unknown
  } catch {
    return errorResponse('INVALID_JSON')
  }
  const request = asObject(parsed)
  let requestKeys = ['eventKind', 'resultId', 'pitchEventKind', 'before']
  if (ordinary) requestKeys = requestKeys.concat(['history'])
  if (request === null || !exactKeys(request, requestKeys)) {
    return errorResponse('INVALID_REQUEST')
  }
  if (
    typeof request.eventKind !== 'string' ||
    typeof request.resultId !== 'string' ||
    typeof request.pitchEventKind !== 'string'
  )
    return errorResponse('INVALID_REQUEST')
  let stack: Array<unknown> = []
  if (ordinary) {
    const history = asObject(request.history)
    if (
      history === null ||
      !exactKeys(history, ['stack']) ||
      !Array.isArray(history.stack)
    )
      return errorResponse('INVALID_REQUEST')
    for (const entry of history.stack) {
      const historyError = validateHistoryEntry(entry)
      if (historyError !== null) return errorResponse(historyError)
    }
    stack = history.stack
  }
  const before = asObject(request.before)
  if (before === null || !exactKeys(before, ['stateFields', 'scoreboard']))
    return errorResponse('INVALID_REQUEST')
  const fields = asObject(before.stateFields)
  const board = asObject(before.scoreboard)
  if (
    fields === null ||
    board === null ||
    !exactKeys(fields, [
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
    ]) ||
    !exactKeys(board, ['inningScores', 'hits', 'errors', 'strikeouts', 'walks'])
  )
    return errorResponse('INVALID_REQUEST')
  const score = asObject(fieldValue(fields, 'state.score'))
  const innings = asObject(board.inningScores)
  if (
    score === null ||
    innings === null ||
    !exactKeys(score, ['home', 'away']) ||
    !exactKeys(innings, ['home', 'away'])
  )
    return errorResponse('INVALID_REQUEST')
  // 検査器が許す固定field参照だけを使い、動的添字へ拡張しない。
  const integerValues = [
    fieldValue(fields, 'state.count.strikes'),
    fieldValue(fields, 'state.count.balls'),
    fieldValue(fields, 'state.outs'),
    fieldValue(fields, 'state.battingOrder'),
    fieldValue(fields, 'state.inning'),
    board.hits,
    board.errors,
    board.strikeouts,
    board.walks,
    score.home,
    score.away,
    innings.home,
    innings.away,
  ]
  if (integerValues.some((value) => parseDecimalInteger(value) === null)) {
    return errorResponse('INVALID_DECIMAL_INTEGER')
  }
  const state = readState(fields)
  const scoreboard = readBoard(board)
  if (state === null || scoreboard === null)
    return errorResponse('INVALID_REQUEST')
  if (request.eventKind !== 'batting-result')
    return errorResponse('UNSUPPORTED_T1_SCOPE')
  let calculator = derive
  if (ordinary) calculator = deriveOrdinary
  const derived = calculator(
    state,
    scoreboard,
    request.resultId,
    request.pitchEventKind,
  )
  if (derived === null) return errorResponse('UNSUPPORTED_T1_SCOPE')
  return JSON.stringify({ ok: true, value: derivedJson(derived, stack) })
}

/** 既初球の要求形・成功範囲を変えない。 */
function deriveState(requestJson: string): string {
  return evaluatePitch(requestJson, false)
}

/** 必須履歴と通常33座標だけを単一計算核へ渡す。 */
function deriveOrdinaryPitch(requestJson: string): string {
  return evaluatePitch(requestJson, true)
}

type T1Evaluation =
  | { ok: false; code: DomainErrorCode }
  | { ok: true; before: StateFields; board: Scoreboard; derived: Derived }

/** T2接続の正規化・一回評価。既deriveの単一計算核を共有する。 */
function evaluateT1(parsed: unknown): T1Evaluation {
  const request = asObject(parsed)
  if (
    request === null ||
    !exactKeys(request, ['eventKind', 'resultId', 'pitchEventKind', 'before'])
  ) {
    return { ok: false, code: 'INVALID_REQUEST' }
  }
  if (
    typeof request.eventKind !== 'string' ||
    typeof request.resultId !== 'string' ||
    typeof request.pitchEventKind !== 'string'
  )
    return { ok: false, code: 'INVALID_REQUEST' }
  const before = asObject(request.before)
  if (before === null || !exactKeys(before, ['stateFields', 'scoreboard']))
    return { ok: false, code: 'INVALID_REQUEST' }
  const fields = asObject(before.stateFields)
  const board = asObject(before.scoreboard)
  if (
    fields === null ||
    board === null ||
    !exactKeys(fields, [
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
    ]) ||
    !exactKeys(board, ['inningScores', 'hits', 'errors', 'strikeouts', 'walks'])
  )
    return { ok: false, code: 'INVALID_REQUEST' }
  const score = asObject(fieldValue(fields, 'state.score'))
  const innings = asObject(board.inningScores)
  if (
    score === null ||
    innings === null ||
    !exactKeys(score, ['home', 'away']) ||
    !exactKeys(innings, ['home', 'away'])
  )
    return { ok: false, code: 'INVALID_REQUEST' }
  // 検査器が許す固定field参照だけを使い、動的添字へ拡張しない。
  const integerValues = [
    fieldValue(fields, 'state.count.strikes'),
    fieldValue(fields, 'state.count.balls'),
    fieldValue(fields, 'state.outs'),
    fieldValue(fields, 'state.battingOrder'),
    fieldValue(fields, 'state.inning'),
    board.hits,
    board.errors,
    board.strikeouts,
    board.walks,
    score.home,
    score.away,
    innings.home,
    innings.away,
  ]
  if (integerValues.some((value) => parseDecimalInteger(value) === null)) {
    return { ok: false, code: 'INVALID_DECIMAL_INTEGER' }
  }
  const state = readState(fields)
  const scoreboard = readBoard(board)
  if (state === null || scoreboard === null)
    return { ok: false, code: 'INVALID_REQUEST' }
  if (request.eventKind !== 'batting-result')
    return { ok: false, code: 'UNSUPPORTED_T1_SCOPE' }
  const derived = derive(
    state,
    scoreboard,
    request.resultId,
    request.pitchEventKind,
  )
  if (derived === null) return { ok: false, code: 'UNSUPPORTED_T1_SCOPE' }
  return { ok: true, before: state, board: scoreboard, derived: derived }
}

/** 一回のT1評価を同じartifact内の限定T2へ接続する。未評価は保存成功にしない。 */
function deriveFirstPitchWithContinuation(requestJson: string): string {
  if (typeof requestJson !== 'string') return errorResponse('INVALID_REQUEST')
  let parsed: unknown
  try {
    parsed = JSON.parse(requestJson) as unknown
  } catch {
    return errorResponse('INVALID_JSON')
  }
  const request = asObject(parsed)
  if (request === null || !exactKeys(request, ['t1', 'rules']))
    return errorResponse('INVALID_REQUEST')
  const rules = readContinuationRules(request.rules)
  if (!rules.ok) return errorResponse(rules.code)
  const result = evaluateT1(request.t1)
  if (!result.ok) return errorResponse(result.code)
  const t1 = derivedJson(result.derived)
  let t2: Record<string, unknown> | null
  try {
    t2 = evaluateFirstPitchContinuation(
      result.before,
      result.board,
      result.derived,
      rules.value,
    )
  } catch {
    return JSON.stringify({
      ok: false,
      error: { code: 'T2_NOT_EVALUATED' },
      value: {
        t1: t1,
        t2: { kind: 'not-evaluated', reason: 'evaluation-unavailable' },
      },
    })
  }
  if (t2 === null)
    return JSON.stringify({
      ok: false,
      error: { code: 'T2_NOT_EVALUATED' },
      value: {
        t1: t1,
        t2: { kind: 'not-evaluated', reason: 'input-not-in-closed-unit' },
      },
    })
  return JSON.stringify({ ok: true, value: { t1: t1, t2: t2 } })
}

/** JSON文字列だけの公開表。未実装の取消/訂正/他結果は公開しない。 */
export const domainOperations = Object.freeze({
  ping,
  deriveState,
  deriveOrdinaryPitch,
  deriveFirstPitchWithContinuation,
  validateInitialGameRoster,
  quantizeCourse,
})
