import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'
import {
  readContinuationRules,
  type ContinuationRules,
} from './firstPitchContinuation'

type JsonObject = Record<string, unknown>
type Prepared =
  | { ok: true; request: JsonObject; t1: JsonObject }
  | { ok: false; response: string }

/** 閉じたJSON objectを読む。 */
function object(value: unknown, keys: Array<string>): JsonObject | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    return null
  const source = value as JsonObject
  if (
    !Object.keys(source).every((key) => keys.includes(key)) ||
    !keys.every((key) => Object.prototype.hasOwnProperty.call(source, key))
  )
    return null
  return source
}

/** key順に依存せず、余剰/欠落も含めて全値を比較する。 */
export function sameContinuationValue(left: unknown, right: unknown): boolean {
  if (left === right) return true
  if (Array.isArray(left) && Array.isArray(right)) {
    const remaining = right.slice() as Array<unknown>
    for (const value of left) {
      if (!sameContinuationValue(value, remaining.shift())) return false
    }
    return !remaining.some(() => true)
  }
  if (
    left === null ||
    right === null ||
    typeof left !== 'object' ||
    typeof right !== 'object' ||
    Array.isArray(left) ||
    Array.isArray(right)
  )
    return false
  const entries = Object.entries(right)
  for (const pair of Object.entries(left)) {
    const key = pair.shift()
    const value = pair.pop()
    const other = entries.find((candidate) => candidate.slice().shift() === key)
    if (
      typeof other === 'undefined' ||
      !sameContinuationValue(value, other.slice().pop())
    )
      return false
  }
  return Object.keys(right).every((key) =>
    Object.prototype.hasOwnProperty.call(left, key),
  )
}

/** 封筒を固定形で返す。入力値や資格をエラーへ混ぜない。 */
function failure(code: string): string {
  return JSON.stringify({ ok: false, error: { code: code } })
}

/** UUIDをホスト正規表現なしで正準の小文字8-4-4-4-12形に制限する。 */
function uuid(value: unknown): boolean {
  if (typeof value !== 'string') return false
  let offset = 0n
  for (const character of value) {
    if (offset === 8n || offset === 13n || offset === 18n || offset === 23n) {
      if (character !== '-') return false
    } else if (!(
      (character >= '0' && character <= '9') ||
      (character >= 'a' && character <= 'f')
    ))
      return false
    offset = offset + 1n
  }
  return offset === 36n
}

/** D4は整数に変換しないopaque記録世代である。 */
function generation(value: unknown): boolean {
  if (typeof value !== 'string') return false
  let size = 0n
  for (const character of value) {
    // 文字列として走査するだけで、その内容に意味を与えない。
    if (typeof character !== 'string') return false
    size = size + 1n
  }
  return size > 0n && size <= 128n
}

/** ordinary-only水位とD4を混同せず参照を読む。真正性は接続側で確認する。 */
function prefix(value: unknown): JsonObject | null {
  const result = object(value, [
    'version',
    'tenantId',
    'gameId',
    'generation',
    'length',
  ])
  if (
    result === null ||
    result.version !== '1' ||
    !uuid(result.tenantId) ||
    !uuid(result.gameId) ||
    !generation(result.generation)
  )
    return null
  const length = parseDecimalInteger(result.length)
  if (length === null || length < 0n) return null
  return result
}

/** 新しい保存意味を決めず、採用済DRAW-01..04の相関だけを検査する。 */
function validRules(rules: ContinuationRules): boolean {
  if (
    rules.extensionLimit !== null &&
    rules.extensionLimit < rules.regulationInnings
  )
    return false
  if (
    rules.coldConditions.some(
      (stage) => stage.startInning > rules.regulationInnings,
    )
  )
    return false
  if (
    rules.tiebreak !== null &&
    (rules.tiebreak.startInning <= rules.regulationInnings ||
      (rules.extensionLimit !== null &&
        rules.tiebreak.startInning > rules.extensionLimit))
  )
    return false
  return true
}

