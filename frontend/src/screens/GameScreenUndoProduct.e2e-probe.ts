/** E2E専用の読取観測。製品state・認可・資格・保存結果を変更しない。 */
import {
  isNativeUndoGame,
  completeUndoSource,
  readCompleteUndoGame,
} from '../api/nativeUndoGame'
import { exactPlayObject } from '../api/terminalPitchWire'
import { apiRequest } from '../api/client'
import { isLineupPrefixGame } from '../api/lineupPrefixGame'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'

const outputId = 'pitchlog-undo-read-probe'
document.getElementById(outputId)?.remove()
const output = document.createElement('output')
output.id = outputId
output.hidden = true
document.body.append(output)
document.addEventListener(
  'pitchlog-undo-read-probe',
  async (event) => {
    if (!(event instanceof CustomEvent)) return
    const detail: unknown = event.detail
    if (
      !exactPlayObject(detail, ['packet', 'requestId']) ||
      typeof detail.requestId !== 'string' ||
      detail.requestId.length > 128
    )
      return
    const packet = detail.packet
    const bindings: Record<string, boolean> = {}
    const checks = {
      bindings,
      shape: isNativeUndoGame(packet),
      completeSource: false,
      completeRead: false,
      failure: 'none',
    }
    if (isNativeUndoGame(packet)) {
      try {
        await completeUndoSource(
          packet,
          packet.checkpoint.content.scope.tenantId,
        )
        checks.completeSource = true
      } catch {
        checks.completeSource = false
      }
      try {
        await readCompleteUndoGame(
          packet.id,
          packet.checkpoint.content.scope.tenantId,
        )
        checks.completeRead = true
      } catch (error) {
        const reasons = new Map([
          ['派生CPと保存原本が一致しません', 'standard-binding'],
          ['実保存CPが取得中に変わりました', 'native-binding'],
          ['取消用の保存原本を確認できません', 'native-read'],
        ])
        checks.failure =
          error instanceof Error
            ? (reasons.get(error.message) ?? 'other')
            : 'other'
      }
    }
    if (isNativeUndoGame(packet)) {
      try {
        const standard = await apiRequest<unknown>(
          'GET',
          `/games/${packet.id}/started`,
          {
            tenantBound: true,
            query: { projection: 'play-prefix-v3', limit: 1 },
          },
        )
        bindings.standardShape = isLineupPrefixGame(standard)
        if (isLineupPrefixGame(standard)) {
          const content = packet.checkpoint.content
          Object.assign(bindings, {
            tenant: standard.prefix_ref.tenantId === content.scope.tenantId,
            game: standard.id === packet.id,
            generation: standard.current_d4 === packet.current_d4,
            checkpointId:
              standard.prefix_ref.checkpoint.id === packet.checkpoint.ref.id,
            checkpointRevision:
              standard.prefix_ref.checkpoint.revision ===
              packet.checkpoint.ref.revision,
            nextD1: standard.next_position.d1 === packet.next_position.d1,
            recovery:
              standard.recovery_generation === packet.recovery_generation,
            after: sameOrdinaryWire(standard.after, packet.after),
            rules: sameOrdinaryWire(standard.rules, content.restored.rules),
            lineup: sameOrdinaryWire(standard.lineup, content.restored.lineup),
            participants: sameOrdinaryWire(
              standard.participants,
              content.restored.participants,
            ),
            runners: sameOrdinaryWire(
              standard.runners,
              content.restored.runners,
            ),
            rosterDigest:
              standard.roster_digest === content.restored.rosterDigest,
            historyVersion:
              standard.prefix_ref.historyVersion === content.historyVersion,
            storageHistoryEpoch:
              standard.storage_anchor?.history_epoch ===
              content.storageHistoryEpoch,
          })
        }
      } catch {
        bindings.standardRead = false
      }
    }
    output.textContent = JSON.stringify(checks)
    output.dataset.requestId = detail.requestId
  },
  { once: true },
)
