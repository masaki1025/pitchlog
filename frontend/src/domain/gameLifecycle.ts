import { canonicalContinuationUuid } from './ordinaryPitchContinuation'
import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'

type Json = Record<string, unknown>

function object(v: unknown, keys: Array<string>): Json | null {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) return null
  const r = v as Json
  if (
    !Object.keys(r).every((k) => keys.includes(k)) ||
    !keys.every((k) => Object.prototype.hasOwnProperty.call(r, k))
  )
    return null
  return r
}
function read(v: Json, key: string): unknown {
  for (const p of Object.entries(v))
    if (p.slice().shift() === key) return p.slice().pop()
  return null
}
function integer(v: unknown): boolean {
  const n = parseDecimalInteger(v)
  return n !== null && n >= 0n
}
function current(v: unknown): Json | null {
  const c = object(v, ['stateFields', 'scoreboard', 'battingOrderBySide'])
  if (c === null) return null
  const s = object(c.stateFields, [
    'state.inning',
    'state.half',
    'state.outs',
    'state.count.strikes',
    'state.count.balls',
    'state.runners',
    'state.battingOrder',
    'state.tiebreakActive',
    'state.gameEnded',
    'state.score',
  ])
  const b = object(c.scoreboard, [
    'inningScores',
    'hits',
    'errors',
    'strikeouts',
    'walks',
  ])
  const cursors = object(c.battingOrderBySide, ['home', 'away'])
  if (s === null || b === null || cursors === null) return null
  const score = object(read(s, 'state.score'), ['home', 'away'])
  const inning = object(b.inningScores, ['home', 'away'])
  if (score === null || inning === null) return null
  if (
    ![
      read(s, 'state.inning'),
      read(s, 'state.outs'),
      read(s, 'state.count.strikes'),
      read(s, 'state.count.balls'),
      read(s, 'state.battingOrder'),
      b.hits,
      b.errors,
      b.strikeouts,
      b.walks,
      score.home,
      score.away,
      inning.home,
      inning.away,
      cursors.home,
      cursors.away,
    ].every(integer)
  )
    return null
  if (
    parseDecimalInteger(read(s, 'state.inning')) === 0n ||
    parseDecimalInteger(read(s, 'state.battingOrder')) === 0n ||
    parseDecimalInteger(cursors.home) === 0n ||
    parseDecimalInteger(cursors.away) === 0n
  )
    return null
  if (read(s, 'state.half') !== 'top' && read(s, 'state.half') !== 'bottom')
    return null
  if (
    ![
      'empty',
      'first',
      'second',
      'third',
      'first-second',
      'first-third',
      'second-third',
      'loaded',
    ].includes(read(s, 'state.runners') as string)
  )
    return null
  if (
    typeof read(s, 'state.tiebreakActive') !== 'boolean' ||
    typeof read(s, 'state.gameEnded') !== 'boolean'
  )
    return null
  return c
}
function active(v: unknown): Json | null {
  const a = object(v, ['version', 'eventId', 'receiptId'])
  if (
    a === null ||
    !integer(a.version) ||
    parseDecimalInteger(a.version) === 0n ||
    !canonicalContinuationUuid(a.eventId) ||
    !canonicalContinuationUuid(a.receiptId)
  )
    return null
  return a
}
function sameActive(a: Json, b: Json): boolean {
  return (
    a.version === b.version &&
    a.eventId === b.eventId &&
    a.receiptId === b.receiptId
  )
}
function fail(code: string): string {
  return JSON.stringify({ ok: false, error: { code } })
}

/** FR-007の再開は唯一の核で終了条件ロックだけを解除する。認可/保存資格を作らない。 */
export function applyGameLifecycle(raw: string): string {
  if (typeof raw !== 'string') return fail('INVALID_REQUEST')
  let parsed: unknown
  try {
    parsed = JSON.parse(raw) as unknown
  } catch {
    return fail('INVALID_JSON')
  }
  const r = object(parsed, [
    'formatVersion',
    'action',
    'current',
    'lifecycle',
    'target',
    'event',
  ])
  if (
    r === null ||
    r.formatVersion !== 'native-game-lifecycle-v1' ||
    (r.action !== 'end' && r.action !== 'reopen')
  )
    return fail('INVALID_REQUEST')
  const c = current(r.current)
  const life = object(r.lifecycle, ['status', 'lastVersion', 'active'])
  const event = object(r.event, ['eventId', 'receiptId'])
  if (
    c === null ||
    life === null ||
    !integer(life.lastVersion) ||
    event === null ||
    !canonicalContinuationUuid(event.eventId) ||
    !canonicalContinuationUuid(event.receiptId)
  )
    return fail('INVALID_REQUEST')
  const before = read(c.stateFields as Json, 'state.gameEnded')
  if (typeof before !== 'boolean') return fail('INVALID_REQUEST')
  const version = parseDecimalInteger(life.lastVersion)
  if (version === null) return fail('INVALID_REQUEST')
  let next: Json
  if (r.action === 'end') {
    if (
      life.status !== 'in_progress' ||
      life.active !== null ||
      r.target !== null
    )
      return fail('LIFECYCLE_STATE_MISMATCH')
    const nextVersion = formatDecimalInteger(version + 1n)
    next = {
      status: 'finished',
      lastVersion: nextVersion,
      active: {
        version: nextVersion,
        eventId: event.eventId,
        receiptId: event.receiptId,
      },
    }
  } else {
    const a = active(life.active)
    const target = active(r.target)
    if (
      life.status !== 'finished' ||
      a === null ||
      target === null ||
      !sameActive(a, target) ||
      a.version !== life.lastVersion ||
      a.eventId === event.eventId ||
      a.receiptId === event.receiptId
    )
      return fail('LIFECYCLE_STATE_MISMATCH')
    // score/count/走者/打順/T2/履歴は変更しない。
    c.stateFields = Object.assign({}, c.stateFields, {
      'state.gameEnded': false,
    })
    next = {
      status: 'in_progress',
      lastVersion: life.lastVersion,
      active: null,
    }
  }
  let effect = 'unchanged'
  if (before !== read(c.stateFields as Json, 'state.gameEnded')) effect = 'set'
  return JSON.stringify({
    ok: true,
    value: {
      current: c,
      lifecycle: next,
      stateEffect: {
        gameEnded: {
          kind: effect,
          before,
          after: read(c.stateFields as Json, 'state.gameEnded'),
        },
      },
    },
  })
}