/** 同じ攻撃中の非終端stateから、実規則の非成立根拠を評価する。 */
function ordinaryBasis(
  snapshot: unknown,
  rules: ContinuationRules,
): JsonObject | null {
  const view = object(snapshot, ['stateFields', 'scoreboard'])
  if (
    view === null ||
    view.stateFields === null ||
    typeof view.stateFields !== 'object' ||
    Array.isArray(view.stateFields)
  )
    return null
  const fields = view.stateFields as JsonObject
  const entries = Object.entries(fields)
  const read = (key: string): unknown => {
    const found = entries.find((pair) => pair.slice().shift() === key)
    if (typeof found === 'undefined') return null
    return found.slice().pop()
  }
  const inning = parseDecimalInteger(read('state.inning'))
  const half = read('state.half')
  const score = object(read('state.score'), ['home', 'away'])
  if (
    score === null ||
    inning === null ||
    inning < 1n ||
    (half !== 'top' && half !== 'bottom') ||
    read('state.gameEnded') !== false
  )
    return null
  const home = parseDecimalInteger(score.home)
  const away = parseDecimalInteger(score.away)
  if (home === null || away === null || home < 0n || away < 0n) return null
  if (rules.extensionLimit !== null && inning > rules.extensionLimit)
    return null
  // 今回は通常open系列。再開後の例外状態に対する恒久的な意味拒否ではない。
  if (
    (half === 'bottom' && inning >= rules.regulationInnings && home > away) ||
    (half === 'top' && inning > rules.regulationInnings && home > away)
  )
    return null
  let expectedTiebreak = false
  if (rules.tiebreak !== null && inning >= rules.tiebreak.startInning)
    expectedTiebreak = true
  if (read('state.tiebreakActive') !== expectedTiebreak) return null
  let branches: Array<string> = []
  for (const stage of rules.coldConditions) {
    let branch = 'COLD-06'
    if (inning < stage.startInning) branch = 'COLD-01'
    else if (half === 'top') {
      branch = 'COLD-01'
      if (away - home >= stage.pointDifference) branch = 'COLD-04'
    } else {
      if (home - away >= stage.pointDifference) return null
      if (away - home >= stage.pointDifference) branch = 'COLD-04'
    }
    branches = branches.concat([branch])
  }
  let drawBranch = 'DRAW-07'
  if (rules.extensionLimit !== null) drawBranch = 'DRAW-08'
  let extension: string | null = null
  if (rules.extensionLimit !== null)
    extension = formatDecimalInteger(rules.extensionLimit)
  return {
    regulationInnings: formatDecimalInteger(rules.regulationInnings),
    inning: formatDecimalInteger(inning),
    half: half,
    halfCompleted: false,
    coldBranches: branches,
    coldAggregate: 'COLD-07',
    drawBranch: drawBranch,
    scoreUnchanged: true,
    outsUnchanged: true,
    priorOpen: true,
    tiebreakActive: expectedTiebreak,
    configuredExtensionLimit: extension,
  }
}

/** 始点/旧初球の限定stateを値全体から検査する。 */
function initialSnapshot(snapshot: unknown, balls: string): boolean {
  return sameContinuationValue(snapshot, {
    stateFields: {
      'state.half': 'top',
      'state.count.strikes': '0',
      'state.count.balls': balls,
      'state.outs': '0',
      'state.runners': 'empty',
      'state.battingOrder': '1',
      'state.tiebreakActive': false,
      'state.gameEnded': false,
      'state.inning': '1',
      'state.score': { home: '0', away: '0' },
    },
    scoreboard: {
      inningScores: { home: '0', away: '0' },
      hits: '0',
      errors: '0',
      strikeouts: '0',
      walks: '0',
    },
  })
}

/** 前回T2を現在rules/afterへ結合し、合法封筒の移植も拒否する。 */
function previousEvaluation(
  prior: JsonObject,
  rules: ContinuationRules,
): boolean {
  const nextBasis = ordinaryBasis(prior.after, rules)
  if (nextBasis === null) return false
  const t2 = object(prior.t2, ['kind', 'scope', 'evaluation_point', 'basis'])
  if (t2 !== null)
    return sameContinuationValue(t2, {
      kind: 'evaluated-no-end-condition',
      scope: 'ordinary37',
      evaluation_point: 'post-play',
      basis: nextBasis,
    })
  if (
    !initialSnapshot(prior.after, '1') ||
    rules.coldConditions.some(() => true) ||
    rules.tiebreak !== null ||
    (rules.regulationInnings !== 7n && rules.regulationInnings !== 9n) ||
    (rules.extensionLimit !== null &&
      !(rules.regulationInnings === 9n && rules.extensionLimit === 9n))
  )
    return false
  let extension: string | null = null
  if (rules.extensionLimit !== null)
    extension = formatDecimalInteger(rules.extensionLimit)
  return sameContinuationValue(prior.t2, {
    kind: 'evaluated-no-end-condition',
    evaluation_point: 'post-play',
    basis: {
      regulation: {
        kind: 'before-regulation-completion',
        regulation_innings: formatDecimalInteger(rules.regulationInnings),
        observed_inning: '1',
        observed_half: 'top',
      },
      cold: { kind: 'no-configured-cold-condition' },
      extra_and_draw: {
        kind: 'before-extra-inning-boundary',
        configured_extension_limit: extension,
      },
      walk_off: { kind: 'top-half-without-score-change' },
    },
  })
}

