// キューの状態表示の導出。
//
// 件数を画面で数えない。未送信の件数は索引集計(durableQueue の
// countUnsentSlots)の結果を受け取り、未送信の警告は clientDiscipline が返す
// 判定(appendUnderQueueDiscipline の warningThresholdReached)を受け取る。
// 画面側で全件を走査したり閾値の式を書き直したりすると、同じ値の導出が 2 つに
// なり、NFR-005(全件読み込み型の集計を書かない)にも当たる。
//
// 状態の名前は queueState(正本 7-2 の写し)の照合器を通してから使う。通知の
// 文面は syncNotices のカタログから作る(NFR-018)。
//
// B 区分の判定は U-F8 の仕事ではない。画面は受け取った通知を並べるだけである
// (docs/features/uf8-game-recording/design.md 4-2)。
import { DEFAULT_UNSENT_WARNING_THRESHOLD } from '../lib/sync/clientDiscipline'
import {
  QUEUE_STATES,
  queueStateId,
  type QueueActionRequiredLabel,
  type QueueStateId,
} from '../lib/sync/queueState'
import {
  createStoragePersistenceNotice,
  createSyncNotice,
  type SyncNoticeDescriptor,
} from '../lib/sync/syncNotices'

const UNSENT_STATE = queueStateId('未送信')
const ACTION_REQUIRED_STATE = queueStateId('要操作')
const EVACUATED_STATE = queueStateId('退避済み')
const SYNCED_STATE = queueStateId('同期済み')

/** 要操作の件数と、その下位ラベル。 */
export type ActionRequiredSummary = Readonly<{
  count: number
  labels: readonly QueueActionRequiredLabel['id'][]
}>

export type QueueStatusInput = Readonly<{
  /** 未送信の件数。索引集計の結果。まだ読めていなければ undefined。 */
  unsentCount: number | undefined
  /** 要操作の件数と下位ラベル。 */
  actionRequired?: ActionRequiredSummary
  /** 退避済みの件数。Q4 が未送信と別の件数としての併記を求める。 */
  evacuatedCount?: number
  /** 同期済みの件数。 */
  syncedCount?: number
  /**
   * 未送信が警告の閾値へ達したか。渡されればそれを使う。
   *
   * 渡されない場合は件数から導く —— `appendUnderQueueDiscipline` の判定は
   * 追記の瞬間にしか得られず、画面の再読込後や追記が無い間に警告が消えるため。
   * 閾値の値は `clientDiscipline` の既定を使い、二重に持たない。
   */
  unsentWarning?: boolean
  /**
   * 永続ストレージの要求が通ったか。まだ分からない場合は undefined とし、
   * 拒否されたことが分かっている場合にだけ警告を出す。
   */
  storagePersistenceGranted: boolean | undefined
  /** 経路から受け取った通知(B 区分を含む)。U-F8 は区分を判定しない。 */
  receivedNotices?: readonly SyncNoticeDescriptor[]
}>

/** 件数を正本の状態 ID で引けるようにした表示値。 */
export type QueueStatusView = Readonly<{
  countsByState: Readonly<Partial<Record<QueueStateId, number>>>
  /** 正本の状態のうち件数が供給されていないもの。黙って 0 と見せない。 */
  unsuppliedStates: readonly QueueStateId[]
  unsentCount: number | undefined
  actionRequiredCount: number
  actionRequiredLabels: readonly QueueActionRequiredLabel['id'][]
  evacuatedCount: number
  unsentWarning: boolean
  notices: readonly SyncNoticeDescriptor[]
}>

/**
 * キューの件数から画面に出す値を導く。
 *
 * Args:
 *     input: 件数と、永続ストレージの可否と、受け取った通知。
 *
 * Returns:
 *     状態ごとの件数・未送信の警告・並べる通知。
 */
export function deriveQueueStatus(input: QueueStatusInput): QueueStatusView {
  const actionRequiredCount = input.actionRequired?.count ?? 0
  const evacuatedCount = input.evacuatedCount ?? 0

  // 正本の状態集合を起点に組み立てる。状態が増えたら未供給として現れる。
  const supplied: Partial<Record<QueueStateId, number>> = {
    [ACTION_REQUIRED_STATE]: actionRequiredCount,
    [EVACUATED_STATE]: evacuatedCount,
    [UNSENT_STATE]: input.unsentCount,
    [SYNCED_STATE]: input.syncedCount,
  }
  const countsByState: Partial<Record<QueueStateId, number>> = {}
  const unsuppliedStates: QueueStateId[] = []
  for (const state of QUEUE_STATES) {
    const count = supplied[state.id]
    if (count === undefined) {
      unsuppliedStates.push(state.id)
      continue
    }
    countsByState[state.id] = count
  }

  const storageNotice =
    input.storagePersistenceGranted === undefined
      ? undefined
      : createStoragePersistenceNotice(input.storagePersistenceGranted)

  const notices: SyncNoticeDescriptor[] = []
  if (input.unsentCount !== undefined) {
    notices.push(createSyncNotice('Q4', { unsentCount: input.unsentCount }))
  }
  if (storageNotice) {
    notices.push(storageNotice)
  }
  notices.push(...(input.receivedNotices ?? []))

  return Object.freeze({
    countsByState: Object.freeze(countsByState),
    unsuppliedStates: Object.freeze(unsuppliedStates),
    unsentCount: input.unsentCount,
    actionRequiredCount,
    actionRequiredLabels: Object.freeze([
      ...(input.actionRequired?.labels ?? []),
    ]),
    evacuatedCount,
    unsentWarning:
      input.unsentWarning ??
      (input.unsentCount !== undefined &&
        input.unsentCount >= DEFAULT_UNSENT_WARNING_THRESHOLD),
    notices: Object.freeze(notices),
  })
}
