import type {
  PrefixRef as PlayRef,
  V1Ref,
  Snapshot,
  PlayT2,
  OrdinaryT2,
  T2NoEndCore as PlayLegacyT2,
  HistoryEntry,
  PlayIdentity,
  Responsibility,
  Checkpoint,
  Bridge,
  Runner,
  Participant,
} from '../../../contracts/state-transition/play_prefix_v2'
import { isPlayDefinition, exactPlayObject } from './terminalPitchWire'

import {
  isOrdinaryAppendPolicy,
  type OrdinaryAppendPolicy,
} from './ordinaryAppendPolicy'
import { ApiError, apiRequest } from './client'
import { canonicalUuid } from './authIntent'
import type {
  StateSnapshot,
  T2NoEndCore,
} from '../../../contracts/state-transition/t2_first_pitch_continuation_v1'
import {
  STARTED_GAME_BASE_KEYS,
  isStartedGameMetadata,
  isStartedGameStateSnapshot,
  isStartedGameTimestamp,
  isLegacyStartedT2,
  isRecordedPrefixPlayRow,
  isStartedGame,
  isStartedRecordedGame,
  type StartedGameMetadata,
  type RecordedPrefixPlayRow,
} from './startedGame'
import {
  isOrdinaryPrefixRef,
  isOrdinarySavedRules,
  isOrdinaryNoEnd,
  isOrdinaryHistoryEntry,
  sameOrdinaryWire,
  type OrdinaryPrefixRef,
  type OrdinaryNoEnd,
  type OrdinaryHistoryEntry,
  type OrdinaryContinuationRequest,
} from './ordinaryPitchWire'
import type { OrdinaryRecordingContext } from '../screens/GameScreenOrdinaryPitchProvider'

export type RecordedPrefixGame = StartedGameMetadata &
  Readonly<{
    last_saved_at: string
    append_policy: OrdinaryAppendPolicy
    read_kind: 'recorded-prefix'
    after: StateSnapshot
    prefix_ref: OrdinaryPrefixRef
    rules: OrdinaryContinuationRequest['rules']
    t2: OrdinaryNoEnd | T2NoEndCore | null
    last_entry: OrdinaryHistoryEntry | null
    next_position: Readonly<{ d1: string; d2: string }>
    checkpoint_anchor: Readonly<{
      id: string
      revision: string
      history_version: string
    }> | null
    recovery_generation: string
    page: Readonly<{
      items: readonly Readonly<{
        play_row: RecordedPrefixPlayRow
        history_entry: OrdinaryHistoryEntry
      }>[]
      next_cursor: string | null
    }>
  }>
