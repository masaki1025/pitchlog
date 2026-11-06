import type {
  Source,
  UndoPayload,
  Target,
} from '../../../contracts/state-transition/nonplay_prefix_bridge_v1'
import type {
  Request as UndoRequest,
  AppliedValue,
} from '../../../contracts/state-transition/undo_v1'
import type {
  NonplayRequest,
  NonplaySuccess,
  PlayIdentity,
} from '../../../contracts/state-transition/lineup_play_prefix_v1'
import type { NonplayNormalV7 } from '../../../contracts/state-transition/lineup_play_prefix_payload_v1'
import type { Observations } from '../../../contracts/state-transition/play_prefix_v2_payload_v1'
import type { NativeUndoGame } from '../api/nativeUndoGame'
import { completeUndoSource } from '../api/nativeUndoGame'
import { isNonplayDefinition } from '../api/nonplayContract'
import { nativeUndoDraft } from '../api/nativeUndoWire'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import { invokeFirstBallDomain } from '../lib/generated/wrappers/domainArtifact'
import identity from '../../public/domain/pitchlog-domain.json'
import type { SyncEvent } from '../lib/sync/syncEvent'
export type UndoProductContext = Readonly<{
  game: NativeUndoGame
  source: Source
  tenantId: string
  storedNative: boolean
}>
const safe = (value: string) => {
  if (
    !/^[1-9][0-9]*(?![\s\S])/.test(value) ||
    BigInt(value) > BigInt(Number.MAX_SAFE_INTEGER)
  )
    throw new Error('端末の位置範囲を確認できません')
  return Number(value)
}
export async function undoContext(
  game: NativeUndoGame,
  tenantId: string,
  frames = game.page.items,
  storedNative = false,
): Promise<UndoProductContext> {
  return {
    game: structuredClone(game),
    tenantId,
    storedNative,
    source: await completeUndoSource(game, tenantId, frames),
  }
}
function assertContext(c: UndoProductContext): void {
  if (
    c.source.checkpoint.content.scope.tenantId !== c.tenantId ||
    c.source.checkpoint.content.scope.gameId !== c.game.id ||
    !sameOrdinaryWire(c.source.checkpoint, c.game.checkpoint) ||
    c.source.checkpoint.content.executionArtifactSha256 !== identity.sha256
  )
    throw new Error('取消文脈の同一性が不一致です')
}
/** 全stackを唯一artifactへ渡し、状態差分を画面で再計算しない。空ならeventを作らない。 */
export function prepareNativeUndo(
  c: UndoProductContext,
  d5: string,
): SyncEvent | null {
  assertContext(c)
  const frames = c.source.activeStack,
    top = frames[0]
  if (!top) return null
  const request: UndoRequest = {
    current: structuredClone(c.source.checkpoint.content.restored.current),
    history: { stack: frames.map((x) => structuredClone(x.historyEntry)) },
  }
  const value = invokeFirstBallDomain('applyUndo', request)
  if (!isNonplayDefinition<AppliedValue>(value, 'Applied', 'undo_schema_v1'))
    throw new Error('正式取消計算が成立しません')
  const payload: UndoPayload = {
    formatVersion: 'native-undo-prefix-v1',
    artifactSha256: identity.sha256,
    expectedCheckpoint: structuredClone(c.source.checkpoint.ref),
    calculation: { request, response: { ok: true, value } },
  }
  const s = top.play.source,
    target: Target = { game: s.gameId, d4: s.generation, d1: safe(s.d1) }
  return nativeUndoDraft(c.game.id, c.game.current_d4, d5, payload, target)
}
/** Source6が提供する通常ボールだけ。数学nextCPは保存済みrefとは扱わない。 */
export function prepareBallAfterUndo(
  c: UndoProductContext,
  observations: Observations,
  playIdentity: PlayIdentity,
  nextCheckpointId: string,
): SyncEvent {
  assertContext(c)
  const cp = c.source.checkpoint,
    restored = cp.content.restored
  const request: NonplayRequest = {
    version: 'nonplay-continuation-v1',
    prefixRef: structuredClone(cp.ref),
    rules: structuredClone(restored.rules),
    t1: {
      eventKind: 'batting-result',
      resultId: 'batting-result.ball',
      pitchEventKind: 'pitch-event',
      before: structuredClone(restored.current),
    },
    source: structuredClone(c.source),
    playIdentity,
    nextCheckpoint: {
      id: nextCheckpointId,
      revision: String(BigInt(cp.ref.revision) + 1n),
      digest: '0'.repeat(64),
    },
    sourcePosition: {
      d1: c.game.next_position.d1,
      d2: c.game.next_position.d2,
      appliedWatermark: cp.content.d3,
    },
  }
  if (
    !isNonplayDefinition(
      request,
      'NonplayRequest',
      'lineup_play_prefix_schema_v1',
    )
  )
    throw new Error('次球の正式入力が不一致です')
  const value = invokeFirstBallDomain(
    'deriveLineupPlayPrefixWithContinuation',
    request,
  )
  const response = { ok: true as const, value }
  if (
    !isNonplayDefinition<NonplaySuccess>(
      response,
      'NonplaySuccess',
      'lineup_play_prefix_schema_v1',
    )
  )
    throw new Error('次球の正式計算が成立しません')
  const payload = {
    formatVersion: 'play-prefix-play-v3',
    observations: structuredClone(observations),
    participants: structuredClone(restored.participants),
    calculation: {
      formatVersion: 'nonplay-prefix-calculation-v1',
      artifactSha256: identity.sha256,
      request,
      response,
    },
  }
  if (
    !isNonplayDefinition<NonplayNormalV7>(
      payload,
      '$root',
      'lineup_play_prefix_payload_schema_v1',
    )
  )
    throw new Error('次球の正式wireが不一致です')
  return {
    fields: {
      V1: playIdentity.d5,
      V3: c.game.current_d4,
      V4: c.game.id,
      V5: '1',
      V6: safe(c.game.next_position.d2),
      V7: payload,
      V8: structuredClone(response.value.newHistoryEntry.difference),
    },
  }
}
