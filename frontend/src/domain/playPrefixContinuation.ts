import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'
import { readContinuationRules } from './firstPitchContinuation'
import {
  sameContinuationValue,
  canonicalContinuationUuid,
  canonicalContinuationGeneration,
  readOrdinaryPrefixRef,
  evaluateOpenPrefixBasis,
  isInitialPrefixSnapshot,
  ordinaryPreviousEvaluation,
} from './ordinaryPitchContinuation'

type Json = Record<string, unknown>
type Prepared =
  | {
      ok: true
      request: Json
      t1: Json
      terminal: boolean
      responsiblePitcherId: string
    }
  | { ok: false; response: string }

/** 閉objectと固定fieldを読む。source資格の真正性は保存側が所有する。 */
function object(value: unknown, keys: Array<string>): Json | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    return null
  const view = value as Json
  if (
    !Object.keys(view).every((key) => keys.includes(key)) ||
    !keys.every((key) => Object.prototype.hasOwnProperty.call(view, key))
  )
    return null
  return view
}
function read(view: Json, key: string): unknown {
  for (const pair of Object.entries(view))
    if (pair.slice().shift() === key) return pair.slice().pop()
  return null
}
function unsigned(value: unknown): bigint | null {
  const n = parseDecimalInteger(value)
  if (n === null || n < 0n) return null
  return n
}
function digest(value: unknown): boolean {
  if (typeof value !== 'string') return false
  let size = 0n
  for (const c of value) {
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false
    size = size + 1n
  }
  return size === 64n
}
function checkpoint(value: unknown): Json | null {
  const v = object(value, ['id', 'revision', 'digest'])
  if (v === null || !canonicalContinuationUuid(v.id) || !digest(v.digest))
    return null
  const revision = unsigned(v.revision)
  if (revision === null || revision < 1n) return null
  return v
}
function playIdentity(value: unknown): Json | null {
  const v = object(value, ['eventId', 'd5', 'playId'])
  if (v === null || !Object.values(v).every(canonicalContinuationUuid))
    return null
  return v
}
/** v1普通球長とv2全play長を別型で保持し、bridge元を不変に束縛する。 */
function prefix(value: unknown): Json | null {
  const v = object(value, [
    'version',
    'scope',
    'tenantId',
    'gameId',
    'generation',
    'length',
    'checkpoint',
    'historyVersion',
    'origin',
  ])
  if (
    v === null ||
    v.version !== '2' ||
    v.scope !== 'play-prefix-v2' ||
    !canonicalContinuationUuid(v.tenantId) ||
    !canonicalContinuationUuid(v.gameId) ||
    !canonicalContinuationGeneration(v.generation) ||
    checkpoint(v.checkpoint) === null ||
    unsigned(v.historyVersion) === null
  )
    return null
  const origin = readOrdinaryPrefixRef(v.origin)
  const length = unsigned(v.length)
  if (
    origin === null ||
    length === null ||
    origin.tenantId !== v.tenantId ||
    origin.gameId !== v.gameId ||
    origin.generation !== v.generation
  )
    return null
  const originLength = unsigned(origin.length)
  if (originLength === null || length < originLength) return null
  return v
}
function failure(code: string): string {
  return JSON.stringify({ ok: false, error: { code: code } })
}
function reject(code: string): Prepared {
  return { ok: false, response: failure(code) }
}

/** 新v2だけで正準占有と旧ABI占有を明示変換する。旧公開ABIを変更しない。 */
function snapshotVocabulary(value: Json, legacy: boolean): Json {
  const fields = value.stateFields as Json
  let runners = read(fields, 'state.runners')
  if (legacy && runners === 'first-second-third') runners = 'loaded'
  if (!legacy && runners === 'loaded') runners = 'first-second-third'
  return {
    stateFields: Object.assign({}, fields, { 'state.runners': runners }),
    scoreboard: value.scoreboard,
  }
}

/** 識別子snapshotの塁と占有が完全一致することを照合する。帰属を推測しない。 */
function runnersMatch(value: unknown, snapshot: Json): boolean {
  if (!Array.isArray(value)) return false
  const fields = snapshot.stateFields as Json
  const occupied = read(fields, 'state.runners')
  const bases: Array<string> = []
  const players: Array<string> = []
  let names: Array<string> = []
  for (const raw of value) {
    const runner = object(raw, [
      'runnerId',
      'responsiblePitcherId',
      'base',
      'status',
      'statusSource',
    ])
    if (
      runner === null ||
      !canonicalContinuationUuid(runner.runnerId) ||
      !canonicalContinuationUuid(runner.responsiblePitcherId) ||
      typeof runner.base !== 'string' ||
      typeof runner.runnerId !== 'string' ||
      !['1', '2', '3'].includes(runner.base) ||
      bases.includes(runner.base) ||
      players.includes(runner.runnerId) ||
      runner.status !== '継続' ||
      runner.statusSource !== 'auto'
    )
      return false
    Object.assign(bases, bases.concat([runner.base]))
    Object.assign(players, players.concat([runner.runnerId]))
  }
  if (bases.includes('1')) names = names.concat(['first'])
  if (bases.includes('2')) names = names.concat(['second'])
  if (bases.includes('3')) names = names.concat(['third'])
  if (!names.some(() => true)) return occupied === 'empty'
  return names.join('-') === occupied
}

