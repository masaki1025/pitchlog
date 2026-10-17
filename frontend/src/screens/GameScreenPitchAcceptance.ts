// 1 球の採番・永続追記・受理の配線。
//
// 順序は docs/features/uf8-game-recording/design.md 4-1' が正。
//   1. 単一書き手の排他を取る
//   2. D1 を採番し、端末の永続キューへ不可分に追記する(採番は durableQueue が
//      追記トランザクションの中で行う)
//   3. 追記が成立した時点を「操作の受理」とする(要件書 :329 の E0・
//      docs/design/sync-protocol.md:1095 の Q1)
//
// 本モジュールはキューを開かない。キューは呼出元が注入する。第 1 期の合否は
// モックの状態差分を注入した隔離試験でのみ判定し、実運用のキューへモック差分を
// 積まない(plan.md ステップ 3)。
import { appendUnderQueueDiscipline } from '../lib/sync/clientDiscipline'
import type {
  DurableQueue,
  DurableQueueAppend,
  DurableQueueScope,
  DurableQueueSlot,
} from '../lib/sync/durableQueue'
import {
  runAsSingleWriter,
  type SingleWriterInjections,
  type SingleWriterStartFailure,
} from '../lib/sync/singleWriter'
import type { SyncEvent } from '../lib/sync/syncEvent'

/** 本モジュールが使うキューの面。読取りは成否の照合にだけ使う。 */
export type PitchAcceptanceQueue = Pick<
  DurableQueue,
  'prepareAppend' | 'append' | 'countUnsentSlots' | 'readSlot' | 'readNextD1'
>

export type PitchAcceptanceInput = Readonly<{
  /** 排他の単位。 */
  gameIdentifier: string
  scope: DurableQueueScope
  d5: unknown
  version: unknown
  /** 下書き(ステップ 1)に状態差分を足したイベント。D1 はまだ持たない。 */
  event: SyncEvent
}>

export type PitchAcceptanceDependencies = Readonly<{
  queue: PitchAcceptanceQueue
  singleWriterInjections?: SingleWriterInjections
  warningThreshold?: number
}>

export const PITCH_ACCEPTANCE_FAILURE = {
  /** 単一書き手の排他を取れなかった。追記していない。 */
  SINGLE_WRITER_NOT_STARTED: 'single-writer-not-started',
  /** 追記が成立していないことを読取りで確かめた。 */
  APPEND_FAILED: 'append-failed',
  /** 追記の成否を確かめられなかった。 */
  RECONCILIATION_FAILED: 'reconciliation-failed',
  /** 排他の単位とキューの試合が食い違う。別の試合のキューへ書きうる。 */
  SCOPE_MISMATCH: 'scope-mismatch',
} as const

export type PitchAcceptanceFailure =
  (typeof PITCH_ACCEPTANCE_FAILURE)[keyof typeof PITCH_ACCEPTANCE_FAILURE]

/**
 * 受理の結果。
 *
 * スロットを持つのは `accepted` だけである。追記が成立していない場合と、成否を
 * 確かめられなかった場合に受理を表示できないよう、型で分けている
 * (NFR-007 / E4・要件書 :880)。
 */
export type PitchAcceptanceResult =
  | Readonly<{
      outcome: 'accepted'
      slot: DurableQueueSlot
      /** 未送信件数。読取りが失敗した場合は undefined(追記は成立している)。 */
      unsentCount: number | undefined
      warningThresholdReached: boolean | undefined
    }>
  | Readonly<{
      outcome: 'not-accepted'
      reason: PitchAcceptanceFailure
      singleWriterReason?: SingleWriterStartFailure
    }>
  | Readonly<{
      outcome: 'undetermined'
      reason: PitchAcceptanceFailure
    }>

/** 複製をまたいでも同一性を判定できる値か(プリミティブに限る)。 */
function isComparableIdentifier(value: unknown): boolean {
  return (
    value === null || (typeof value !== 'object' && typeof value !== 'function')
  )
}

async function reconcileAppend(
  queue: PitchAcceptanceQueue,
  input: PitchAcceptanceInput,
  expectedD1: number | undefined,
): Promise<PitchAcceptanceResult> {
  if (expectedD1 === undefined) {
    return {
      outcome: 'undetermined',
      reason: PITCH_ACCEPTANCE_FAILURE.RECONCILIATION_FAILED,
    }
  }

  let slot: DurableQueueSlot | undefined
  try {
    slot = await queue.readSlot(input.scope, expectedD1)
  } catch {
    return {
      outcome: 'undetermined',
      reason: PITCH_ACCEPTANCE_FAILURE.RECONCILIATION_FAILED,
    }
  }

  if (slot === undefined) {
    // その D1 に何も書かれていない。追記は成立していない。
    return {
      outcome: 'not-accepted',
      reason: PITCH_ACCEPTANCE_FAILURE.APPEND_FAILED,
    }
  }

  // D5 は不透明な識別値で、物理形は正本が決めていない(論点 17)。キューは
  // structuredClone で保存するので、非プリミティブだと Object.is は必ず false に
  // なり、成立した追記を「不受理」と誤判定しうる。判定できない場合は不明へ倒す。
  if (!isComparableIdentifier(slot.d5) || !isComparableIdentifier(input.d5)) {
    return {
      outcome: 'undetermined',
      reason: PITCH_ACCEPTANCE_FAILURE.RECONCILIATION_FAILED,
    }
  }
  if (Object.is(slot.d5, input.d5)) {
    return {
      outcome: 'accepted',
      slot,
      unsentCount: undefined,
      warningThresholdReached: undefined,
    }
  }
  return {
    outcome: 'not-accepted',
    reason: PITCH_ACCEPTANCE_FAILURE.APPEND_FAILED,
  }
}

