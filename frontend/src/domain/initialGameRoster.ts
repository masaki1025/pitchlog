import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'

type ErrorCode =
  | 'INVALID_JSON'
  | 'INVALID_REQUEST'
  | 'INVALID_DECIMAL_INTEGER'
  | 'INVALID_INITIAL_LINEUP'
  | 'UNSUPPORTED_INITIAL_ROSTER_SCOPE'
type ReadError = { ok: false; code: ErrorCode }
type Role =
  { kind: 'fielding'; position: bigint } | { kind: 'designated-hitter' }
type Entry = {
  playerId: string
  battingOrder: bigint | null
  role: Role
}
type Side = { teamId: string; entries: Array<Entry> }
type SideRead = { ok: true; value: Side } | ReadError
type RoleShape =
  { kind: 'fielding'; position: unknown } | { kind: 'designated-hitter' }
type EntryShape = { playerId: string; battingOrder: unknown; role: RoleShape }
type SideShape = { teamId: string; entries: Array<EntryShape> }
type EntryShapeRead = { ok: true; value: EntryShape } | ReadError
type SideShapeRead = { ok: true; value: SideShape } | ReadError

/** 新操作だけの閉じた失敗。開始や保存結果へ写さない。 */
function failure(code: ErrorCode): string {
  return JSON.stringify({ ok: false, error: { code: code } })
}

/** 全必須キーがある閉objectだけを読む。 */
function object(
  value: unknown,
  keys: Array<string>,
): Record<string, unknown> | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    return null
  if (!Object.keys(value).every((key) => keys.includes(key))) return null
  if (!keys.every((key) => Object.prototype.hasOwnProperty.call(value, key)))
    return null
  return value as Record<string, unknown>
}

/** UUIDのcanonical ASCII構造だけを読む。在籍や実在は証明しない。 */
function uuid(value: unknown): string | null {
  if (typeof value !== 'string') return null
  let index = 0n
  for (const character of value) {
    if (index === 8n || index === 13n || index === 18n || index === 23n) {
      if (character !== '-') return null
    } else if (!'0123456789abcdef'.includes(character)) return null
    index = index + 1n
  }
  if (index !== 36n) return null
  return value
}

/** 既decimal codecだけで1..9のwire値を読む。 */
function slot(value: unknown): bigint | null {
  const result = parseDecimalInteger(value)
  if (result === null || result < 1n || result > 9n) return null
  return result
}

/** 整数に触れず、公式IDとroleの閉じた外形だけを読む。 */
function readEntryShape(value: unknown): EntryShapeRead {
  const source = object(value, [
    'player_id',
    'batting_order',
    'fielding_position',
  ])
  if (source === null) return { ok: false, code: 'INVALID_REQUEST' }
  const playerId = uuid(source.player_id)
  if (playerId === null) return { ok: false, code: 'INVALID_REQUEST' }
  let role: RoleShape
  const position = object(source.fielding_position, ['kind', 'position'])
  if (position !== null && position.kind === 'fielding') {
    role = { kind: 'fielding', position: position.position }
  } else {
    const dh = object(source.fielding_position, ['kind'])
    if (dh === null || dh.kind !== 'designated-hitter')
      return { ok: false, code: 'INVALID_REQUEST' }
    role = { kind: 'designated-hitter' }
  }
  return {
    ok: true,
    value: {
      playerId: playerId,
      battingOrder: source.batting_order,
      role: role,
    },
  }
}

/** 全sideの外形確認を十進値の検査より先に完了させる。 */
function readSideShape(value: unknown): SideShapeRead {
  const source = object(value, ['team_id', 'entries'])
  if (source === null || !Array.isArray(source.entries))
    return { ok: false, code: 'INVALID_REQUEST' }
  const teamId = uuid(source.team_id)
  if (teamId === null) return { ok: false, code: 'INVALID_REQUEST' }
  let count = 0n
  let entries: Array<EntryShape> = []
  for (const item of source.entries) {
    count = count + 1n
    if (count > 10n) return { ok: false, code: 'INVALID_REQUEST' }
    const entry = readEntryShape(item)
    if (!entry.ok) return entry
    entries = entries.concat(entry.value)
  }
  if (count < 9n) return { ok: false, code: 'INVALID_REQUEST' }
  return { ok: true, value: { teamId: teamId, entries: entries } }
}

