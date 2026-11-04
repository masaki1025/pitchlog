import type {
  Snapshot,
  PrefixRef,
  SavedRuleWire,
  T2,
  HistoryEntry,
  PlayIdentity,
  Responsibility,
  Lineup,
  Participant,
  Runner,
} from '../../../contracts/state-transition/lineup_play_prefix_v1'
import { ApiError, apiRequest } from './client'
import { canonicalUuid } from './authIntent'
import {
  isOrdinaryAppendPolicy,
  type OrdinaryAppendPolicy,
} from './ordinaryAppendPolicy'
import { sameOrdinaryWire, isOrdinarySavedRules } from './ordinaryPitchWire'
import { exactPlayObject } from './terminalPitchWire'
import { isLineupDefinition } from './lineupPrefixWire'
import {
  STARTED_GAME_BASE_KEYS,
  isStartedGameMetadata,
  isStartedGameTimestamp,
  isRecordedPrefixPlayRow,
  type RecordedPrefixPlayRow,
  type StartedGameMetadata,
} from './startedGame'
export type LineupPrefixGame = StartedGameMetadata &
  Readonly<{
    read_kind: 'lineup-prefix'
    after: Snapshot
    prefix_ref: PrefixRef
    rules: SavedRuleWire
    t2: T2 | null
    last_entry: HistoryEntry | null
    last_source: PlayIdentity | null
    prior_artifact_sha256: string
    pa_start_source: Responsibility['paStartSource']
    lineup: Lineup
    roster_digest: string
    runners: readonly Runner[]
    participants: Participant
    next_position: Readonly<{ d1: string; d2: string }>
    checkpoint_anchor: Readonly<{
      id: string
      revision: string
      history_version: string
    }> | null
    storage_anchor: Readonly<{ id: string; history_epoch: string }> | null
    recovery_generation: string
    append_policy: OrdinaryAppendPolicy
    last_saved_at: string
    page: Readonly<{
      items: readonly Readonly<{
        play_row: RecordedPrefixPlayRow
        history_entry: HistoryEntry
        play_runners: readonly Record<string, unknown>[]
      }>[]
      next_cursor: string | null
    }>
  }>
const uuid = (x: unknown): x is string =>
  typeof x === 'string' && x.length === 36 && canonicalUuid.test(x)
const positive = (x: unknown): x is string =>
  typeof x === 'string' && /^[1-9][0-9]*$/.test(x) && x.trim() === x
const cursor = (x: unknown): x is string | null =>
  x === null ||
  (typeof x === 'string' &&
    x.length > 0 &&
    x.length <= 2048 &&
    !/[\u0000-\u001f\u007f]/.test(x))