/**
 * 排他の単位とキューの試合が一致しているか。
 *
 * 食い違うと、試合 A のロックしか持たずに試合 B のキューへ追記しうる。
 *
 * Args:
 *     input: 追記の入力。
 *
 * Returns:
 *     一致していれば true。
 */
export function pitchScopeMatchesLock(input: PitchAcceptanceInput): boolean {
  return Object.is(input.scope.game, input.gameIdentifier)
}

/**
 * 永続キューへ追記し、追記の成立をもって受理とする(排他は取らない)。
 *
 * 呼出元が単一書き手の排他の中で呼ぶこと。追記から送信・ACK の適用までを 1 つの
 * 排他で包むため、排他の取得をこの関数から分けてある
 * (docs/features/uf8-game-recording/design.md 4-1')。
 *
 * 追記の成否を戻り値だけで決めない —— `appendUnderQueueDiscipline` は追記が
 * 成功した後に未送信件数を別途読むため(clientDiscipline.ts:34)、件数の読取り
 * だけが失敗しても追記は成立している。その場合は追記前に読んだ次の D1 で
 * スロットを読み直して照合する。
 *
 * Args:
 *     input: 追記するイベントと、その範囲。
 *     queue: 追記先のキュー。
 *     warningThreshold: 未送信件数の警告の閾値。
 *
 * Returns:
 *     受理・不受理・不明のいずれか。スロットを持つのは受理だけである。
 */
export async function appendPitchEventUnderLock(
  input: PitchAcceptanceInput,
  queue: PitchAcceptanceQueue,
  warningThreshold?: number,
): Promise<PitchAcceptanceResult> {
  // 追記が成立したかを後から照合するため、採番される D1 を先に読む。
  let expectedD1: number | undefined
  try {
    expectedD1 = await queue.readNextD1(input.scope)
  } catch {
    expectedD1 = undefined
  }

  const append: DurableQueueAppend = {
    scope: input.scope,
    d5: input.d5,
    version: input.version,
    event: input.event,
  }

  try {
    const disciplined = await appendUnderQueueDiscipline(
      queue,
      append,
      warningThreshold,
    )
    return {
      outcome: 'accepted',
      slot: disciplined.slot,
      unsentCount: disciplined.unsentCount,
      warningThresholdReached: disciplined.warningThresholdReached,
    }
  } catch {
    return reconcileAppend(queue, input, expectedD1)
  }
}

/** 排他を取れなかったときの結果。 */
export function pitchAcceptanceNotStarted(
  singleWriterReason: SingleWriterStartFailure,
): PitchAcceptanceResult {
  return {
    outcome: 'not-accepted',
    reason: PITCH_ACCEPTANCE_FAILURE.SINGLE_WRITER_NOT_STARTED,
    singleWriterReason,
  }
}

/**
 * 単一書き手の排他の下で永続キューへ追記し、追記の成立をもって受理とする。
 *
 * 排他を取れなければ追記しない。追記だけを行う入口で、送信までを 1 つの排他で
 * 包む経路は commitPitchEvent にある。
 *
 * Args:
 *     input: 追記するイベントと、その範囲。
 *     dependencies: 注入するキューと単一書き手の前提。
 *
 * Returns:
 *     受理・不受理・不明のいずれか。
 */
export async function acceptPitchEvent(
  input: PitchAcceptanceInput,
  dependencies: PitchAcceptanceDependencies,
): Promise<PitchAcceptanceResult> {
  if (!pitchScopeMatchesLock(input)) {
    return {
      outcome: 'not-accepted',
      reason: PITCH_ACCEPTANCE_FAILURE.SCOPE_MISMATCH,
    }
  }

  const started = await runAsSingleWriter<PitchAcceptanceResult>(
    { gameIdentifier: input.gameIdentifier },
    () =>
      appendPitchEventUnderLock(
        input,
        dependencies.queue,
        dependencies.warningThreshold,
      ),
    dependencies.singleWriterInjections,
  )

  if (!started.recordingStarted) {
    return pitchAcceptanceNotStarted(started.reason)
  }
  return started.value
}
