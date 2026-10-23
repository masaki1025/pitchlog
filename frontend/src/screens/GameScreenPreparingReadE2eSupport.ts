import { setupGameScreenE2eForMode } from './GameScreenE2eSupport'

/** 鍵を発行しないread専用の明示起動口。 */
export default async function setupPreparingRead(): Promise<
  () => Promise<void>
> {
  return setupGameScreenE2eForMode('preparing-read')
}