/** native headだけを閉検証し、欠測cursorや未知variantを補わない。 */
export function isLineupPrefixGame(v: unknown): v is LineupPrefixGame {
  if (
    !exactPlayObject(v, [
      ...STARTED_GAME_BASE_KEYS,
      'after',
      'prefix_ref',
      'rules',
      't2',
      'last_entry',
      'last_source',
      'prior_artifact_sha256',
      'pa_start_source',
      'lineup',
      'roster_digest',
      'runners',
      'participants',
      'next_position',
      'checkpoint_anchor',
      'storage_anchor',
      'recovery_generation',
      'page',
      'append_policy',
      'last_saved_at',
    ]) ||
    v.read_kind !== 'lineup-prefix' ||
    !isStartedGameMetadata(v) ||
    !isLineupDefinition<Snapshot>(v.after, 'Snapshot') ||
    !isLineupDefinition<PrefixRef>(v.prefix_ref, 'PrefixRef') ||
    v.prefix_ref.gameId !== v.id ||
    v.prefix_ref.generation !== v.current_d4 ||
    !isOrdinarySavedRules(v.rules) ||
    !isOrdinaryAppendPolicy(v.append_policy) ||
    !isStartedGameTimestamp(v.last_saved_at) ||
    !isLineupDefinition(v.prior_artifact_sha256, 'Digest') ||
    !isLineupDefinition<Lineup>(v.lineup, 'Lineup') ||
    !isLineupDefinition(v.roster_digest, 'Digest') ||
    !isLineupDefinition<Participant>(v.participants, 'Participant') ||
    !exactPlayObject(v.pa_start_source, ['kind', 'id']) ||
    !['started-game', 'confirmed-play'].includes(
      String(v.pa_start_source.kind),
    ) ||
    !uuid(v.pa_start_source.id) ||
    !positive(v.recovery_generation) ||
    !exactPlayObject(v.next_position, ['d1', 'd2']) ||
    !positive(v.next_position.d1) ||
    !positive(v.next_position.d2) ||
    !Array.isArray(v.runners) ||
    v.runners.length > 3 ||
    !v.runners.every((r) => isLineupDefinition(r, 'Runner')) ||
    (v.t2 !== null && !isLineupDefinition(v.t2, 'T2')) ||
    (v.last_entry !== null &&
      !isLineupDefinition(v.last_entry, 'HistoryEntry')) ||
    (v.last_source !== null &&
      !isLineupDefinition(v.last_source, 'PlayIdentity')) ||
    !exactPlayObject(v.page, ['items', 'next_cursor']) ||
    !Array.isArray(v.page.items) ||
    v.page.items.length > 100 ||
    !cursor(v.page.next_cursor) ||
    (v.page.next_cursor !== null && v.page.items.length === 0)
  )
    return false
  const zero = v.prefix_ref.length === '0'
  if (zero) {
    const initial = {
      stateFields: v.after.stateFields,
      scoreboard: v.after.scoreboard,
    }
    if (
      !sameOrdinaryWire(initial, v.state) ||
      v.last_source !== null ||
      v.last_entry !== null ||
      v.t2 !== null ||
      v.checkpoint_anchor !== null ||
      v.storage_anchor !== null ||
      v.page.items.length !== 0 ||
      v.page.next_cursor !== null ||
      v.runners.length !== 0 ||
      v.last_saved_at !== v.started_at
    )
      return false
  } else if (v.last_source === null || v.last_entry === null || v.t2 === null)
    return false
  if (
    !zero &&
    (!exactPlayObject(v.checkpoint_anchor, [
      'id',
      'revision',
      'history_version',
    ]) ||
      !uuid(v.checkpoint_anchor.id) ||
      !positive(v.checkpoint_anchor.revision) ||
      !positive(v.checkpoint_anchor.history_version) ||
      !exactPlayObject(v.storage_anchor, ['id', 'history_epoch']) ||
      !uuid(v.storage_anchor.id) ||
      !positive(v.storage_anchor.history_epoch) ||
      v.storage_anchor.id !== v.checkpoint_anchor.id ||
      v.storage_anchor.history_epoch !== v.checkpoint_anchor.history_version ||
      v.prefix_ref.origin.eventId !== v.checkpoint_anchor.id ||
      v.prefix_ref.checkpoint.revision !== v.checkpoint_anchor.revision)
  )
    return false
  for (const side of ['away', 'home'] as const) {
    const team = v.roster.teams.find((t) => t.side === side),
      provided = v.lineup[side]
    if (!team || team.team_id !== provided.teamId) return false
    for (const [slot, id] of Object.entries(provided.battingOrder))
      if (
        !team.participants.some(
          (p) =>
            p.player.player_id === id &&
            p.batting_slot.kind === 'slot' &&
            p.batting_slot.slot === slot,
        )
      )
        return false
    for (const [role, id] of [
      ['1', provided.pitcherId],
      ['2', provided.catcherId],
    ])
      if (
        !team.participants.some(
          (p) =>
            p.player.player_id === id &&
            p.roles.some((r) => r.kind === 'fielding' && r.position === role),
        )
      )
        return false
  }
  const ids = new Set<string>()
  for (const item of v.page.items) {
    if (
      !exactPlayObject(item, ['play_row', 'history_entry', 'play_runners']) ||
      !isRecordedPrefixPlayRow(item.play_row) ||
      item.play_row.game_id !== v.id ||
      ids.has(item.play_row.id) ||
      !isLineupDefinition(item.history_entry, 'HistoryEntry') ||
      !Array.isArray(item.play_runners) ||
      item.play_runners.length > 3
    )
      return false
    ids.add(item.play_row.id)
    for (const row of item.play_runners)
      if (
        !exactPlayObject(row, [
          'id',
          'play_id',
          'base',
          'runner_id',
          'status',
          'status_source',
          'responsible_pitcher_id',
        ]) ||
        !uuid(row.id) ||
        row.play_id !== item.play_row.id ||
        !uuid(row.runner_id) ||
        !uuid(row.responsible_pitcher_id) ||
        typeof row.base !== 'number' ||
        ![1, 2, 3].includes(row.base) ||
        row.status !== '継続' ||
        row.status_source !== 'auto'
      )
        return false
  }
  const r = v.applied_rules
  return sameOrdinaryWire(v.rules, {
    regulationInnings: String(r.regulationInnings),
    coldConditions: r.coldConditions.map((c) => ({
      pointDifference: String(c.pointDifference),
      startInning: String(c.startInning),
    })),
    extensionLimit: r.extensionLimit === null ? null : String(r.extensionLimit),
    tiebreak:
      r.tiebreak === null
        ? null
        : {
            startInning: String(r.tiebreak.startInning),
            runnerPlacement: r.tiebreak.runnerPlacement,
            leadoffRule: r.tiebreak.leadoffRule,
          },
    dh: r.dh,
  })
}
export async function readLineupPrefixGame(
  id: string,
  pageCursor: string | null = null,
  limit = 25,
  signal?: AbortSignal,
): Promise<
  | { kind: 'found'; game: LineupPrefixGame }
  | { kind: 'not-found' | 'unavailable' | 'unsupported' }
> {
  if (
    !uuid(id) ||
    !cursor(pageCursor) ||
    !Number.isSafeInteger(limit) ||
    limit < 1 ||
    limit > 100
  )
    throw new Error('記録の読取条件が正しくありません')
  let value: unknown
  try {
    value = await apiRequest<unknown>('GET', `/games/${id}/started`, {
      tenantBound: true,
      query: {
        projection: 'play-prefix-v3',
        limit,
        ...(pageCursor === null ? {} : { cursor: pageCursor }),
      },
      signal,
    })
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 404) return { kind: 'not-found' }
      if (error.status === 409) return { kind: 'unavailable' }
      if ([400, 422, 501].includes(error.status)) return { kind: 'unsupported' }
    }
    throw error
  }
  if (
    !isLineupPrefixGame(value) ||
    value.id !== id ||
    value.page.items.length > limit ||
    (value.page.next_cursor !== null && value.page.next_cursor === pageCursor)
  )
    throw new Error('記録の応答を確認できません')
  return { kind: 'found', game: value }
}
