import type {
  Checkpoint,
  ActiveFrame,
  Source,
} from '../../../contracts/state-transition/nonplay_prefix_bridge_v1'
import { apiRequest, ApiError } from './client'
import { canonicalUuid } from './authIntent'
import {
  STARTED_GAME_BASE_KEYS,
  isStartedGameMetadata,
  isStartedGameTimestamp,
  type StartedGameMetadata,
} from './startedGame'
import { isLineupPrefixGame } from './lineupPrefixGame'
import { exactPlayObject, playHash } from './terminalPitchWire'
import {
  isOrdinaryAppendPolicy,
  type OrdinaryAppendPolicy,
} from './ordinaryAppendPolicy'
import { sameOrdinaryWire } from './ordinaryPitchWire'
import { isNonplayDefinition } from './nonplayContract'
import identity from '../../public/domain/pitchlog-domain.json'
export type NativeUndoGame = StartedGameMetadata &
  Readonly<{
    read_kind: 'nonplay-prefix'
    profile: 'nonplay-prefix-read-v1'
    checkpoint: Checkpoint
    after: Checkpoint['content']['restored']['current']
    next_position: Readonly<{ d1: string; d2: string }>
    recovery_generation: string
    page: Readonly<{
      items: readonly ActiveFrame[]
      next_cursor: string | null
    }>
    append_policy: OrdinaryAppendPolicy
    last_saved_at: string
  }>
const positive = (v: unknown): v is string =>
  typeof v === 'string' && /^[1-9][0-9]*(?![\s\S])/.test(v)
/** 全metadataとCPを検証する。完全pageかどうかは次段で分ける。 */
export function isNativeUndoGame(v: unknown): v is NativeUndoGame {
  if (
    !exactPlayObject(v, [
      ...STARTED_GAME_BASE_KEYS,
      'profile',
      'checkpoint',
      'after',
      'next_position',
      'recovery_generation',
      'page',
      'append_policy',
      'last_saved_at',
    ]) ||
    !isStartedGameMetadata(v) ||
    v.read_kind !== 'nonplay-prefix' ||
    v.profile !== 'nonplay-prefix-read-v1' ||
    !isNonplayDefinition<Checkpoint>(v.checkpoint, 'Checkpoint') ||
    !sameOrdinaryWire(v.after, v.checkpoint.content.restored.current) ||
    !exactPlayObject(v.next_position, ['d1', 'd2']) ||
    !positive(v.next_position.d1) ||
    !positive(v.next_position.d2) ||
    !positive(v.recovery_generation) ||
    !isOrdinaryAppendPolicy(v.append_policy) ||
    !isStartedGameTimestamp(v.last_saved_at) ||
    !exactPlayObject(v.page, ['items', 'next_cursor']) ||
    !Array.isArray(v.page.items) ||
    v.page.items.length > 100 ||
    !v.page.items.every((x) => isNonplayDefinition(x, 'ActiveFrame')) ||
    (v.page.next_cursor !== null &&
      (typeof v.page.next_cursor !== 'string' ||
        v.page.next_cursor.length < 1 ||
        v.page.next_cursor.length > 2048))
  )
    return false
  const c = v.checkpoint.content
  return (
    c.scope.gameId === v.id &&
    c.scope.generation === v.current_d4 &&
    BigInt(v.next_position.d1) === BigInt(c.d3) + 1n &&
    BigInt(v.page.items.length) <= BigInt(c.activeDepth)
  )
}
/** 認証済み実GETだけを使い、409/503や不完全応答を成功へ補完しない。 */
export async function readNativeUndoGame(
  gameId: string,
  signal?: AbortSignal,
  cursor: string | null = null,
): Promise<NativeUndoGame> {
  if (!canonicalUuid.test(gameId) || gameId.length !== 36)
    throw new Error('試合を確認できません')
  const value = await apiRequest<unknown>('GET', `/games/${gameId}/started`, {
    tenantBound: true,
    query: {
      projection: 'undo-prefix-v1',
      limit: 100,
      ...(cursor === null ? {} : { cursor }),
    },
    signal,
  })
  if (!isNativeUndoGame(value) || value.id !== gameId)
    throw new Error('取消用の保存原本を確認できません')
  return value
}
/** 不完全pageをstackにせず、原本digestと文脈の連鎖を保持する。 */
export async function completeUndoSource(
  game: NativeUndoGame,
  tenantId: string,
  frames: readonly ActiveFrame[] = game.page.items,
): Promise<Source> {
  if (
    !isNativeUndoGame(game) ||
    game.checkpoint.content.scope.tenantId !== tenantId ||
    game.page.next_cursor !== null ||
    BigInt(frames.length) !== BigInt(game.checkpoint.content.activeDepth) ||
    game.checkpoint.content.executionArtifactSha256 !== identity.sha256 ||
    (await playHash(game.checkpoint.content)) !== game.checkpoint.ref.digest
  )
    throw new Error('完全な取消原本を確認できません')
  const source = {
    formatVersion: 'nonplay-prefix-source-v1' as const,
    checkpoint: structuredClone(game.checkpoint),
    activeStack: structuredClone(frames),
  }
  if (!isNonplayDefinition<Source>(source, 'Source'))
    throw new Error('取消原本の型が不一致です')
  const c = source.checkpoint.content
  if (
    c.d1Head === null ||
    c.d1Head.source.gameId !== game.id ||
    c.d1Head.source.generation !== game.current_d4 ||
    c.d1Head.source.d1 !== c.d3
  )
    throw new Error('現在headの位置が不一致です')
  const seenPlays = new Set<string>(),
    seenEvents = new Set<string>(),
    seenD5 = new Set<string>()
  const activeFrames = source.activeStack
  for (let i = 0; i < activeFrames.length; i++) {
    const frame = activeFrames[i]!
    if (
      seenPlays.has(frame.play.playId) ||
      seenEvents.has(frame.play.source.eventId) ||
      seenD5.has(frame.play.source.d5) ||
      BigInt(frame.play.physicalPlayNumber) >= BigInt(c.nextPhysicalPlayNumber)
    )
      throw new Error('取消履歴の識別/物理順が不一致です')
    seenPlays.add(frame.play.playId)
    seenEvents.add(frame.play.source.eventId)
    seenD5.add(frame.play.source.d5)
    if (
      frame.play.source.gameId !== game.id ||
      frame.play.source.eventKind !== 'play_input' ||
      (i === 0 &&
        (!sameOrdinaryWire(frame.play, source.checkpoint.content.activeHead) ||
          !sameOrdinaryWire(
            frame.afterContext,
            source.checkpoint.content.restored,
          ))) ||
      (i > 0 &&
        !sameOrdinaryWire(
          activeFrames[i - 1]!.beforeContext,
          frame.afterContext,
        ))
    )
      throw new Error('取消履歴の連結が不一致です')
  }
  if (
    (activeFrames.length === 0) !==
    (source.checkpoint.content.activeHead === null)
  )
    throw new Error('取消対象の有無が不一致です')
  return source
}

