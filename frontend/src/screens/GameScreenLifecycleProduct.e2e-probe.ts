/** 実E2EのDTO検査だけを観測する。認証/保存/製品状態は変更しない。 */
import { isGameLifecycleGame, isGameLifecycleMeta } from '../api/gameLifecycle'
import { isNativeUndoGame } from '../api/nativeUndoGame'
import {
  isStartedGameMetadata,
  isStartedGameTimestamp,
} from '../api/startedGame'
import { isNonplayDefinition } from '../api/nonplayContract'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import { isOrdinaryAppendPolicy } from '../api/ordinaryAppendPolicy'
const output = document.createElement('output')
output.id = 'pitchlog-lifecycle-dto-probe'
output.hidden = true
document.body.append(output)
document.addEventListener('pitchlog-lifecycle-dto-probe', (event) => {
  if (!(event instanceof CustomEvent)) return
  const packet: unknown = event.detail
  if (packet === null || typeof packet !== 'object') return
  const { status, lifecycle, ...prefix } = packet as Record<string, unknown>
  const row = packet as Record<string, unknown>
  const cp = row.checkpoint as
    | {
        content?: {
          restored?: { current?: unknown }
          d3?: string
          activeDepth?: string
          scope?: { gameId?: string; generation?: string }
        }
      }
    | undefined
  const next = row.next_position as { d1?: string; d2?: string } | undefined
  const page = row.page as
    { items?: unknown[]; next_cursor?: unknown } | undefined
  output.textContent = JSON.stringify({
    base: isStartedGameMetadata({ ...prefix, status: 'in_progress' }),
    checkpoint: isNonplayDefinition(row.checkpoint, 'Checkpoint'),
    sameAfter: sameOrdinaryWire(row.after, cp?.content?.restored?.current),
    appendPolicy: isOrdinaryAppendPolicy(row.append_policy),
    timestamp: isStartedGameTimestamp(row.last_saved_at),
    frames: page?.items?.every((x) => isNonplayDefinition(x, 'ActiveFrame')),
    gameScope: cp?.content?.scope?.gameId === row.id,
    generationScope: cp?.content?.scope?.generation === row.current_d4,
    nextD1:
      next?.d1 !== undefined &&
      cp?.content?.d3 !== undefined &&
      BigInt(next.d1) === BigInt(cp.content.d3) + 1n,
    depth:
      cp?.content?.activeDepth !== undefined &&
      BigInt(page?.items?.length ?? -1) <= BigInt(cp.content.activeDepth),
    full: isGameLifecycleGame(packet),
    metadata:
      (status === 'finished' || status === 'in_progress') &&
      isGameLifecycleMeta(lifecycle, status),
    prefix: isNativeUndoGame({ ...prefix, status: 'in_progress' }),
  })
})
