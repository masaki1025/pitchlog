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
import type { SyncRequestCredentials } from '../api/client'
import type { DurableQueueSlot } from '../lib/sync/durableQueue'
import type { EventKind } from '../lib/sync/eventKinds'
import { queueStateId } from '../lib/sync/queueState'
import {
  runAsSingleWriter,
  type NonOwnerInputRejection,
  type SingleWriterInjections,
} from '../lib/sync/singleWriter'
import {
  postSyncEvents,
  type SyncEventSendResult,
  type SyncEventSendRequest,
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
  pitchScopeMatchesLock,
  type PitchAcceptanceInput,
  type PitchAcceptanceQueue,
  type PitchAcceptanceResult,
} from './GameScreenPitchAcceptance'
import {
  describeNonOwnerInput,
  withNonBlockingSingleWriter,
} from './GameScreenSingleWriter'

const UNSENT_STATE = queueStateId('未送信')

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
  /** 追記後・HTTP前に耐久保存を完了し、同じ要求の実資格だけを返す。 */
  prepareSend?: (
    request: SyncEventSendRequest,
  ) => Promise<SyncRequestCredentials>
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
      /** 端末の送信準備が成立しなかった。HTTP未送信であり結果不明ではない。 */
      sendPreparation?: Readonly<{ outcome: 'failed' }>
      /** 送れなければ、または ACK が無ければ undefined。 */
      ackApplication?: AckApplicationResult
      /**
       * 排他を抜けた時点のスロット。ACK を適用したならその結果、していなければ
       * 追記直後のもの。画面はこれを読む(acceptance.slot は追記直後の時点で、
       * 後から書き戻すと古い状態で上書きする)。
       */
      latestSlot?: DurableQueueSlot
      /** 他のタブが記録中で、この端末からは記録できないときの記述子。 */
      nonOwner?: NonOwnerInputRejection
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
  // 判定は受理側と同じ述語を使う(2 箇所で別々に書かない)。
  if (!pitchScopeMatchesLock(input)) {
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
      if (!Object.is(acceptance.slot.state, UNSENT_STATE)) {
        // 照合で見つけたスロットが既に遷移済みなら、送り直さない。
        return {
          outcome: 'attempted',
          acceptance,
          latestSlot: acceptance.slot,
        }
      }

      const request: SyncEventSendRequest = {
        gameId: input.gameIdentifier,
        recordingRightProof: input.recordingRightProof,
        slots: [acceptance.slot],
        eventKinds: input.eventKinds,
      }
      let syncCredentials: SyncRequestCredentials | undefined
      if (dependencies.prepareSend) {
        try {
          syncCredentials = await dependencies.prepareSend(request)
        } catch {
          return {
            outcome: 'attempted',
            acceptance,
            sendPreparation: { outcome: 'failed' },
            latestSlot: acceptance.slot,
          }
        }
      }
      const send = await postSyncEvents({
        ...request,
        ...(syncCredentials === undefined ? {} : { syncCredentials }),
      })
      if (!send.sent) {
        // ACK が返らないのでスロットは未送信のまま(sync-protocol.md:764)。
        return {
          outcome: 'attempted',
          acceptance,
          send,
          latestSlot: acceptance.slot,
        }
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
      return {
        outcome: 'attempted',
        acceptance,
        send,
        ackApplication,
        latestSlot:
          ackApplication.outcome === 'applied'
            ? ackApplication.slot
            : acceptance.slot,
      }
    },
    withNonBlockingSingleWriter(dependencies.singleWriterInjections),
  )

  if (!started.recordingStarted) {
    return {
      outcome: 'attempted',
      acceptance: pitchAcceptanceNotStarted(started.reason),
      // 待たない管理機構の下では、鍵が取れないことが「他のタブが記録中」を
      // 意味する。記録できないことと導線を利用者へ示すための記述子を載せる。
      nonOwner: describeNonOwnerInput(started.reason),
    }
  }
  return started.value
}