/** 有限pageを同一CPで連結する。途中更新/重複cursorを検出したら全部閉拒否。 */
export async function readCompleteUndoGame(
  gameId: string,
  tenantId: string,
  signal?: AbortSignal,
): Promise<{ game: NativeUndoGame; source: Source; storedNative: boolean }> {
  let game = await readNativeUndoGame(gameId, signal)
  const anchor = { ...game, page: null },
    frames = [...game.page.items],
    seen = new Set<string>()
  while (game.page.next_cursor !== null) {
    const cursor = game.page.next_cursor
    if (seen.has(cursor)) throw new Error('取消履歴のcursorが循環しています')
    seen.add(cursor)
    const next = await readNativeUndoGame(gameId, signal, cursor)
    if (
      !sameOrdinaryWire({ ...next, page: null }, anchor) ||
      next.page.items.length === 0
    )
      throw new Error('取消原本が取得中に変わりました')
    frames.push(...next.page.items)
    game = next
  }
  const source = await completeUndoSource(game, tenantId, frames)
  let standard: unknown
  try {
    standard = await apiRequest<unknown>('GET', `/games/${gameId}/started`, {
      tenantBound: true,
      query: { projection: 'play-prefix-v3', limit: 1 },
      signal,
    })
  } catch (error) {
    if (
      signal?.aborted ||
      (error instanceof ApiError && [401, 403].includes(error.status))
    )
      throw error
    return { game, source, storedNative: false }
  }
  let storedNative = false
  if (isNativeUndoGame(standard)) {
    if (
      !sameOrdinaryWire(standard.checkpoint, game.checkpoint) ||
      !sameOrdinaryWire(standard.next_position, game.next_position) ||
      standard.recovery_generation !== game.recovery_generation
    )
      throw new Error('実保存CPが取得中に変わりました')
    storedNative = true
  } else if (
    !isLineupPrefixGame(standard) ||
    standard.prefix_ref.tenantId !== tenantId ||
    standard.id !== game.id ||
    standard.current_d4 !== game.current_d4 ||
    standard.checkpoint_anchor?.id !== game.checkpoint.ref.id ||
    standard.checkpoint_anchor?.revision !== game.checkpoint.ref.revision ||
    standard.next_position.d1 !== game.next_position.d1 ||
    standard.recovery_generation !== game.recovery_generation ||
    !sameOrdinaryWire(standard.after, game.after) ||
    !sameOrdinaryWire(standard.rules, game.checkpoint.content.restored.rules) ||
    !sameOrdinaryWire(
      standard.lineup,
      game.checkpoint.content.restored.lineup,
    ) ||
    !sameOrdinaryWire(
      standard.participants,
      game.checkpoint.content.restored.participants,
    ) ||
    !sameOrdinaryWire(
      standard.runners,
      game.checkpoint.content.restored.runners,
    ) ||
    standard.roster_digest !== game.checkpoint.content.restored.rosterDigest ||
    standard.prefix_ref.historyVersion !==
      game.checkpoint.content.historyVersion ||
    standard.storage_anchor?.history_epoch !==
      game.checkpoint.content.storageHistoryEpoch
  )
    throw new Error('派生CPと保存原本が一致しません')
  return {
    game,
    source,
    storedNative,
  }
}