/** 新ABIを閉検査し、計算より先に参照/前回lock不整合を拒否する。 */
export function prepareOrdinaryContinuation(requestJson: string): Prepared {
  if (typeof requestJson !== 'string')
    return { ok: false, response: failure('INVALID_REQUEST') }
  let value: unknown
  try {
    value = JSON.parse(requestJson) as unknown
  } catch {
    return { ok: false, response: failure('INVALID_JSON') }
  }
  const request = object(value, [
    'version',
    'prefixRef',
    'rules',
    't1',
    'prior',
  ])
  if (
    request === null ||
    request.version !== '1' ||
    prefix(request.prefixRef) === null
  )
    return { ok: false, response: failure('INVALID_REQUEST') }
  const t1 = object(request.t1, [
    'eventKind',
    'resultId',
    'pitchEventKind',
    'before',
  ])
  const prior = object(request.prior, [
    'kind',
    'prefixRef',
    'rules',
    'after',
    't2',
  ])
  if (
    t1 === null ||
    prior === null ||
    prefix(prior.prefixRef) === null ||
    !['started-initial', 'evaluated-prefix', 'locked-prefix'].includes(
      prior.kind as string,
    )
  )
    return { ok: false, response: failure('INVALID_REQUEST') }
  const rules = readContinuationRules(request.rules)
  const previousRules = readContinuationRules(prior.rules)
  if (!rules.ok) return { ok: false, response: failure(rules.code) }
  if (!previousRules.ok)
    return { ok: false, response: failure(previousRules.code) }
  if (
    !sameContinuationValue(request.prefixRef, prior.prefixRef) ||
    !sameContinuationValue(request.rules, prior.rules) ||
    !sameContinuationValue(t1.before, prior.after) ||
    prior.kind === 'locked-prefix'
  )
    return { ok: false, response: failure('T2_NOT_EVALUATED') }
  const ref = prefix(request.prefixRef)
  if (ref === null) return { ok: false, response: failure('INVALID_REQUEST') }
  const length = parseDecimalInteger(ref.length)
  if (prior.kind === 'started-initial') {
    if (
      length !== 0n ||
      prior.t2 !== null ||
      !initialSnapshot(prior.after, '0')
    )
      return { ok: false, response: failure('T2_NOT_EVALUATED') }
  } else if (length === null || length < 1n)
    return { ok: false, response: failure('T2_NOT_EVALUATED') }
  // T1の既拒否順を保つため、非対応stateは同一T1評価後にT2で拒否する。
  return { ok: true, request: request, t1: t1 }
}

/** T1一回分の結果を無再計算で今回entryへ射影する。全履歴は返さない。 */
export function finishOrdinaryContinuation(
  request: JsonObject,
  t1Json: string,
): string {
  const response = JSON.parse(t1Json) as JsonObject
  if (response.ok !== true) return t1Json
  const value = response.value as JsonObject
  const prior = request.prior as JsonObject
  const rules = readContinuationRules(request.rules)
  if (!rules.ok || !validRules(rules.value)) return failure('T2_NOT_EVALUATED')
  if (
    prior.kind === 'evaluated-prefix' &&
    !previousEvaluation(prior, rules.value)
  )
    return failure('T2_NOT_EVALUATED')
  const t1 = request.t1 as JsonObject
  const before = t1.before as JsonObject
  const after = value.after as JsonObject
  const beforeFields = before.stateFields as JsonObject
  const afterFields = after.stateFields as JsonObject
  const beforeRest = Object.entries(beforeFields).filter(
    (pair) =>
      !['state.count.strikes', 'state.count.balls'].includes(
        pair.slice().shift() as string,
      ),
  )
  const afterRest = Object.entries(afterFields).filter(
    (pair) =>
      !['state.count.strikes', 'state.count.balls'].includes(
        pair.slice().shift() as string,
      ),
  )
  if (
    !sameContinuationValue(
      Object.fromEntries(beforeRest),
      Object.fromEntries(afterRest),
    ) ||
    !sameContinuationValue(before.scoreboard, after.scoreboard) ||
    !sameContinuationValue(value.outEffect, { count: '0', targets: [] }) ||
    value.plateAppearanceEnded !== false
  )
    return failure('T2_NOT_EVALUATED')
  const basis = ordinaryBasis(before, rules.value)
  if (basis === null) return failure('T2_NOT_EVALUATED')
  const stack = value.historyContext
  if (!Array.isArray(stack)) return failure('T2_NOT_EVALUATED')
  const entries = stack.slice() as Array<unknown>
  const entry = entries.shift()
  if (typeof entry === 'undefined' || entries.some(() => true))
    return failure('T2_NOT_EVALUATED')
  const projected = {
    countEffect: value.countEffect,
    plateAppearanceEnded: value.plateAppearanceEnded,
    batterDestination: value.batterDestination,
    runnerDefaultAdvance: value.runnerDefaultAdvance,
    outEffect: value.outEffect,
    statFlags: value.statFlags,
    after: value.after,
  }
  const ref = prefix(request.prefixRef)
  if (ref === null) return failure('T2_NOT_EVALUATED')
  const length = parseDecimalInteger(ref.length)
  if (length === null) return failure('T2_NOT_EVALUATED')
  return JSON.stringify({
    ok: true,
    value: {
      t1: projected,
      t2: {
        kind: 'evaluated-no-end-condition',
        scope: 'ordinary37',
        evaluation_point: 'post-play',
        basis: basis,
      },
      newHistoryEntry: entry,
      previousPrefixRef: ref,
      nextPrefixRef: {
        version: ref.version,
        tenantId: ref.tenantId,
        gameId: ref.gameId,
        generation: ref.generation,
        length: formatDecimalInteger(length + 1n),
      },
    },
  })
}
