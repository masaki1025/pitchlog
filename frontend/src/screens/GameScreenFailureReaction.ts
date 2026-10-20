// E5 の故障シナリオに対する画面側の反応。
//
// 期待値そのものは契約資産(tests/fixtures/sync-protocol-failures/)が正で、
// 構造の検査は failureScenarioContract が行う。本モジュールは、契約が置く
// クライアント側の観測値(queue / d1 / lock / acceptanceDisplay /
// reinputAvailability)から、画面が何を出すかだけを導く。
//
// すべて fail-closed にする。観測値が無い・読めない場合は「受理成功を表示しない」
// 側へ倒す(docs/design/sync-protocol.md の E5 の 3 行はいずれも、受理成功を
// 表示しないことを求めている)。
import type { FailureScenarioObservation } from '../lib/sync/failureScenarioContract'
import { SYNC_NOTICE_IDS, type SyncNoticeId } from '../lib/sync/syncNotices'

export type FailureReaction = Readonly<{
  /** 受理成功として見せてよいか。 */
  showsAcceptance: boolean
  /** 再検証を経て記録を再開した状態か。 */
  recordingResumed: boolean
  /** 再入力の導線を出すか。 */
  offersReinput: boolean
  /** 利用者へ再入力を要求するか。 */
  requiresReinput: boolean
  /** 同じ次番号で再試行できるか。 */
  retriesWithSameNextD1: boolean
  /** 記録できない旨として出す通知。 */
  blockedNoticeId: SyncNoticeId | undefined
}>

function recordOf(fields: Readonly<Record<string, unknown>>, key: string) {
  const value = fields[key]
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return undefined
  }
  return value as Readonly<Record<string, unknown>>
}

function isTrue(
  source: Readonly<Record<string, unknown>> | undefined,
  key: string,
): boolean {
  return source?.[key] === true
}

function noticeIdOf(
  source: Readonly<Record<string, unknown>> | undefined,
): SyncNoticeId | undefined {
  const candidate = source?.noticeId
  return SYNC_NOTICE_IDS.find((id) => Object.is(id, candidate))
}

/**
 * 故障シナリオの観測値から、画面が出すものを導く。
 *
 * Args:
 *     observation: 契約資産の観測点 1 つ分。
 *
 * Returns:
 *     画面の反応。
 */
export function deriveFailureReaction(
  observation: FailureScenarioObservation,
): FailureReaction {
  const fields = observation.fields
  const acceptanceDisplay = recordOf(fields, 'acceptanceDisplay')
  const reinputAvailability = recordOf(fields, 'reinputAvailability')

  return Object.freeze({
    showsAcceptance:
      isTrue(acceptanceDisplay, 'shownAsAccepted') ||
      isTrue(acceptanceDisplay, 'waitingInputShownAsAccepted'),
    recordingResumed: isTrue(
      acceptanceDisplay,
      'recordingResumedAfterRevalidation',
    ),
    offersReinput:
      isTrue(reinputAvailability, 'possible') ||
      isTrue(reinputAvailability, 'afterLockAcquisition'),
    requiresReinput: isTrue(reinputAvailability, 'required'),
    retriesWithSameNextD1: isTrue(reinputAvailability, 'retryWithSameNextD1'),
    blockedNoticeId: noticeIdOf(acceptanceDisplay),
  })
}