/** A-2の有限証拠から責任投手を唯一の核で判断する。未解決を現在投手へ補完しない。 */
function responsibility(source: Json, t1: Json): string | null {
  const p = source.participants as Json
  const proof = object(source.responsibility, [
    'kind',
    'paStartSource',
    'previousPitcherId',
    'strikesAtChange',
    'ballsAtChange',
  ])
  if (proof === null || typeof p.pitcherId !== 'string') return null
  const pa = object(proof.paStartSource, ['kind', 'id'])
  if (
    pa === null ||
    !canonicalContinuationUuid(pa.id) ||
    !['started-game', 'confirmed-play'].includes(pa.kind as string)
  )
    return null
  const ref = source.prefixRef as Json
  if (pa.kind === 'started-game' && pa.id !== ref.gameId) return null
  let expected = p.pitcherId
  if (proof.kind === 'no-change') {
    if (
      proof.previousPitcherId !== null ||
      proof.strikesAtChange !== null ||
      proof.ballsAtChange !== null
    )
      return null
  } else if (proof.kind === 'one-change') {
    const strikes = unsigned(proof.strikesAtChange)
    const balls = unsigned(proof.ballsAtChange)
    const fields = (t1.before as Json).stateFields as Json
    const currentStrikes = unsigned(read(fields, 'state.count.strikes'))
    const currentBalls = unsigned(read(fields, 'state.count.balls'))
    if (
      !canonicalContinuationUuid(proof.previousPitcherId) ||
      proof.previousPitcherId === p.pitcherId ||
      strikes === null ||
      strikes > 2n ||
      balls === null ||
      balls > 3n ||
      currentStrikes === null ||
      currentBalls === null ||
      strikes > currentStrikes ||
      balls > currentBalls
    )
      return null
    if (
      t1.resultId === 'batting-result.walk' &&
      (balls === 3n || (balls === 2n && strikes <= 1n))
    )
      expected = proof.previousPitcherId as string
  } else return null
  return expected
}

/** 保存原本由来とされるbridge証拠の全内部関係を検査する。DB真正性は主張しない。 */
function bridgeMatches(source: Json, ref: Json): boolean {
  const bridge = object(source.bridge, [
    'kind',
    'v1Ref',
    'ordinaryPlayCount',
    'allPlayCount',
    'historyDepth',
    'lastSource',
    'priorArtifactSha256',
    'rulesDigest',
    'layoutDigest',
    'checkpoint',
  ])
  if (
    bridge === null ||
    !sameContinuationValue(bridge.v1Ref, ref.origin) ||
    !sameContinuationValue(bridge.checkpoint, ref.checkpoint) ||
    bridge.ordinaryPlayCount !== ref.length ||
    bridge.allPlayCount !== ref.length ||
    bridge.historyDepth !== source.historyDepth ||
    !sameContinuationValue(bridge.lastSource, source.lastSource) ||
    bridge.priorArtifactSha256 !== source.priorArtifactSha256 ||
    bridge.rulesDigest !== source.rulesDigest ||
    bridge.layoutDigest !== source.layoutDigest
  )
    return false
  const origin = ref.origin as Json
  if (ref.length !== origin.length) return false
  if (ref.length === '0')
    return (
      bridge.kind === 'started-initial' &&
      source.lastSource === null &&
      source.t2 === null &&
      isInitialPrefixSnapshot(
        snapshotVocabulary(source.after as Json, true),
        '0',
      )
    )
  const rules = readContinuationRules(source.rules)
  return (
    bridge.kind === 'ordinary-only-confirmed' &&
    rules.ok &&
    ordinaryPreviousEvaluation(
      { after: snapshotVocabulary(source.after as Json, true), t2: source.t2 },
      rules.value,
    )
  )
}

