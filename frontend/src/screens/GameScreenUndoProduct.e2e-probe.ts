/** E2E専用の読取観測。製品state・認可・資格・保存結果を変更しない。 */
import { isNativeUndoGame, completeUndoSource } from '../api/nativeUndoGame'
import { exactPlayObject } from '../api/terminalPitchWire'

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
    const checks = { shape: isNativeUndoGame(packet), completeSource: false }
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
    }
    output.textContent = JSON.stringify(checks)
    output.dataset.requestId = detail.requestId
  },
  { once: true },
)
