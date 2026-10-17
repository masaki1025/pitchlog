// 利用者の確定操作の封鎖。
//
// 毎球入力は取消可能な確定プレイであり、取消可能な操作には状態差分が要る
// (docs/design/sync-protocol.md:277・docs/features/sync-wire-schema/design.md:204)。
// 有効な状態差分の供給元は状況計算核(U-X1)で、U-X1 は凍結中である
// (PO 裁定 2026-10-16)。したがって第 1 期は配線までで、利用者の操作から
// 永続追記・送信へ進ませない。
//
// 【封鎖を外す前に決めること】docs/features/uf8-game-recording/design.md 6-2。
// 非所有タブの拒否は是正済み(GameScreenSingleWriter.ts)。残るのは排他の保持単位
// を「1 球ごと」にするか「記録セッションとして保持」するかの設計判断で、封鎖を
// 外す PR で決める。
//
// 【封鎖を外す箇所はこのファイルの PITCH_COMMIT_BLOCKED ただ 1 つである。】
// 計算核と接続する後続期では、この 1 行と、確定の経路を画面へつなぐ変更だけを
// 行えばよい。画面側に封鎖の判断を複製しない。

/** 封鎖の可否。解除はここだけで行う。 */
const PITCH_COMMIT_BLOCKED: boolean = true

/** 封鎖の理由。画面に出して、利用者が何を待っているのか分かるようにする。 */
export const PITCH_COMMIT_BLOCK_REASON =
  '状況計算核との接続待ちのため、この画面から 1 球を確定することはできません。入力は下書きのままで、保存も送信もされません。'

export type PitchCommitGate =
  | Readonly<{ committable: true }>
  | Readonly<{ committable: false; reason: string }>

/**
 * 利用者が 1 球を確定できるかを返す。
 *
 * Returns:
 *     確定できるかと、できない場合の理由。
 */
export function resolvePitchCommitGate(): PitchCommitGate {
  if (PITCH_COMMIT_BLOCKED) {
    return { committable: false, reason: PITCH_COMMIT_BLOCK_REASON }
  }
  return { committable: true }
}
