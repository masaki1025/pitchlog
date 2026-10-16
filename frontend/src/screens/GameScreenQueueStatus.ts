// キューの状態表示の導出。
//
// 未同期の判定を画面側で作り直さない。状態の集合は queueState(正本 7-2 の写し)
// から取り、個々の状態 ID は queueStateId で正本に照合してから使う。通知の文面も
// syncNotices のカタログから作る(NFR-018)。
//
// B 区分の判定は U-F8 の仕事ではない。画面は受け取った通知を並べるだけである
// (docs/features/uf8-game-recording/design.md 4-2)。
import { DEFAULT_UNSENT_WARNING_THRESHOLD } from '../lib/sync/clientDiscipline'
import type { DurableQueueSlot } from '../lib/sync/durableQueue'
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

/** 表示に要るスロットの面だけを受け取る。 */
export type QueueStatusSlot = Pick<
  DurableQueueSlot,
  'state' | 'actionRequiredLabel'
>

export type QueueStatusInput = Readonly<{
  slots: readonly QueueStatusSlot[]
  /**
   * 永続ストレージの要求が通ったか。まだ分からない場合は undefined とし、
   * 拒否されたことが分かっている場合にだけ警告を出す。
   */
  storagePersistenceGranted: boolean | undefined
  /** 経路から受け取った通知(B 区分を含む)。U-F8 は区分を判定しない。 */
  receivedNotices?: readonly SyncNoticeDescriptor[]
  unsentWarningThreshold?: number
}>

export type QueueStatusView = Readonly<{
  countsByState: Readonly<Record<QueueStateId, number>>
  /** 正本の状態集合に無い値の件数。黙って落とさないために数える。 */
  unrecognizedStateCount: number
  unsentCount: number
  actionRequiredCount: number
  actionRequiredLabels: readonly QueueActionRequiredLabel['id'][]
  unsentWarning: boolean
  notices: readonly SyncNoticeDescriptor[]
}>

function emptyCounts(): Record<QueueStateId, number> {
  const counts = {} as Record<QueueStateId, number>
  for (const state of QUEUE_STATES) {
    counts[state.id] = 0
  }
  return counts
}

/**
 * キューのスロットから画面に出す値を導く。
 *
 * Args:
 *     input: スロットの状態と、永続ストレージの可否と、受け取った通知。
 *
 * Returns:
 *     状態ごとの件数・未送信の警告・並べる通知。
 */
export function deriveQueueStatus(input: QueueStatusInput): QueueStatusView {
  const countsByState = emptyCounts()
  const actionRequiredLabels: QueueActionRequiredLabel['id'][] = []
  let unrecognizedStateCount = 0

  for (const slot of input.slots) {
    if (!Object.hasOwn(countsByState, slot.state)) {
      unrecognizedStateCount += 1
      continue
    }
    countsByState[slot.state] += 1
    if (slot.state === ACTION_REQUIRED_STATE && slot.actionRequiredLabel) {
      actionRequiredLabels.push(slot.actionRequiredLabel)
    }
  }

  const unsentCount = countsByState[UNSENT_STATE]
  const threshold =
    input.unsentWarningThreshold ?? DEFAULT_UNSENT_WARNING_THRESHOLD

  const storageNotice =
    input.storagePersistenceGranted === undefined
      ? undefined
      : createStoragePersistenceNotice(input.storagePersistenceGranted)
  const notices: SyncNoticeDescriptor[] = [
    createSyncNotice('Q4', { unsentCount }),
  ]
  if (storageNotice) {
    notices.push(storageNotice)
  }
  notices.push(...(input.receivedNotices ?? []))

  return Object.freeze({
    countsByState: Object.freeze(countsByState),
    unrecognizedStateCount,
    unsentCount,
    actionRequiredCount: countsByState[ACTION_REQUIRED_STATE],
    actionRequiredLabels: Object.freeze(actionRequiredLabels),
    unsentWarning: unsentCount >= threshold,
    notices: Object.freeze(notices),
  })
}