/** v2のsource/参照/前回openを先に検査し、計算には履歴空stackだけを渡す。 */
export function preparePlayPrefixContinuation(text: string): Prepared {
  if (typeof text !== 'string') return reject('INVALID_REQUEST')
  let parsed: unknown
  try {
    parsed = JSON.parse(text) as unknown
  } catch {
    return reject('INVALID_JSON')
  }
  const request = object(parsed, [
    'version',
    'prefixRef',
    'rules',
    't1',
    'source',
    'playIdentity',
    'nextCheckpoint',
  ])
  if (request === null || request.version !== '2')
    return reject('INVALID_REQUEST')
  const ref = prefix(request.prefixRef)
  const t1 = object(request.t1, [
    'eventKind',
    'resultId',
    'pitchEventKind',
    'before',
  ])
  const source = object(request.source, [
    'kind',
    'prefixRef',
    'rules',
    'after',
    't2',
    'historyDepth',
    'playCount',
    'lastSource',
    'position',
    'priorArtifactSha256',
    'executionArtifactSha256',
    'rulesDigest',
    'layoutDigest',
    'runners',
    'participants',
    'nextBatter',
    'bridge',
    'responsibility',
  ])
  const next = checkpoint(request.nextCheckpoint)
  if (
    ref === null ||
    t1 === null ||
    source === null ||
    next === null ||
    playIdentity(request.playIdentity) === null ||
    typeof t1.eventKind !== 'string' ||
    typeof t1.resultId !== 'string' ||
    typeof t1.pitchEventKind !== 'string' ||
    !['bridged-v1', 'evaluated-prefix-v2', 'locked-prefix-v2'].includes(
      source.kind as string,
    )
  )
    return reject('INVALID_REQUEST')
  const after = object(source.after, ['stateFields', 'scoreboard'])
  const participants = object(source.participants, [
    'batterId',
    'pitcherId',
    'battingOrder',
  ])
  const position = object(source.position, ['d1', 'd2', 'appliedWatermark'])
  if (
    after === null ||
    participants === null ||
    !canonicalContinuationUuid(participants.batterId) ||
    !canonicalContinuationUuid(participants.pitcherId) ||
    position === null ||
    Object.values(position).some((v) => unsigned(v) === null) ||
    !digest(source.priorArtifactSha256) ||
    !digest(source.executionArtifactSha256) ||
    !digest(source.rulesDigest) ||
    !digest(source.layoutDigest)
  )
    return reject('INVALID_REQUEST')
  const fields = after.stateFields
  if (fields === null || typeof fields !== 'object' || Array.isArray(fields))
    return reject('INVALID_REQUEST')
  const board = object(after.scoreboard, [
    'inningScores',
    'hits',
    'errors',
    'strikeouts',
    'walks',
  ])
  if (
    board === null ||
    !sameContinuationValue(
      read(fields as Json, 'state.score'),
      board.inningScores,
    )
  )
    return reject('PREFIX_SOURCE_MISMATCH')
  const previousCheckpoint = ref.checkpoint as Json
  const revision = unsigned(previousCheckpoint.revision)
  const nextRevision = unsigned(next.revision)
  if (
    !sameContinuationValue(source.prefixRef, ref) ||
    !sameContinuationValue(source.rules, request.rules) ||
    !sameContinuationValue(source.after, t1.before) ||
    participants.battingOrder !== read(fields as Json, 'state.battingOrder') ||
    source.historyDepth !== ref.length ||
    source.playCount !== ref.length ||
    revision === null ||
    nextRevision !== revision + 1n ||
    next.id === previousCheckpoint.id ||
    !runnersMatch(source.runners, after)
  )
    return reject('PREFIX_SOURCE_MISMATCH')
  if (ref.length === '0') {
    if (source.lastSource !== null) return reject('PREFIX_SOURCE_MISMATCH')
  } else if (playIdentity(source.lastSource) === null)
    return reject('PREFIX_SOURCE_MISMATCH')
  if (source.lastSource !== null) {
    const last = source.lastSource as Json
    const current = request.playIdentity as Json
    if (
      last.eventId === current.eventId ||
      last.d5 === current.d5 ||
      last.playId === current.playId
    )
      return reject('PREFIX_SOURCE_MISMATCH')
  }
  const rules = readContinuationRules(request.rules)
  if (!rules.ok) return reject(rules.code)
  if (source.kind === 'locked-prefix-v2') return reject('T2_NOT_EVALUATED')
  if (source.kind === 'bridged-v1') {
    if (!bridgeMatches(source, ref)) return reject('PREFIX_SOURCE_MISMATCH')
  } else {
    const origin = ref.origin as Json
    const length = unsigned(ref.length)
    const originLength = unsigned(origin.length)
    const basis = evaluateOpenPrefixBasis(
      snapshotVocabulary(after, true),
      rules.value,
    )
    if (
      source.bridge !== null ||
      length === null ||
      originLength === null ||
      length <= originLength ||
      basis === null ||
      !sameContinuationValue(source.t2, {
        kind: 'evaluated-no-end-condition',
        scope: 'play-prefix-v2',
        evaluation_point: 'post-play',
        basis: basis,
      })
    )
      return reject('T2_NOT_EVALUATED')
  }
  const responsible = responsibility(source, t1)
  if (responsible === null) return reject('PREFIX_SOURCE_MISMATCH')
  let terminal = false
  if (
    t1.resultId === 'batting-result.walk' ||
    t1.resultId === 'batting-result.hit-by-pitch'
  )
    terminal = true
  let before = t1.before as Json
  if (!terminal) before = snapshotVocabulary(before, true)
  return {
    ok: true,
    request: request,
    t1: {
      eventKind: t1.eventKind,
      resultId: t1.resultId,
      pitchEventKind: t1.pitchEventKind,
      before: before,
      history: { stack: [] },
    },
    terminal: terminal,
    responsiblePitcherId: responsible,
  }
}