/** 外形検査済みの私有値だけを既decimal codecへ渡す。 */
function readSideIntegers(source: SideShape): SideRead {
  let entries: Array<Entry> = []
  for (const entry of source.entries) {
    let role: Role
    if (entry.role.kind === 'fielding') {
      const position = slot(entry.role.position)
      if (position === null)
        return { ok: false, code: 'INVALID_DECIMAL_INTEGER' }
      role = { kind: 'fielding', position: position }
    } else role = { kind: 'designated-hitter' }
    let battingOrder: bigint | null = null
    if (entry.battingOrder !== null) {
      battingOrder = slot(entry.battingOrder)
      if (battingOrder === null)
        return { ok: false, code: 'INVALID_DECIMAL_INTEGER' }
    }
    entries = entries.concat({
      playerId: entry.playerId,
      battingOrder: battingOrder,
      role: role,
    })
  }
  return { ok: true, value: { teamId: source.teamId, entries: entries } }
}

/** 明示した初期配置の集合・相関だけを検証する。 */
function validLayout(side: Side, dh: boolean): boolean {
  let count = 0n
  let hitters = 0n
  let players: Array<string> = []
  let batting: Array<bigint> = []
  let fielding: Array<bigint> = []
  for (const entry of side.entries) {
    count = count + 1n
    if (players.includes(entry.playerId)) return false
    players = players.concat(entry.playerId)
    if (entry.battingOrder !== null) {
      if (batting.includes(entry.battingOrder)) return false
      batting = batting.concat(entry.battingOrder)
    }
    if (entry.role.kind === 'designated-hitter') {
      if (!dh || entry.battingOrder === null) return false
      hitters = hitters + 1n
    } else {
      const position = entry.role.position
      if (fielding.includes(position)) return false
      fielding = fielding.concat(position)
      if (dh && position === 1n) {
        if (entry.battingOrder !== null) return false
      } else if (entry.battingOrder === null) return false
    }
  }
  if (dh) {
    if (count !== 10n || hitters !== 1n) return false
  } else if (count !== 9n || hitters !== 0n) return false
  const complete = [1n, 2n, 3n, 4n, 5n, 6n, 7n, 8n, 9n]
  return (
    complete.every((value) => batting.includes(value)) &&
    complete.every((value) => fielding.includes(value))
  )
}

/** input順を保持したpoint無しの初期entryへ写す。 */
function projectEntry(entry: Entry): Record<string, unknown> {
  let batting: Record<string, unknown> = { kind: 'none' }
  if (entry.battingOrder !== null)
    batting = { kind: 'slot', slot: formatDecimalInteger(entry.battingOrder) }
  let role: Record<string, unknown>
  if (entry.role.kind === 'fielding') {
    role = {
      kind: 'fielding',
      position: formatDecimalInteger(entry.role.position),
    }
  } else role = { kind: 'designated-hitter' }
  return {
    player: { kind: 'official', player_id: entry.playerId },
    batting_slot: batting,
    roles: [role],
    entry_origin: { kind: 'initial' },
  }
}

/** ownerfulなpointや背番号を補完せずteamの構造だけを返す。 */
function projectSide(side: Side, name: string): Record<string, unknown> {
  return {
    team_id: side.teamId,
    side: name,
    participants: side.entries.map(projectEntry),
  }
}

/** 開始名簿の純検証。認可・在籍・初期state・保存成功を返さない。 */
export function validateInitialGameRoster(requestJson: string): string {
  if (typeof requestJson !== 'string') return failure('INVALID_REQUEST')
  let parsed: unknown
  try {
    parsed = JSON.parse(requestJson) as unknown
  } catch {
    return failure('INVALID_JSON')
  }
  const source = object(parsed, ['dh', 'away', 'home'])
  if (source === null || typeof source.dh !== 'boolean')
    return failure('INVALID_REQUEST')
  const awayShape = readSideShape(source.away)
  if (!awayShape.ok) return failure(awayShape.code)
  const homeShape = readSideShape(source.home)
  if (!homeShape.ok) return failure(homeShape.code)
  const away = readSideIntegers(awayShape.value)
  if (!away.ok) return failure(away.code)
  const home = readSideIntegers(homeShape.value)
  if (!home.ok) return failure(home.code)
  if (away.value.teamId === home.value.teamId)
    return failure('UNSUPPORTED_INITIAL_ROSTER_SCOPE')
  if (
    !validLayout(away.value, source.dh) ||
    !validLayout(home.value, source.dh)
  )
    return failure('INVALID_INITIAL_LINEUP')
  return JSON.stringify({
    ok: true,
    value: {
      teams: [projectSide(away.value, 'away'), projectSide(home.value, 'home')],
    },
  })
}
