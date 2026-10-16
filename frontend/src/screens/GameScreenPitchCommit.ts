// 確定の経路を 1 つの排他で包む。
//
// 順序は docs/features/uf8-game-recording/design.md 4-1' が正。
//   1. 単一書き手の排他を取る
//   2. D1 を採番し、端末の永続キューへ不可分に追記する
//   3. 追記が成立した時点を「操作の受理」とする
//   4. 画面に受理を表示する(表示は呼出元の仕事)
//   5. E-1 へ送る
//   6. ACK を分類し、A5 と拒否理由を既存スロットへ適用する
//
// 旧実装は再送にしか鍵を掛けておらず、初回の確定 POST が排他の外にあった
// (research.md の欠陥 1)。ここでは【排他を 1 回だけ取り、その中で追記から
// ACK の適用までを行う】ことでこれを是正する。
//
// 第 1 期では利用者からこの経路へ到達できない(GameScreenCommitGate が塞ぐ)。
// 合否はモックの状態差分と契約モックのサーバー相手の隔離試験でのみ判定する。
import type { EventKind } from '../lib/sync/eventKinds'
import {
  runAsSingleWriter,
  type SingleWriterInjections,
} from '../lib/sync/singleWriter'
import {
  postSyncEvents,
  type SyncEventSendResult,
} from '../api/client.syncEvents'
import {
  applyAckToSlot,
  type AckApplicationQueue,
  type AckApplicationResult,
  type AckResponse,
} from './GameScreenAckApplication'
import {
  appendPitchEventUnderLock,
  pitchAcceptanceNotStarted,
  type PitchAcceptanceInput,
  type PitchAcceptanceQueue,
  type PitchAcceptanceResult,
} from './GameScreenPitchAcceptance'

export type PitchCommitQueue = PitchAcceptanceQueue & AckApplicationQueue

export type PitchCommitInput = PitchAcceptanceInput &
  Readonly<{
    /** V12。不透明な値のまま運ぶ。 */
    recordingRightProof: unknown
    /** 受理する種別の集合。採否が未裁定の種別を既定で混ぜない。 */
    eventKinds: readonly EventKind[]
  }>

export type PitchCommitDependencies = Readonly<{
  queue: PitchCommitQueue
  singleWriterInjections?: SingleWriterInjections
  warningThreshold?: number
  /**
   * 応答から ACK を取り出す。応答の物理形を解釈する codec が製品側に無いため、
   * U-F8 で形を決め打ちせず呼出元から受け取る。ACK が無ければ undefined を返す。
   */
  readAck: (response: unknown) => AckResponse | undefined
}>

export const PITCH_COMMIT_SCOPE_MISMATCH = 'scope-mismatch' as const

export type PitchCommitResult =
  /** 前提が合わず、排他も取らずに止めた。 */
  | Readonly<{
      outcome: 'not-attempted'
      reason: typeof PITCH_COMMIT_SCOPE_MISMATCH
    }>
  | Readonly<{
      outcome: 'attempted'
      acceptance: PitchAcceptanceResult
      /** 受理できなければ送らないので undefined。 */
      send?: SyncEventSendResult
      /** 送れなければ、または ACK が無ければ undefined。 */
      ackApplication?: AckApplicationResult
    }>

/**
 * 1 球の確定を、採番・追記・受理・送信・ACK の適用まで 1 つの排他で行う。
 *
 * 排他を取れなければ追記も送信もしない。追記が成立しなければ送信しない。
 *
 * Args:
 *     input: 確定するイベントと、その範囲。
 *     dependencies: 注入するキュー・単一書き手の前提・ACK の取り出し。
 *
 * Returns:
 *     受理の結果と、到達した段までの結果。
 */
export async function commitPitchEvent(
  input: PitchCommitInput,
  dependencies: PitchCommitDependencies,
): Promise<PitchCommitResult> {
  // path の試合と排他の単位が食い違うと、別の試合のキューへ書きうる。
  if (!Object.is(input.scope.game, input.gameIdentifier)) {
    return { outcome: 'not-attempted', reason: PITCH_COMMIT_SCOPE_MISMATCH }
  }

  const { queue } = dependencies

  const started = await runAsSingleWriter<PitchCommitResult>(
    { gameIdentifier: input.gameIdentifier },
    async () => {
      const acceptance = await appendPitchEventUnderLock(
        input,
        queue,
        dependencies.warningThreshold,
      )
      if (acceptance.outcome !== 'accepted') {
        // 追記が成立していなければ送らない(要件書 :329 の E0)。
        return { outcome: 'attempted', acceptance }
      }

      const send = await postSyncEvents({
        gameId: input.gameIdentifier,
        recordingRightProof: input.recordingRightProof,
        slots: [acceptance.slot],
        eventKinds: input.eventKinds,
      })
      if (!send.sent) {
        // ACK が返らないのでスロットは未送信のまま(sync-protocol.md:764)。
        return { outcome: 'attempted', acceptance, send }
      }

      let ack: AckResponse | undefined
      try {
        ack = dependencies.readAck(send.response)
      } catch {
        ack = undefined
      }

      const ackApplication = await applyAckToSlot(
        { scope: input.scope, d1: acceptance.slot.d1, ack },
        queue,
      )
      return { outcome: 'attempted', acceptance, send, ackApplication }
    },
    dependencies.singleWriterInjections,
  )

  if (!started.recordingStarted) {
    return {
      outcome: 'attempted',
      acceptance: pitchAcceptanceNotStarted(started.reason),
    }
  }
  return started.value
}