function exact(
  v: unknown,
  keys: readonly string[],
): v is Record<string, unknown> {
  return (
    v !== null &&
    typeof v === 'object' &&
    !Array.isArray(v) &&
    Object.keys(v).length === keys.length &&
    keys.every((k) => Object.hasOwn(v, k))
  )
}
function positive(v: unknown): v is string {
  return typeof v === 'string' && /^[1-9][0-9]*$/.test(v) && v.trim() === v
}
function uuid(v: unknown): v is string {
  return typeof v === 'string' && v.length === 36 && canonicalUuid.test(v)
}
function cursor(v: unknown): v is string | null {
  return (
    v === null ||
    (typeof v === 'string' &&
      v.length > 0 &&
      v.length <= 2048 &&
      !/[\u0000-\u001f\u007f]/.test(v))
  )
}
/** finite pageは全履歴を表さず、空prefixにcheckpoint UUIDを捏造しない。 */
export function isRecordedPrefixGame(v: unknown): v is RecordedPrefixGame {
  if (
    !exact(v, [
      ...STARTED_GAME_BASE_KEYS,
      'after',
      'prefix_ref',
      'rules',
      't2',
      'last_entry',
      'next_position',
      'checkpoint_anchor',
      'recovery_generation',
      'page',
      'append_policy',
      'last_saved_at',
    ]) ||
    v.read_kind !== 'recorded-prefix' ||
    !isOrdinaryAppendPolicy(v.append_policy) ||
    !isStartedGameTimestamp(v.last_saved_at) ||
    !isStartedGameMetadata(v) ||
    !isStartedGameStateSnapshot(v.after) ||
    !isOrdinaryPrefixRef(v.prefix_ref) ||
    v.prefix_ref.gameId !== v.id ||
    v.prefix_ref.generation !== v.current_d4 ||
    !isOrdinarySavedRules(v.rules) ||
    !exact(v.next_position, ['d1', 'd2']) ||
    !positive(v.next_position.d1) ||
    !positive(v.next_position.d2) ||
    !positive(v.recovery_generation)
  )
    return false
  const n = BigInt(v.prefix_ref.length)
  if (n === 0n) {
    if (
      v.last_saved_at !== v.started_at ||
      v.t2 !== null ||
      v.last_entry !== null ||
      v.checkpoint_anchor !== null ||
      !sameOrdinaryWire(v.after, v.state)
    )
      return false
  } else if (
    (!isOrdinaryNoEnd(v.t2) && !(n === 1n && isLegacyStartedT2(v.t2))) ||
    !isOrdinaryHistoryEntry(v.last_entry)
  )
    return false
  if (v.checkpoint_anchor === null) {
    if (n > 1n) return false
  } else if (
    !exact(v.checkpoint_anchor, ['id', 'revision', 'history_version']) ||
    !uuid(v.checkpoint_anchor.id) ||
    !positive(v.checkpoint_anchor.revision) ||
    !positive(v.checkpoint_anchor.history_version)
  )
    return false
  if (
    !exact(v.page, ['items', 'next_cursor']) ||
    !Array.isArray(v.page.items) ||
    v.page.items.length > 100 ||
    !cursor(v.page.next_cursor) ||
    (n === 0n && v.page.items.length !== 0) ||
    (v.page.next_cursor !== null && v.page.items.length === 0)
  )
    return false
  const ids = new Set<string>()
  for (const item of v.page.items) {
    if (
      !exact(item, ['play_row', 'history_entry']) ||
      !isRecordedPrefixPlayRow(item.play_row) ||
      item.play_row.game_id !== v.id ||
      !isOrdinaryHistoryEntry(item.history_entry) ||
      ids.has(item.play_row.id)
    )
      return false
    ids.add(item.play_row.id)
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
export type RecordedPrefixRead =
  | { kind: 'found'; game: RecordedPrefixGame }
  | { kind: 'not-found' }
  | { kind: 'unavailable' }
  | { kind: 'unsupported' }
/** 旧queryなしの入口を変えず、明示ordinary projectionだけを要求する。 */
export async function readRecordedPrefixGame(
  id: string,
  pageCursor: string | null = null,
  limit = 25,
  signal?: AbortSignal,
): Promise<RecordedPrefixRead> {
  if (
    !uuid(id) ||
    !Number.isSafeInteger(limit) ||
    limit < 1 ||
    limit > 100 ||
    !cursor(pageCursor)
  )
    throw new Error('通常記録の読取条件が正しくありません')
  let value: unknown
  try {
    value = await apiRequest<unknown>('GET', `/games/${id}/started`, {
      tenantBound: true,
      query: {
        projection: 'ordinary-prefix-v1',
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
    isRecordedPrefixGame(value) &&
    value.id === id &&
    value.page.items.length <= limit &&
    (value.page.next_cursor === null || value.page.next_cursor !== pageCursor)
  )
    return { kind: 'found', game: value }
  // 未提供のサーバーが旧応答を返しても、新projectionの成功に昇格しない。
  if ((isStartedGame(value) || isStartedRecordedGame(value)) && value.id === id)
    return { kind: 'unsupported' }
  throw new Error('通常記録prefixの応答が正しくありません')
}
/** server由来のafter/T2/rulesと独立next_positionを、そのまま計算contextへ供給する。 */
export function ordinaryContextFromRead(
  value: RecordedPrefixGame,
  tenantId: string,
): OrdinaryRecordingContext {
  if (
    !isRecordedPrefixGame(value) ||
    !uuid(tenantId) ||
    value.prefix_ref.tenantId !== tenantId
  )
    throw new Error('通常記録のtenantを確認できません')
  const metadata = Object.fromEntries(
    STARTED_GAME_BASE_KEYS.filter((k) => k !== 'read_kind').map((k) => [
      k,
      value[k],
    ]),
  ) as StartedGameMetadata
  return structuredClone({
    game: metadata,
    prefixRef: value.prefix_ref,
    rules: value.rules,
    after: value.after,
    t2: value.t2,
    priorKind:
      BigInt(value.prefix_ref.length) === 0n
        ? 'started-initial'
        : 'evaluated-prefix',
    nextPosition: value.next_position,
    source: 'server-confirmed',
    appendPolicy: value.append_policy,
  })
}

// 旧ordinary DTOを拡張せず、実v2 GETを独立した閉variantとして扱う。
export type PlayPrefixGame = StartedGameMetadata &
  Readonly<{
    read_kind: 'play-prefix'
    after: Snapshot
    prefix_ref: PlayRef | V1Ref
    rules: OrdinaryContinuationRequest['rules']
    t2: PlayT2 | OrdinaryT2 | PlayLegacyT2 | null
    last_entry: HistoryEntry | null
    next_position: Readonly<{ d1: string; d2: string }>
    checkpoint_anchor: RecordedPrefixGame['checkpoint_anchor']
    recovery_generation: string
    page: Readonly<{
      items: readonly Readonly<{
        play_row: RecordedPrefixPlayRow
        history_entry: HistoryEntry
        play_runners: readonly Record<string, unknown>[]
      }>[]
      next_cursor: string | null
    }>
    append_policy: OrdinaryAppendPolicy
    last_saved_at: string
    last_source: PlayIdentity | null
    prior_artifact_sha256: string
    pa_start_source: Responsibility['paStartSource']
    bridge_checkpoint: Checkpoint | null
    storage_anchor: Readonly<{ id: string; history_epoch: string }> | null
    bridge_origin: Bridge | null
    runners: readonly Runner[]
    participants: Participant | null
  }>
export function isPlayPrefixGame(v: unknown): v is PlayPrefixGame {
  if (
    !exactPlayObject(v, [
      ...STARTED_GAME_BASE_KEYS,
      'after',
      'prefix_ref',
      'rules',
      't2',
      'last_entry',
      'next_position',
      'checkpoint_anchor',
      'recovery_generation',
      'page',
      'append_policy',
      'last_saved_at',
      'last_source',
      'prior_artifact_sha256',
      'pa_start_source',
      'bridge_checkpoint',
      'storage_anchor',
      'bridge_origin',
      'runners',
      'participants',
    ]) ||
    v.read_kind !== 'play-prefix' ||
    !isStartedGameMetadata(v) ||
    !isPlayDefinition<Snapshot>(v.after, 'Snapshot') ||
    (!isPlayDefinition<PlayRef>(v.prefix_ref, 'PrefixRef') &&
      !isPlayDefinition<V1Ref>(v.prefix_ref, 'V1Ref')) ||
    v.prefix_ref.gameId !== v.id ||
    v.prefix_ref.generation !== v.current_d4 ||
    !isOrdinarySavedRules(v.rules) ||
    !isOrdinaryAppendPolicy(v.append_policy) ||
    !isStartedGameTimestamp(v.last_saved_at) ||
    !exactPlayObject(v.next_position, ['d1', 'd2']) ||
    !positive(v.next_position.d1) ||
    !positive(v.next_position.d2) ||
    !positive(v.recovery_generation) ||
    !isPlayDefinition(v.prior_artifact_sha256, 'Digest') ||
    !exactPlayObject(v.pa_start_source, ['kind', 'id']) ||
    !['started-game', 'confirmed-play'].includes(
      String(v.pa_start_source.kind),
    ) ||
    !uuid(v.pa_start_source.id) ||
    (v.last_source !== null &&
      !isPlayDefinition(v.last_source, 'PlayIdentity')) ||
    (v.last_entry !== null &&
      !isPlayDefinition(v.last_entry, 'HistoryEntry')) ||
    (v.t2 !== null &&
      !['PlayT2', 'OrdinaryT2', 'T2NoEndCore'].some((name) =>
        isPlayDefinition(v.t2, name),
      )) ||
    (v.checkpoint_anchor !== null &&
      (!exactPlayObject(v.checkpoint_anchor, [
        'id',
        'revision',
        'history_version',
      ]) ||
        !uuid(v.checkpoint_anchor.id) ||
        !positive(v.checkpoint_anchor.revision) ||
        !positive(v.checkpoint_anchor.history_version))) ||
    !Array.isArray(v.runners) ||
    v.runners.length > 3 ||
    !v.runners.every((r) => isPlayDefinition(r, 'Runner')) ||
    !exactPlayObject(v.page, ['items', 'next_cursor']) ||
    !Array.isArray(v.page.items) ||
    v.page.items.length > 100 ||
    !cursor(v.page.next_cursor) ||
    (v.page.next_cursor !== null && v.page.items.length === 0)
  )
    return false
  const n = BigInt(v.prefix_ref.length)
  if (
    n === 0n &&
    (v.last_source !== null ||
      v.t2 !== null ||
      v.last_entry !== null ||
      v.checkpoint_anchor !== null ||
      v.page.items.length !== 0 ||
      v.page.next_cursor !== null ||
      !sameOrdinaryWire(v.after, v.state) ||
      v.last_saved_at !== v.started_at)
  )
    return false
  if (
    n > 0n &&
    (v.last_source === null || v.last_entry === null || v.t2 === null)
  )
    return false
  if (v.prefix_ref.version === '1') {
    if (
      !isPlayDefinition(v.bridge_checkpoint, 'Checkpoint') ||
      v.storage_anchor !== null ||
      v.bridge_origin !== null ||
      v.runners.length !== 0 ||
      v.participants !== null
    )
      return false
  } else {
    if (
      v.prefix_ref.origin.tenantId !== v.prefix_ref.tenantId ||
      v.prefix_ref.origin.gameId !== v.id ||
      v.prefix_ref.origin.generation !== v.current_d4
    )
      return false
    if (
      v.bridge_checkpoint !== null ||
      !isPlayDefinition<Bridge>(v.bridge_origin, 'Bridge') ||
      !isPlayDefinition(v.participants, 'Participant') ||
      !isPlayDefinition(v.t2, 'PlayT2') ||
      !exactPlayObject(v.storage_anchor, ['id', 'history_epoch']) ||
      !uuid(v.storage_anchor.id) ||
      !positive(v.storage_anchor.history_epoch) ||
      !v.checkpoint_anchor ||
      v.storage_anchor.id !== v.checkpoint_anchor.id ||
      v.storage_anchor.history_epoch !== v.checkpoint_anchor.history_version ||
      v.prefix_ref.checkpoint.revision !== v.checkpoint_anchor.revision ||
      !sameOrdinaryWire(v.bridge_origin.v1Ref, v.prefix_ref.origin)
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
      !isPlayDefinition(item.history_entry, 'HistoryEntry') ||
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
          'runner_id',
          'responsible_pitcher_id',
          'base',
          'status',
          'status_source',
        ]) ||
        !uuid(row.id) ||
        row.play_id !== item.play_row.id ||
        !uuid(row.runner_id) ||
        !uuid(row.responsible_pitcher_id) ||
        ![1, 2, 3].includes(Number(row.base)) ||
        typeof row.base !== 'number' ||
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
export async function readPlayPrefixGame(
  id: string,
  pageCursor: string | null = null,
  limit = 25,
  signal?: AbortSignal,
): Promise<
  | { kind: 'found'; game: PlayPrefixGame }
  | { kind: 'not-found' | 'unavailable' | 'unsupported' }
> {
  if (
    !uuid(id) ||
    !Number.isSafeInteger(limit) ||
    limit < 1 ||
    limit > 100 ||
    !cursor(pageCursor)
  )
    throw new Error('記録の読取条件が正しくありません')
  let value: unknown
  try {
    value = await apiRequest<unknown>('GET', `/games/${id}/started`, {
      tenantBound: true,
      query: {
        projection: 'play-prefix-v2',
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
    isPlayPrefixGame(value) &&
    value.id === id &&
    value.page.items.length <= limit &&
    (value.page.next_cursor === null || value.page.next_cursor !== pageCursor)
  )
    return { kind: 'found', game: value }
  throw new Error('記録の応答を確認できません')
}