/** 同一T1のafterを既T2核へ渡し、今回entry/runner/参照だけを射影する。 */
export function finishPlayPrefixContinuation(
  request: Json,
  responseJson: string,
  responsiblePitcherId: string,
): string {
  const response = JSON.parse(responseJson) as Json
  if (response.ok !== true) return responseJson
  const value = response.value as Json
  const input = request.t1 as Json
  const source = request.source as Json
  const rules = readContinuationRules(request.rules)
  if (!rules.ok) return failure('T2_NOT_EVALUATED')
  const after = snapshotVocabulary(value.after as Json, false)
  const basis = evaluateOpenPrefixBasis(
    snapshotVocabulary(after, true),
    rules.value,
  )
  if (basis === null) return failure('T2_NOT_EVALUATED')
  const history = value.historyContext
  if (!Array.isArray(history)) return failure('T2_NOT_EVALUATED')
  const entries = history.slice() as Array<unknown>
  const entry = entries.shift()
  if (typeof entry === 'undefined' || entries.some(() => true))
    return failure('T2_NOT_EVALUATED')
  const participants = source.participants as Json
  let nextParticipants = participants
  let runners = source.runners
  if (value.plateAppearanceEnded === true) {
    if (
      input.resultId !== 'batting-result.walk' &&
      input.resultId !== 'batting-result.hit-by-pitch'
    )
      return failure('UNSUPPORTED_T1_SCOPE')
    const next = object(source.nextBatter, ['batterId', 'battingOrder'])
    if (
      next === null ||
      !canonicalContinuationUuid(next.batterId) ||
      next.batterId === participants.batterId ||
      next.battingOrder !==
        read(after.stateFields as Json, 'state.battingOrder')
    )
      return failure('PREFIX_SOURCE_MISMATCH')
    nextParticipants = {
      batterId: next.batterId,
      pitcherId: participants.pitcherId,
      battingOrder: next.battingOrder,
    }
    runners = [
      {
        runnerId: participants.batterId,
        responsiblePitcherId: responsiblePitcherId,
        base: '1',
        status: '継続',
        statusSource: 'auto',
      },
    ]
  } else if (value.plateAppearanceEnded !== false || source.nextBatter !== null)
    return failure('PREFIX_SOURCE_MISMATCH')
  if (!runnersMatch(runners, after)) return failure('PREFIX_SOURCE_MISMATCH')
  const ref = request.prefixRef as Json
  const length = unsigned(ref.length)
  const historyVersion = unsigned(ref.historyVersion)
  if (length === null || historyVersion === null)
    return failure('PREFIX_SOURCE_MISMATCH')
  return JSON.stringify({
    ok: true,
    value: {
      t1: {
        countEffect: value.countEffect,
        plateAppearanceEnded: value.plateAppearanceEnded,
        batterDestination: value.batterDestination,
        runnerDefaultAdvance: value.runnerDefaultAdvance,
        outEffect: value.outEffect,
        statFlags: value.statFlags,
        after: after,
      },
      t2: {
        kind: 'evaluated-no-end-condition',
        scope: 'play-prefix-v2',
        evaluation_point: 'post-play',
        basis: basis,
      },
      newHistoryEntry: entry,
      previousPrefixRef: ref,
      nextPrefixRef: Object.assign({}, ref, {
        length: formatDecimalInteger(length + 1n),
        historyVersion: formatDecimalInteger(historyVersion + 1n),
        checkpoint: request.nextCheckpoint,
      }),
      runners: runners,
      participants: nextParticipants,
      playIdentity: request.playIdentity,
      sourcePosition: source.position,
      executionArtifactSha256: source.executionArtifactSha256,
    },
  })
}
