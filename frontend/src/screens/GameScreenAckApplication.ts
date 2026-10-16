// ACK の分類と、A5・拒否理由の既存スロットへの適用の配線。
//
// 分類も遷移も U-F8 では決めない。ACK の読み取りは ackAdapter(内部で
// parseAckBoundaryResult を使う)に、遷移は durableQueue の A5 永続境界
// (内部で queueTransition の単一実装を使う)に委ねる。本モジュールは順序を
// 組むだけである(NFR-018)。
//
// B3(恒久的な内容拒否)は「送信が失敗したこと」ではなく「拒否を含む ACK が
// 返ったこと」である(docs/design/sync-protocol.md:764)。ACK が返らない場合は
// 未送信のままで、自動再送の対象として残す。
import { createAckAdapterInjections } from '../lib/sync/ackAdapter'
import type {
  DurableQueue,
  DurableQueueScope,
  DurableQueueSlot,
} from '../lib/sync/durableQueue'

export type AckApplicationQueue = Pick<
  DurableQueue,
  'prepareA5Transition' | 'persistA5Transition'
>

/** サーバーが返した ACK。中身は解釈せず ackAdapter へ渡す。 */
export type AckResponse = Readonly<{
  envelope: unknown
  boundaryResult: unknown
  b3Rejection?: unknown
}>

export type AckApplicationInput = Readonly<{
  scope: DurableQueueScope
  d1: number
  /** ACK が返らなかった場合は渡さない。 */
  ack?: AckResponse
}>

export const ACK_APPLICATION_REASON = {
  /** そもそも ACK が返らなかった。 */
  NO_ACK_RECEIVED: 'no-ack-received',
  /** ACK が返らない境界結果、または解釈できない ACK だった。 */
  ACK_NOT_INTERPRETABLE: 'ack-not-interpretable',
  /** 対象のスロットが未送信で見つからない(既に遷移済みを含む)。 */
  NO_TARGET_SLOT: 'no-target-slot',
  /** 遷移の条件を満たさず、状態を変えなかった。 */
  NOT_TRANSITIONED: 'not-transitioned',
  /** 永続化に失敗した。 */
  PERSISTENCE_FAILED: 'persistence-failed',
} as const

export type AckApplicationReason =
  (typeof ACK_APPLICATION_REASON)[keyof typeof ACK_APPLICATION_REASON]

export type AckApplicationResult =
  | Readonly<{ outcome: 'applied'; slot: DurableQueueSlot }>
  | Readonly<{ outcome: 'not-applied'; reason: AckApplicationReason }>

/**
 * ACK を既存スロットへ適用する。
 *
 * ACK が返らない場合・解釈できない場合は何も変えない(未送信のまま)。
 *
 * Args:
 *     input: 対象のスロットと ACK。
 *     queue: 適用先のキュー。
 *
 * Returns:
 *     適用の可否と、適用後のスロットまたは理由。
 */
export async function applyAckToSlot(
  input: AckApplicationInput,
  queue: AckApplicationQueue,
): Promise<AckApplicationResult> {
  if (!input.ack) {
    return {
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.NO_ACK_RECEIVED,
    }
  }

  let injections
  try {
    injections = createAckAdapterInjections({ d1: input.ack })
  } catch {
    // ACK が返らない境界結果・未知の境界結果・読めない封筒はここで落ちる。
    return {
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.ACK_NOT_INTERPRETABLE,
    }
  }

  let preparation
  try {
    preparation = await queue.prepareA5Transition(
      input.scope,
      input.d1,
      injections,
    )
  } catch {
    return {
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.NO_TARGET_SLOT,
    }
  }
  if (!preparation) {
    return {
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.NO_TARGET_SLOT,
    }
  }

  let slot: DurableQueueSlot | undefined
  try {
    slot = await queue.persistA5Transition(preparation)
  } catch {
    return {
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.PERSISTENCE_FAILED,
    }
  }
  if (!slot) {
    return {
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.NOT_TRANSITIONED,
    }
  }
  return { outcome: 'applied', slot }
}
