// 非所有タブの確定を、待たずに拒む。
//
// Web Locks の既定はブロッキングで、前の書き手が解放した瞬間にコールバックが
// 走る。そのままでは「押したときは無反応、数十秒後に勝手に 1 球入る」ことになり、
// 待機中の入力を受理しない契約(要件書 :332 の E2・:333 の E3・
// docs/design/sync-protocol.md:1690)を満たせない。
//
// `runAsSingleWriter` は `lockManager` を注入点として公開しており、鍵が取れない
// ときにコールバックが `null` を受けると追記せずに `LOCK_REQUEST_FAILED` で戻る
// (singleWriter.ts)。したがって `ifAvailable` を使う管理機構を呼出側から渡せば、
// lib/sync を変更せずに契約を満たせる。
import {
  rejectNonOwnerInput,
  SINGLE_WRITER_START_FAILURE,
  type ExclusiveLockManager,
  type NonOwnerInputRejection,
  type SingleWriterInjections,
  type SingleWriterStartFailure,
} from '../lib/sync/singleWriter'

/** Web Locks の `request` のうち、本モジュールが使う面。 */
type LockRequestWithOptions = (
  name: string,
  options: { ifAvailable: true },
  callback: (lock: unknown) => unknown,
) => Promise<unknown>

/**
 * 鍵が空いていなければ待たずに諦める管理機構を作る。
 *
 * Args:
 *     request: Web Locks の `request`。既定は `navigator.locks.request`。
 *
 * Returns:
 *     待たない管理機構。鍵が取れなければコールバックへ null を渡す。
 */
export function createNonBlockingLockManager(
  request?: LockRequestWithOptions,
): ExclusiveLockManager | undefined {
  const resolved =
    request ??
    (typeof navigator === 'undefined' || !navigator.locks
      ? undefined
      : (navigator.locks.request.bind(
          navigator.locks,
        ) as unknown as LockRequestWithOptions))
  if (!resolved) {
    return undefined
  }

  return {
    request: async (name, callback) =>
      (await resolved(name, { ifAvailable: true }, (lock) =>
        callback(lock),
      )) as never,
  }
}

/**
 * 単一書き手の注入を、待たない管理機構が既定になるよう整える。
 *
 * `runAsSingleWriter` は `lockManager` を省略するとブラウザ既定(ブロッキング)
 * を使う。呼出元が渡し忘れると、待機側の確定が前の書き手の解放後に実行され、
 * `sync-protocol.md:1690` の「キューへ追記せず D1 を消費しない」に反する。
 * 既定の差し替えを呼出元の記憶に任せず、ここで機構として固定する。
 *
 * Args:
 *     injections: 呼出元が渡した注入(省略可)。
 *
 * Returns:
 *     `lockManager` が待たない管理機構に揃った注入。
 */
export function withNonBlockingSingleWriter(
  injections: SingleWriterInjections = {},
): SingleWriterInjections {
  if (injections.lockManager !== undefined) {
    return injections
  }
  return { ...injections, lockManager: createNonBlockingLockManager() ?? null }
}

/**
 * 単一書き手を始められなかった理由が「他のタブが記録中」かを判定する。
 *
 * 待たない管理機構の下では、鍵が取れなかった場合に `LOCK_REQUEST_FAILED` が返る。
 *
 * Args:
 *     reason: `runAsSingleWriter` が返した理由。
 *
 * Returns:
 *     非所有として扱うなら、その旨の記述子(通知 `Q2-b` を含む)。
 */
export function describeNonOwnerInput(
  reason: SingleWriterStartFailure,
): NonOwnerInputRejection | undefined {
  if (reason !== SINGLE_WRITER_START_FAILURE.LOCK_REQUEST_FAILED) {
    return undefined
  }
  // 通知と文面は lib/sync の既存の成果から作る(U-F8 で作らない)。
  return rejectNonOwnerInput()
}
