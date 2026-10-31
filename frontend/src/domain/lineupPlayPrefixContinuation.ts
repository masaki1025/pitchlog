import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'
import { readContinuationRules } from './firstPitchContinuation'
import { evaluateEndCondition, validEndRules } from './endConditionCore'
import {
  canonicalContinuationUuid,
  canonicalContinuationGeneration,
  sameContinuationValue,
} from './ordinaryPitchContinuation'

type Json = Record<string, unknown>
type Prepared =
  { ok: true; request: Json; t1: Json } | { ok: false; response: string }
/** 閉shapeを再検証し、余剰/欠落を補完しない。 */
function object(value: unknown, keys: Array<string>): Json | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    return null
  const v = value as Json
  if (
    !Object.keys(v).every((k) => keys.includes(k)) ||
    !keys.every((k) => Object.prototype.hasOwnProperty.call(v, k))
  )
    return null
  return v
}
function read(v: Json, key: string): unknown {
  for (const p of Object.entries(v))
    if (p.slice().shift() === key) return p.slice().pop()
  return null
}
function unsigned(v: unknown): bigint | null {
  if (typeof v !== 'string' || v.startsWith('-')) return null
  const n = parseDecimalInteger(v)
  if (n === null || n < 0n) return null
  return n
}
function digest(v: unknown): boolean {
  if (typeof v !== 'string') return false
  let n = 0n
  for (const c of v) {
    if (!((c >= 'a' && c <= 'f') || (c >= '0' && c <= '9'))) return false
    n = n + 1n
  }
  return n === 64n
}
function checkpoint(v: unknown): Json | null {
  const c = object(v, ['id', 'revision', 'digest'])
  if (c === null || !canonicalContinuationUuid(c.id) || !digest(c.digest))
    return null
  const n = unsigned(c.revision)
  if (n === null || n < 1n) return null
  return c
}
function identity(v: unknown): Json | null {
  const c = object(v, ['eventId', 'd5', 'playId'])
  if (c === null || !Object.values(c).every(canonicalContinuationUuid))
    return null
  return c
}
function prefix(v: unknown): Json | null {
  const r = object(v, [
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
    r === null ||
    r.version !== '3' ||
    r.scope !== 'play-prefix-v3' ||
    !canonicalContinuationUuid(r.tenantId) ||
    !canonicalContinuationUuid(r.gameId) ||
    !canonicalContinuationGeneration(r.generation) ||
    unsigned(r.length) === null ||
    unsigned(r.historyVersion) === null ||
    checkpoint(r.checkpoint) === null
  )
    return null
  const o = object(r.origin, ['kind', 'eventId'])
  if (
    o === null ||
    o.kind !== 'started-game' ||
    !canonicalContinuationUuid(o.eventId)
  )
    return null
  return r
}
function failure(code: string): string {
  return JSON.stringify({ ok: false, error: { code: code } })
}
function reject(code: string): Prepared {
  return { ok: false, response: failure(code) }
}
/** 全配置のIDを実sourceと照合するための、閉じた名簿の外形。 */
function lineup(value: unknown, dh: boolean): Json | null {
  const l = object(value, ['away', 'home'])
  if (l === null) return null
  let teams: Array<unknown> = []
  let all: Array<unknown> = []
  for (const side of Object.values(l)) {
    const t = object(side, ['teamId', 'battingOrder', 'pitcherId', 'catcherId'])
    if (
      t === null ||
      !canonicalContinuationUuid(t.teamId) ||
      !canonicalContinuationUuid(t.pitcherId) ||
      !canonicalContinuationUuid(t.catcherId) ||
      t.pitcherId === t.catcherId ||
      teams.includes(t.teamId)
    )
      return null
    teams = teams.concat([t.teamId])
    const order = object(t.battingOrder, [
      '1',
      '2',
      '3',
      '4',
      '5',
      '6',
      '7',
      '8',
      '9',
    ])
    if (order === null) return null
    const players = Object.values(order)
    let seen: Array<unknown> = []
    for (const player of players) {
      if (
        !canonicalContinuationUuid(player) ||
        seen.includes(player) ||
        all.includes(player)
      )
        return null
      seen = seen.concat([player])
    }
    if (!players.includes(t.catcherId) || players.includes(t.pitcherId) === dh)
      return null
    if (!players.includes(t.pitcherId)) {
      if (all.includes(t.pitcherId)) return null
      seen = seen.concat([t.pitcherId])
    }
    all = all.concat(seen)
  }
  return l
}
/** next側の選択は同artifactだけが所有する。BE/UIには半回/打順算式を置かない。 */
function participant(snapshot: Json, l: Json): Json | null {
  const fields = snapshot.stateFields as Json
  let batting = l.away as Json
  let fielding = l.home as Json
  if (read(fields, 'state.half') === 'bottom') {
    batting = l.home as Json
    fielding = l.away as Json
  } else if (read(fields, 'state.half') !== 'top') return null
  const slot = read(fields, 'state.battingOrder')
  if (typeof slot !== 'string') return null
  const id = read(batting.battingOrder as Json, slot)
  if (!canonicalContinuationUuid(id)) return null
  return {
    batterId: id,
    pitcherId: fielding.pitcherId,
    catcherId: fielding.catcherId,
    battingOrder: slot,
  }
}
function people(v: unknown): Json | null {
  const p = object(v, ['batterId', 'pitcherId', 'catcherId', 'battingOrder'])
  if (
    p === null ||
    !canonicalContinuationUuid(p.batterId) ||
    !canonicalContinuationUuid(p.pitcherId) ||
    !canonicalContinuationUuid(p.catcherId)
  )
    return null
  return p
}
function responsibility(v: unknown): Json | null {
  const r = object(v, [
    'kind',
    'paStartSource',
    'previousPitcherId',
    'strikesAtChange',
    'ballsAtChange',
  ])
  if (
    r === null ||
    r.kind !== 'no-change' ||
    r.previousPitcherId !== null ||
    r.strikesAtChange !== null ||
    r.ballsAtChange !== null
  )
    return null
  const p = object(r.paStartSource, ['kind', 'id'])
  if (
    p === null ||
    !['started-game', 'confirmed-play'].includes(p.kind as string) ||
    !canonicalContinuationUuid(p.id)
  )
    return null
  return r
}
function runners(value: unknown, snapshot: Json): boolean {
  if (!Array.isArray(value)) return false
  const fields = snapshot.stateFields as Json
  const vocabulary = read(fields, 'state.runners')
  let bases: Array<string> = []
  if (vocabulary === 'first') bases = ['1']
  else if (vocabulary === 'second') bases = ['2']
  else if (vocabulary === 'third') bases = ['3']
  else if (vocabulary === 'first-second') bases = ['1', '2']
  else if (vocabulary === 'first-third') bases = ['1', '3']
  else if (vocabulary === 'second-third') bases = ['2', '3']
  else if (vocabulary === 'first-second-third') bases = ['1', '2', '3']
  else if (vocabulary !== 'empty') return false
  let ids: Array<unknown> = []
  for (const item of value) {
    const r = object(item, [
      'runnerId',
      'responsiblePitcherId',
      'base',
      'status',
      'statusSource',
    ])
    if (
      r === null ||
      !canonicalContinuationUuid(r.runnerId) ||
      !canonicalContinuationUuid(r.responsiblePitcherId) ||
      !bases.includes(r.base as string) ||
      ids.includes(r.runnerId) ||
      r.status !== '継続' ||
      r.statusSource !== 'auto'
    )
      return false
    ids = ids.concat([r.runnerId])
    bases = bases.filter((b) => b !== r.base)
  }
  return !bases.some(() => true)
}
/** 未信頼提案の相関だけを検査する。DB真正資格はsource verifierが別に確認する。 */
export function prepareLineupContinuation(raw: string): Prepared {
  const r = object(JSON.parse(raw), [
    'version',
    'prefixRef',
    'rules',
    't1',
    'source',
    'playIdentity',
    'nextCheckpoint',
  ])
  if (r === null || r.version !== '3') return reject('INVALID_REQUEST')
  const ref = prefix(r.prefixRef)
  const next = checkpoint(r.nextCheckpoint)
  const input = object(r.t1, [
    'eventKind',
    'resultId',
    'pitchEventKind',
    'before',
  ])
  const s = object(r.source, [
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
    'rosterDigest',
    'lineup',
    'runners',
    'participants',
    'responsibility',
    'provenance',
  ])
  if (
    ref === null ||
    next === null ||
    input === null ||
    s === null ||
    identity(r.playIdentity) === null
  )
    return reject('INVALID_REQUEST')
  const rules = readContinuationRules(r.rules)
  if (!rules.ok) return reject(rules.code)
  if (!validEndRules(rules.value)) return reject('T2_NOT_EVALUATED')
  const l = lineup(s.lineup, rules.value.dh)
  const before = object(s.after, [
    'stateFields',
    'scoreboard',
    'battingOrderBySide',
  ])
  const pos = object(s.position, ['d1', 'd2', 'appliedWatermark'])
  const resp = responsibility(s.responsibility)
  if (
    l === null ||
    before === null ||
    people(s.participants) === null ||
    pos === null ||
    Object.values(pos).some((v) => unsigned(v) === null) ||
    resp === null ||
    ![
      s.priorArtifactSha256,
      s.executionArtifactSha256,
      s.rulesDigest,
      s.layoutDigest,
      s.rosterDigest,
    ].every(digest)
  )
    return reject('INVALID_REQUEST')
  const fields = before.stateFields as Json
  const cursors = object(before.battingOrderBySide, ['away', 'home'])
  if (
    cursors === null ||
    Object.values(cursors).some((v) => {
      const n = unsigned(v)
      return n === null || n < 1n || n > 9n
    })
  )
    return reject('INVALID_REQUEST')
  let active = cursors.away
  if (read(fields, 'state.half') === 'bottom') active = cursors.home
  const cp = ref.checkpoint as Json
  const revision = unsigned(cp.revision)
  if (
    !sameContinuationValue(s.prefixRef, ref) ||
    !sameContinuationValue(s.rules, r.rules) ||
    !sameContinuationValue(before, input.before) ||
    !sameContinuationValue(s.participants, participant(before, l)) ||
    read(fields, 'state.battingOrder') !== active ||
    !sameContinuationValue(
      read(fields, 'state.score'),
      (before.scoreboard as Json).inningScores,
    ) ||
    s.historyDepth !== ref.length ||
    s.playCount !== ref.length ||
    pos.d1 !== pos.d2 ||
    pos.d1 !== pos.appliedWatermark ||
    s.rosterDigest !== s.layoutDigest ||
    revision === null ||
    unsigned(next.revision) !== revision + 1n ||
    next.id === cp.id ||
    !runners(s.runners, before)
  )
    return reject('PREFIX_SOURCE_MISMATCH')
  const provenance = s.provenance as Json
  if (s.kind === 'started-initial-v3') {
    const p = object(provenance, ['kind', 'eventId'])
    const origin = ref.origin as Json
    const pa = resp.paStartSource as Json
    if (
      p === null ||
      p.kind !== 'started-game' ||
      p.eventId !== origin.eventId ||
      pa.kind !== 'started-game' ||
      pa.id !== p.eventId ||
      ref.length !== '0' ||
      ref.historyVersion !== '0' ||
      s.t2 !== null ||
      s.lastSource !== null ||
      pos.d1 !== '0' ||
      cursors.away !== '1' ||
      cursors.home !== '1' ||
      read(fields, 'state.inning') !== '1' ||
      read(fields, 'state.half') !== 'top' ||
      read(fields, 'state.outs') !== '0' ||
      read(fields, 'state.count.strikes') !== '0' ||
      read(fields, 'state.count.balls') !== '0' ||
      read(fields, 'state.runners') !== 'empty' ||
      read(fields, 'state.tiebreakActive') !== false ||
      read(fields, 'state.gameEnded') !== false ||
      !sameContinuationValue(read(fields, 'state.score'), {
        home: '0',
        away: '0',
      }) ||
      !sameContinuationValue(before.scoreboard, {
        inningScores: { home: '0', away: '0' },
        hits: '0',
        errors: '0',
        strikeouts: '0',
        walks: '0',
      })
    )
      return reject('PREFIX_SOURCE_MISMATCH')
  } else if (s.kind === 'evaluated-prefix-v3') {
    const p = object(provenance, [
      'kind',
      'checkpoint',
      'sourceIdentity',
      'historyDepth',
    ])
    const t2 = object(s.t2, [
      'kind',
      'scope',
      'evaluation_point',
      'facts',
      'decision',
      'tiebreakStartRequired',
    ])
    if (
      p === null ||
      p.kind !== 'confirmed-prefix' ||
      !sameContinuationValue(p.checkpoint, cp) ||
      identity(s.lastSource) === null ||
      !sameContinuationValue(p.sourceIdentity, s.lastSource) ||
      p.historyDepth !== s.historyDepth ||
      t2 === null ||
      t2.kind !== 'evaluated-end-condition' ||
      t2.scope !== 'play-prefix-v3' ||
      t2.evaluation_point !== 'post-play' ||
      t2.tiebreakStartRequired !== false
    )
      return reject('PREFIX_SOURCE_MISMATCH')
    const d = object(t2.decision, [
      'outcome',
      'endConditionDetected',
      'lockFurtherPlayInput',
      'promptEndDeclaration',
      'automaticallyEndsGame',
      'xMark',
    ])
    const f = object(t2.facts, [
      'beforeInning',
      'beforeHalf',
      'beforeOuts',
      'afterInning',
      'afterHalf',
      'afterOuts',
      'halfCompleted',
      'outsUnchanged',
      'scoreUnchanged',
      'priorOpen',
    ])
    if (
      d === null ||
      d.endConditionDetected !== false ||
      d.lockFurtherPlayInput !== false ||
      d.promptEndDeclaration !== false ||
      d.automaticallyEndsGame !== false ||
      d.xMark !== 'recorded-score' ||
      !['no-end', 'extra-continue', 'tiebreak-continue'].includes(
        d.outcome as string,
      ) ||
      f === null ||
      f.afterInning !== read(fields, 'state.inning') ||
      f.afterHalf !== read(fields, 'state.half') ||
      f.afterOuts !== read(fields, 'state.outs') ||
      f.priorOpen !== true ||
      typeof f.halfCompleted !== 'boolean' ||
      typeof f.outsUnchanged !== 'boolean' ||
      typeof f.scoreUnchanged !== 'boolean' ||
      unsigned(f.beforeInning) === null ||
      unsigned(f.beforeInning) === 0n ||
      !['top', 'bottom'].includes(f.beforeHalf as string) ||
      !['0', '1', '2'].includes(f.beforeOuts as string)
    )
      return reject('PREFIX_SOURCE_MISMATCH')
  } else return reject('PREFIX_SOURCE_MISMATCH')
  if (s.kind === 'evaluated-prefix-v3') {
    const prior = s.t2 as Json
    const facts = prior.facts as Json
    const score = read(fields, 'state.score') as Json
    const observedInning = unsigned(read(fields, 'state.inning'))
    const home = unsigned(score.home)
    const away = unsigned(score.away)
    const observedHalf = read(fields, 'state.half')
    if (
      observedInning === null ||
      home === null ||
      away === null ||
      (observedHalf !== 'top' && observedHalf !== 'bottom')
    )
      return reject('PREFIX_SOURCE_MISMATCH')
    let completed: 'top' | 'bottom' | null = null
    let completedInning: bigint | null = null
    if (facts.halfCompleted === true) {
      if (facts.beforeHalf !== 'top' && facts.beforeHalf !== 'bottom')
        return reject('PREFIX_SOURCE_MISMATCH')
      completed = facts.beforeHalf
      completedInning = unsigned(facts.beforeInning)
    }
    const checked = evaluateEndCondition(
      {
        inning: observedInning,
        half: observedHalf,
        home: home,
        away: away,
        tiebreakActive: read(fields, 'state.tiebreakActive') === true,
        gameEnded: read(fields, 'state.gameEnded') === true,
      },
      rules.value,
      { completedHalf: completed, completedInning: completedInning },
    )
    if (checked === null || !sameContinuationValue(prior.decision, checked))
      return reject('PREFIX_SOURCE_MISMATCH')
  }
  // TB開始を自動実行せず、FR009が未供給の状態から投球しない。
  let expectedTB = false
  const inning = unsigned(read(fields, 'state.inning'))
  if (inning === null) return reject('INVALID_DECIMAL_INTEGER')
  if (
    rules.value.tiebreak !== null &&
    inning >= rules.value.tiebreak.startInning
  )
    expectedTB = true
  if (read(fields, 'state.tiebreakActive') !== expectedTB)
    return reject('T2_NOT_EVALUATED')
  return {
    ok: true,
    request: r,
    t1: {
      eventKind: input.eventKind,
      resultId: input.resultId,
      pitchEventKind: input.pitchEventKind,
      before: before,
      history: { stack: [] },
    },
  }
}
/** 実一回T1をT2/runner/次sourceへ射影する。入力提案からT1結果をlookupしない。 */
export function finishLineupContinuation(r: Json, raw: string): string {
  const response = JSON.parse(raw) as Json
  if (response.ok !== true) return raw
  const value = response.value as Json
  const input = r.t1 as Json
  const source = r.source as Json
  const before = input.before as Json
  const after = value.after as Json
  const bf = before.stateFields as Json
  const af = after.stateFields as Json
  const rule = readContinuationRules(r.rules)
  if (!rule.ok) return failure('T2_NOT_EVALUATED')
  const inning = unsigned(read(af, 'state.inning'))
  const beforeInning = unsigned(read(bf, 'state.inning'))
  const score = read(af, 'state.score') as Json
  const home = unsigned(score.home)
  const away = unsigned(score.away)
  const half = read(af, 'state.half')
  const beforeHalf = read(bf, 'state.half')
  if (
    inning === null ||
    beforeInning === null ||
    home === null ||
    away === null ||
    (half !== 'top' && half !== 'bottom') ||
    (beforeHalf !== 'top' && beforeHalf !== 'bottom')
  )
    return failure('T2_NOT_EVALUATED')
  let completedHalf: 'top' | 'bottom' | null = null
  let completedInning: bigint | null = null
  if (half !== beforeHalf) {
    completedHalf = beforeHalf
    completedInning = beforeInning
  }
  const result = evaluateEndCondition(
    {
      inning: inning,
      half: half,
      home: home,
      away: away,
      tiebreakActive: read(af, 'state.tiebreakActive') === true,
      gameEnded: read(af, 'state.gameEnded') === true,
    },
    rule.value,
    { completedHalf: completedHalf, completedInning: completedInning },
  )
  if (result === null) return failure('T2_NOT_EVALUATED')
  let tbRequired = false
  if (
    result.outcome === 'tiebreak-continue' &&
    read(af, 'state.tiebreakActive') !== true
  )
    tbRequired = true
  const t2 = {
    kind: 'evaluated-end-condition',
    scope: 'play-prefix-v3',
    evaluation_point: 'post-play',
    facts: {
      beforeInning: read(bf, 'state.inning'),
      beforeHalf: beforeHalf,
      beforeOuts: read(bf, 'state.outs'),
      afterInning: read(af, 'state.inning'),
      afterHalf: half,
      afterOuts: read(af, 'state.outs'),
      halfCompleted: completedHalf !== null,
      outsUnchanged: read(bf, 'state.outs') === read(af, 'state.outs'),
      scoreUnchanged: sameContinuationValue(
        read(bf, 'state.score'),
        read(af, 'state.score'),
      ),
      priorOpen: true,
    },
    decision: result,
    tiebreakStartRequired: tbRequired,
  }
  const entries = (value.historyContext as Array<unknown>).slice()
  const entry = entries.shift()
  if (typeof entry === 'undefined' || entries.some(() => true))
    return failure('T2_NOT_EVALUATED')
  const l = source.lineup as Json
  const nextPeople = participant(after, l)
  if (nextPeople === null) return failure('PREFIX_SOURCE_MISMATCH')
  let nextRunners = source.runners
  if (completedHalf !== null) nextRunners = []
  else if (
    value.plateAppearanceEnded === true &&
    (value.batterDestination as Json).kind === 'reach'
  )
    nextRunners = [
      {
        runnerId: (source.participants as Json).batterId,
        responsiblePitcherId: (source.participants as Json).pitcherId,
        base: '1',
        status: '継続',
        statusSource: 'auto',
      },
    ]
  if (!runners(nextRunners, after)) return failure('PREFIX_SOURCE_MISMATCH')
  let nextResponsibility = source.responsibility
  if (value.plateAppearanceEnded === true)
    nextResponsibility = {
      kind: 'no-change',
      paStartSource: {
        kind: 'confirmed-play',
        id: (r.playIdentity as Json).eventId,
      },
      previousPitcherId: null,
      strikesAtChange: null,
      ballsAtChange: null,
    }
  const ref = r.prefixRef as Json
  const length = unsigned(ref.length)
  const history = unsigned(ref.historyVersion)
  if (length === null || history === null)
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
      t2: t2,
      newHistoryEntry: entry,
      previousPrefixRef: ref,
      nextPrefixRef: Object.assign({}, ref, {
        length: formatDecimalInteger(length + 1n),
        historyVersion: formatDecimalInteger(history + 1n),
        checkpoint: r.nextCheckpoint,
      }),
      runners: nextRunners,
      beforeParticipants: source.participants,
      participants: nextPeople,
      lineup: l,
      rosterDigest: source.rosterDigest,
      responsibility: source.responsibility,
      nextResponsibility: nextResponsibility,
      playIdentity: r.playIdentity,
      sourcePosition: source.position,
      executionArtifactSha256: source.executionArtifactSha256,
    },
  })
}
