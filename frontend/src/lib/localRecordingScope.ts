import type { SingleWriterRevalidationContext } from './sync/singleWriter'

/** ローカル受理だけの境界。サーバー認証や記録権の成功値には使わない。 */
export type LocalAcceptanceBoundary = Readonly<{
  withinAcceptance<T>(
    heldGame: SingleWriterRevalidationContext,
    operation: () => Promise<T>,
  ): Promise<T>
}>
