/** 交代だけの単一純計算。投球・打席・得点は既核へ渡す。 */
export type Side = 'away' | 'home'
export type Slot = '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9'
export const SLOTS: Array<Slot> = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
export type Runner = {
  runnerId: string
  responsiblePitcherId: string
  base: '1' | '2' | '3'
  status: '継続'
  statusSource: 'auto'
}
export type SubstitutionTeam = {
  teamId: string
  battingOrder: Record<Slot, string>
  fielding: Record<Slot, string | null>
  dhSlot: Slot | null
}
export type PitcherResponsibility =
  | { kind: 'unchanged' }
  | {
      kind: 'changed-mid-plate-appearance'
      previousPitcherId: string
      reliefPitcherId: string
      strikesAtChange: '0' | '1' | '2'
      ballsAtChange: '0' | '1' | '2' | '3'
    }
export type SubstitutionState = {
  attackingSide: Side
  away: SubstitutionTeam
  home: SubstitutionTeam
  runners: Array<Runner>
  exitedPlayerIds: Array<string>
  responsibility: PitcherResponsibility
}
export type SubstitutionOperation =
  | {
      kind: 'pitcher'
      side: Side
      outgoingId: string
      incomingId: string
      count: { strikes: '0' | '1' | '2'; balls: '0' | '1' | '2' | '3' }
      dh: 'retain' | 'pitcher-takes-dh-slot'
    }
  | {
      kind: 'pinch-hitter'
      side: Side
      outgoingId: string
      incomingId: string
      battingSlot: Slot
    }
  | {
      kind: 'pinch-runner'
      side: Side
      outgoingId: string
      incomingId: string
      base: '1' | '2' | '3'
    }
  | {
      kind: 'defense'
      side: Side
      changes: Array<{
        position: Slot
        outgoingId: string | null
        incomingId: string | null
      }>
    }
export type SubstitutionError =
  | 'invalid-source'
  | 'invalid-operation'
  | 'unavailable-player'
  | 'reentry'
  | 'current-player-mismatch'
  | 'ambiguous-responsibility'
  | 'unsupported-dh-route'
export type SubstitutionWarning =
  'fielding-position-missing' | 'fielding-position-duplicate'
export type ContinuationTeam = {
  teamId: string
  battingOrder: Record<Slot, string>
  pitcherId: string
  catcherId: string
}
export type ContinuationLineup = {
  away: ContinuationTeam
  home: ContinuationTeam
}
export type SubstitutionResult =
  | { ok: false; error: SubstitutionError }
  | {
      ok: true
      state: SubstitutionState
      warnings: Array<SubstitutionWarning>
      continuationLineup: ContinuationLineup | null
    }
