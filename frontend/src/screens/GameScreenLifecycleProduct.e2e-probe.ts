/** 実E2EのDTO検査だけを観測する。認証/保存/製品状態は変更しない。 */
import { isGameLifecycleGame, isGameLifecycleMeta } from '../api/gameLifecycle'
import { isNativeUndoGame } from '../api/nativeUndoGame'
const output = document.createElement('output')
output.id = 'pitchlog-lifecycle-dto-probe'
output.hidden = true
document.body.append(output)
document.addEventListener('pitchlog-lifecycle-dto-probe', (event) => {
  if (!(event instanceof CustomEvent)) return
  const packet: unknown = event.detail
  if (packet === null || typeof packet !== 'object') return
  const { status, lifecycle, ...prefix } = packet as Record<string, unknown>
  output.textContent = JSON.stringify({
    full: isGameLifecycleGame(packet),
    metadata:
      (status === 'finished' || status === 'in_progress') &&
      isGameLifecycleMeta(lifecycle, status),
    prefix: isNativeUndoGame({ ...prefix, status: 'in_progress' }),
  })
})
