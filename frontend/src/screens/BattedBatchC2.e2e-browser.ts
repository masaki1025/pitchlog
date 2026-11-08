/** 同origin E2E専用の有限read bridge。製品の認可clientをそのまま使う。 */
import {
  readLineupPrefixGame,
  type LineupPrefixGame,
} from '../api/lineupPrefixGame'
import { readGameLifecycle, type GameLifecycleGame } from '../api/gameLifecycle'
import { apiDownload } from '../api/client'

export type C2ReadBridge = {
  repeated(id: string): Promise<LineupPrefixGame>
  ended(id: string): Promise<GameLifecycleGame>
  plays(
    id: string,
  ): Promise<{ bytes: number[]; length: number | null; sha256: string | null }>
}
declare global {
  interface Window {
    __battedC2ReadBridge: C2ReadBridge
  }
}
window.__battedC2ReadBridge = {
  async repeated(id) {
    const result = await readLineupPrefixGame(id)
    if (result.kind !== 'found') throw new Error('再送後の正規C2読取が不成立')
    return result.game
  },
  async ended(id) {
    const result = await readGameLifecycle(id, { limit: 25 })
    if (result.kind !== 'found') throw new Error('終了版の正規C2読取が不成立')
    return result.game
  },
  async plays(id) {
    const result = await apiDownload('/games/' + id + '/exports/plays.zip', {
      tenantBound: true,
    })
    return {
      bytes: Array.from(new Uint8Array(await result.blob.arrayBuffer())),
      length: result.contentLength,
      sha256: result.sha256,
    }
  },
}