type InitialParticipant = {
  player: { player_id: string }
  batting_slot: { kind: string; slot: Slot }
  roles: Array<{ kind: string; position: Slot }>
}
type InitialTeam = { team_id: string; participants: Array<InitialParticipant> }
type InitialRoster = { teams: Array<InitialTeam> }
function object(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}
function exact(v: unknown, keys: Array<string>): v is Record<string, unknown> {
  if (!object(v)) return false
  for (const key of keys) if (!Object.hasOwn(v, key)) return false
  for (const key of Object.keys(v)) if (!keys.includes(key)) return false
  return true
}
function uuid(v: unknown): v is string {
  if (typeof v !== 'string') return false
  let i = 0n
  for (const c of v) {
    if (i === 8n || i === 13n || i === 18n || i === 23n) {
      if (c !== '-') return false
    } else if (!'0123456789abcdef'.includes(c)) return false
    i = i + 1n
  }
  return i === 36n
}
export function isSubstitutionUuid(v: unknown): v is string {
  return uuid(v)
}
function slot(v: unknown): v is Slot {
  return typeof v === 'string' && SLOTS.includes(v as Slot)
}
function readKey(v: Record<string, unknown>, key: string): unknown {
  for (const pair of Object.entries(v)) {
    const name = pair.shift()
    const value = pair.pop()
    if (name === key) return value
  }
  return null
}
function writeKey(v: object, key: string, value: unknown): void {
  Object.assign(v, Object.fromEntries([[key, value]]))
}
function slotObject(v: unknown, nullable: boolean): boolean {
  if (!exact(v, SLOTS)) return false
  for (const position of SLOTS) {
    const player = readKey(v, position)
    if (nullable) {
      if (player !== null && !uuid(player)) return false
    } else if (!uuid(player)) return false
  }
  return true
}
function team(v: unknown): v is SubstitutionTeam {
  if (!exact(v, ['teamId', 'battingOrder', 'fielding', 'dhSlot'])) return false
  return (
    uuid(v.teamId) &&
    slotObject(v.battingOrder, false) &&
    slotObject(v.fielding, true) &&
    (v.dhSlot === null || slot(v.dhSlot))
  )
}
function runner(v: unknown): v is Runner {
  if (
    !exact(v, [
      'runnerId',
      'responsiblePitcherId',
      'base',
      'status',
      'statusSource',
    ])
  )
    return false
  return (
    uuid(v.runnerId) &&
    uuid(v.responsiblePitcherId) &&
    (v.base === '1' || v.base === '2' || v.base === '3') &&
    v.status === '継続' &&
    v.statusSource === 'auto'
  )
}
function responsibility(v: unknown): v is PitcherResponsibility {
  if (!object(v)) return false
  if (v.kind === 'unchanged') return exact(v, ['kind'])
  if (
    !exact(v, [
      'kind',
      'previousPitcherId',
      'reliefPitcherId',
      'strikesAtChange',
      'ballsAtChange',
    ])
  )
    return false
  return (
    v.kind === 'changed-mid-plate-appearance' &&
    uuid(v.previousPitcherId) &&
    uuid(v.reliefPitcherId) &&
    v.previousPitcherId !== v.reliefPitcherId &&
    (v.strikesAtChange === '0' ||
      v.strikesAtChange === '1' ||
      v.strikesAtChange === '2') &&
    (v.ballsAtChange === '0' ||
      v.ballsAtChange === '1' ||
      v.ballsAtChange === '2' ||
      v.ballsAtChange === '3')
  )
}
/** 保存状態を未知memberと値型まで閉じる。 */
export function isSubstitutionState(v: unknown): v is SubstitutionState {
  if (
    !exact(v, [
      'attackingSide',
      'away',
      'home',
      'runners',
      'exitedPlayerIds',
      'responsibility',
    ])
  )
    return false
  if (
    (v.attackingSide !== 'away' && v.attackingSide !== 'home') ||
    !team(v.away) ||
    !team(v.home) ||
    v.away.teamId === v.home.teamId ||
    !Array.isArray(v.runners) ||
    !Array.isArray(v.exitedPlayerIds) ||
    !responsibility(v.responsibility)
  )
    return false
  let seen: Array<string> = []
  for (const item of v.runners) {
    if (!runner(item) || seen.includes(item.runnerId)) return false
    seen = seen.concat([item.runnerId])
  }
  seen = []
  for (const item of v.exitedPlayerIds) {
    if (!uuid(item) || seen.includes(item)) return false
    seen = seen.concat([item])
  }
  return true
}
/** 四種の交代操作を閉じる。 */
export function isSubstitutionOperation(
  v: unknown,
): v is SubstitutionOperation {
  if (!object(v) || (v.side !== 'away' && v.side !== 'home')) return false
  if (v.kind === 'pitcher') {
    if (
      !exact(v, ['kind', 'side', 'outgoingId', 'incomingId', 'count', 'dh']) ||
      !uuid(v.outgoingId) ||
      !uuid(v.incomingId) ||
      !exact(v.count, ['strikes', 'balls'])
    )
      return false
    return (
      (v.count.strikes === '0' ||
        v.count.strikes === '1' ||
        v.count.strikes === '2') &&
      (v.count.balls === '0' ||
        v.count.balls === '1' ||
        v.count.balls === '2' ||
        v.count.balls === '3') &&
      (v.dh === 'retain' || v.dh === 'pitcher-takes-dh-slot')
    )
  }
  if (v.kind === 'pinch-hitter')
    return (
      exact(v, ['kind', 'side', 'outgoingId', 'incomingId', 'battingSlot']) &&
      uuid(v.outgoingId) &&
      uuid(v.incomingId) &&
      slot(v.battingSlot)
    )
  if (v.kind === 'pinch-runner')
    return (
      exact(v, ['kind', 'side', 'outgoingId', 'incomingId', 'base']) &&
      uuid(v.outgoingId) &&
      uuid(v.incomingId) &&
      (v.base === '1' || v.base === '2' || v.base === '3')
    )
  if (v.kind === 'defense') {
    if (!exact(v, ['kind', 'side', 'changes']) || !Array.isArray(v.changes))
      return false
    let count = 0n,
      positions: Array<Slot> = []
    for (const change of v.changes) {
      if (
        !exact(change, ['position', 'outgoingId', 'incomingId']) ||
        !slot(change.position) ||
        positions.includes(change.position) ||
        (change.outgoingId !== null && !uuid(change.outgoingId)) ||
        (change.incomingId !== null && !uuid(change.incomingId))
      )
        return false
      count = count + 1n
      positions = positions.concat([change.position])
    }
    return count >= 1n && count <= 9n
  }
  return false
}
function emptyBatting(): Record<Slot, string> {
  return {
    '1': '',
    '2': '',
    '3': '',
    '4': '',
    '5': '',
    '6': '',
    '7': '',
    '8': '',
    '9': '',
  }
}
function emptyFielding(): Record<Slot, string | null> {
  return {
    '1': null,
    '2': null,
    '3': null,
    '4': null,
    '5': null,
    '6': null,
    '7': null,
    '8': null,
    '9': null,
  }
}
function projectedTeam(v: InitialTeam): SubstitutionTeam {
  const batting = emptyBatting(),
    fielding = emptyFielding()
  let dhSlot: Slot | null = null
  for (const p of v.participants) {
    if (p.batting_slot.kind === 'slot')
      writeKey(batting, p.batting_slot.slot, p.player.player_id)
    for (const role of p.roles) {
      if (role.kind === 'fielding')
        writeKey(fielding, role.position, p.player.player_id)
      else if (p.batting_slot.kind === 'slot') dhSlot = p.batting_slot.slot
    }
  }
  return { teamId: v.team_id, battingOrder: batting, fielding, dhSlot }
}
/** 採用済みinitial-roster射影を表示用初期状態へ写す。 */
export function substitutionFromInitialRoster(
  roster: unknown,
  attackingSide: Side,
): SubstitutionState {
  const teams = (roster as InitialRoster).teams.concat([])
  const away = teams.shift() as InitialTeam,
    home = teams.shift() as InitialTeam
  return {
    attackingSide,
    away: projectedTeam(away),
    home: projectedTeam(home),
    runners: [],
    exitedPlayerIds: [],
    responsibility: { kind: 'unchanged' },
  }
}
function readSlot(
  v: Record<Slot, string | null>,
  position: Slot,
): string | null {
  return readKey(v, position) as string | null
}
function activeIds(v: SubstitutionTeam, runners: Array<Runner>): Array<string> {
  let ids: Array<string> = []
  for (const position of SLOTS) {
    ids = ids.concat([readSlot(v.battingOrder, position) as string])
    const fielder = readSlot(v.fielding, position)
    if (fielder !== null) ids = ids.concat([fielder])
  }
  for (const r of runners) ids = ids.concat([r.runnerId])
  return ids
}
function lineupTeam(v: SubstitutionTeam): ContinuationTeam | null {
  const pitcherId = readSlot(v.fielding, '1'),
    catcherId = readSlot(v.fielding, '2')
  if (pitcherId === null || catcherId === null) return null
  return {
    teamId: v.teamId,
    battingOrder: v.battingOrder,
    pitcherId,
    catcherId,
  }
}
function continuationLineup(v: SubstitutionState): ContinuationLineup | null {
  const away = lineupTeam(v.away),
    home = lineupTeam(v.home)
  if (away === null || home === null) return null
  return { away, home }
}
function warnings(v: SubstitutionState): Array<SubstitutionWarning> {
  let missing = false,
    duplicate = false
  for (const current of [v.away, v.home]) {
    let ids: Array<string> = []
    for (const position of SLOTS) {
      const player = readSlot(current.fielding, position)
      if (player === null) missing = true
      else {
        if (ids.includes(player)) duplicate = true
        ids = ids.concat([player])
      }
    }
  }
  let result: Array<SubstitutionWarning> = []
  if (missing) result = result.concat(['fielding-position-missing'])
  if (duplicate) result = result.concat(['fielding-position-duplicate'])
  return result
}
/** 真正資格とは区別した一回の交代純更新。 */
export function applySubstitution(
  source: SubstitutionState,
  operation: SubstitutionOperation,
  eligibleIncomingIds: Array<string>,
): SubstitutionResult {
  if (!isSubstitutionState(source))
    return { ok: false, error: 'invalid-source' }
  if (!isSubstitutionOperation(operation))
    return { ok: false, error: 'invalid-operation' }
  let oldTeam = source.home
  if (operation.side === 'away') oldTeam = source.away
  let sideRunners: Array<Runner> = []
  if (operation.side === source.attackingSide) sideRunners = source.runners
  const active = activeIds(oldTeam, sideRunners)
  let incoming: Array<string> = []
  if (operation.kind === 'defense')
    for (const change of operation.changes) {
      if (change.incomingId !== null)
        incoming = incoming.concat([change.incomingId])
    }
  else incoming = [operation.incomingId]
  for (const player of incoming) {
    if (!eligibleIncomingIds.includes(player))
      return { ok: false, error: 'unavailable-player' }
    if (source.exitedPlayerIds.includes(player))
      return { ok: false, error: 'reentry' }
  }
  const batting = JSON.parse(JSON.stringify(oldTeam.battingOrder)) as Record<
    Slot,
    string
  >
  const fielding = JSON.parse(JSON.stringify(oldTeam.fielding)) as Record<
    Slot,
    string | null
  >
  const runners = JSON.parse(JSON.stringify(source.runners)) as Array<Runner>
  let dhSlot = oldTeam.dhSlot,
    responsibility = source.responsibility
  if (operation.kind !== 'defense' && active.includes(operation.incomingId))
    return { ok: false, error: 'invalid-operation' }
  if (operation.kind === 'pitcher') {
    if (readSlot(fielding, '1') !== operation.outgoingId)
      return { ok: false, error: 'current-player-mismatch' }
    if (
      operation.side !== source.attackingSide &&
      responsibility.kind !== 'unchanged'
    )
      return { ok: false, error: 'ambiguous-responsibility' }
    writeKey(fielding, '1', operation.incomingId)
    for (const position of SLOTS)
      if (readSlot(batting, position) === operation.outgoingId)
        writeKey(batting, position, operation.incomingId)
    if (operation.side !== source.attackingSide)
      responsibility = {
        kind: 'changed-mid-plate-appearance',
        previousPitcherId: operation.outgoingId,
        reliefPitcherId: operation.incomingId,
        strikesAtChange: operation.count.strikes,
        ballsAtChange: operation.count.balls,
      }
    if (operation.dh === 'pitcher-takes-dh-slot') {
      if (dhSlot === null) return { ok: false, error: 'unsupported-dh-route' }
      writeKey(batting, dhSlot, operation.incomingId)
      dhSlot = null
    }
  } else if (operation.kind === 'pinch-hitter') {
    if (operation.side !== source.attackingSide)
      return { ok: false, error: 'invalid-operation' }
    if (readSlot(batting, operation.battingSlot) !== operation.outgoingId)
      return { ok: false, error: 'current-player-mismatch' }
    writeKey(batting, operation.battingSlot, operation.incomingId)
    for (const position of SLOTS)
      if (readSlot(fielding, position) === operation.outgoingId)
        writeKey(fielding, position, null)
  } else if (operation.kind === 'pinch-runner') {
    if (operation.side !== source.attackingSide)
      return { ok: false, error: 'invalid-operation' }
    let matched = false
    for (const r of runners)
      if (r.base === operation.base && r.runnerId === operation.outgoingId) {
        r.runnerId = operation.incomingId
        matched = true
      }
    if (!matched) return { ok: false, error: 'current-player-mismatch' }
    for (const position of SLOTS) {
      if (readSlot(batting, position) === operation.outgoingId)
        writeKey(batting, position, operation.incomingId)
      if (readSlot(fielding, position) === operation.outgoingId)
        writeKey(fielding, position, null)
    }
  } else {
    for (const change of operation.changes)
      if (readSlot(fielding, change.position) !== change.outgoingId)
        return { ok: false, error: 'current-player-mismatch' }
    for (const change of operation.changes) {
      writeKey(fielding, change.position, change.incomingId)
      if (
        change.outgoingId !== null &&
        change.incomingId !== null &&
        !active.includes(change.incomingId)
      )
        for (const position of SLOTS)
          if (readSlot(batting, position) === change.outgoingId)
            writeKey(batting, position, change.incomingId)
    }
  }
  let unique: Array<string> = []
  for (const position of SLOTS) {
    const player = readSlot(batting, position) as string
    if (unique.includes(player))
      return { ok: false, error: 'invalid-operation' }
    unique = unique.concat([player])
  }
  const nextTeam: SubstitutionTeam = {
    teamId: oldTeam.teamId,
    battingOrder: batting,
    fielding,
    dhSlot,
  }
  let remainingRunners: Array<Runner> = []
  if (operation.side === source.attackingSide) remainingRunners = runners
  const remaining = activeIds(nextTeam, remainingRunners)
  let exited = source.exitedPlayerIds.concat([])
  for (const player of active)
    if (!remaining.includes(player) && !exited.includes(player))
      exited = exited.concat([player])
  let away = source.away
  let home = source.home
  if (operation.side === 'away') away = nextTeam
  else home = nextTeam
  const next: SubstitutionState = {
    attackingSide: source.attackingSide,
    away,
    home,
    runners,
    exitedPlayerIds: exited,
    responsibility,
  }
  return {
    ok: true,
    state: next,
    warnings: warnings(next),
    continuationLineup: continuationLineup(next),
  }
}
/** 規定された2-0/2-1/3-0/3-1/3-2の四球責任。 */
export function walkResponsiblePitcher(
  value: PitcherResponsibility,
  currentPitcherId: string,
): string {
  if (value.kind === 'unchanged') return currentPitcherId
  if (
    (value.ballsAtChange === '2' &&
      (value.strikesAtChange === '0' || value.strikesAtChange === '1')) ||
    value.ballsAtChange === '3'
  )
    return value.previousPitcherId
  return value.reliefPitcherId
}
