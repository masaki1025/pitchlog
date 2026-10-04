// この合成入口は docs/design/sync-protocol.md 4-3-A の W4 を直接の典拠とする。
// オンライン専用の変更操作に必要なクライアント側前提だけを扱い、要求境界の判定は既存実装へ委ねる。

import { SYNC_EVENT_PATH } from './eventFieldRules'
import {
  checkRequestBoundary,
  P3_REQUEST_STATE,
  type RecoveryGenerationVerifier,
  type RequestBoundaryEnvelope,
  type RequestBoundaryResult,
  type V12BindingVerifier,
} from './requestBoundary'

export const CHANGE_OPERATION_GATE_RESULT = {
  ONLINE_NOT_CONFIRMED: 'online-not-confirmed',
  UNSENT_OR_ACTION_REQUIRED_EVENTS_PRESENT_OR_UNCONFIRMED:
    'unsent-or-action-required-events-present-or-unconfirmed',
} as const

export type ChangeOperationGateRejection =
  | (typeof CHANGE_OPERATION_GATE_RESULT)[keyof typeof CHANGE_OPERATION_GATE_RESULT]
  | RequestBoundaryResult

export type ChangeOperationGateRequest = Extract<
  RequestBoundaryEnvelope,
  { path: typeof SYNC_EVENT_PATH.P3 }
>

export type ChangeOperationGateInjections = Readonly<{
  resolveOnline?: () => boolean | undefined
  /**
   * 進行中修正について FR-007 の修正許可条件④を確認する。
   *
   * `true` は `未送信` が 0 件かつ `要操作` が 0 件であることを表す。
   * `要操作` は現世代の正史へ入る予定の未解決イベントなので含める。
   * `退避済み` は現世代の正史へ適用されないため含めない。
   */
  resolveUnsentAndActionRequiredCountsZero?: () => boolean | undefined
  v12Binding?: V12BindingVerifier
  recoveryGeneration?: RecoveryGenerationVerifier
}>

export type ChangeOperationGateResult =
  | Readonly<{ ok: true }>
  | Readonly<{ ok: false; result: ChangeOperationGateRejection }>

function confirmPrerequisite(
  resolver: (() => boolean | undefined) | undefined,
): boolean {
  if (!resolver) {
    return false
  }
  try {
    return resolver() === true
  } catch {
    return false
  }
}

/**
 * 変更操作についてオンライン・キュー・要求境界の前提を合成する。
 *
 * Args:
 *   request: 進行中または終了後の変更操作要求。
 *   injections: オンライン、未送信・要操作の件数、記録権、復旧世代の検査器。
 *
 * Returns:
 *   すべての適用対象前提を満たす場合だけ成功となる判定結果。
 */
export function checkChangeOperationGate(
  request: ChangeOperationGateRequest,
  injections: ChangeOperationGateInjections = {},
): ChangeOperationGateResult {
  if (!confirmPrerequisite(injections.resolveOnline)) {
    return {
      ok: false,
      result: CHANGE_OPERATION_GATE_RESULT.ONLINE_NOT_CONFIRMED,
    }
  }

  if (
    request.p3State === P3_REQUEST_STATE.IN_PROGRESS &&
    !confirmPrerequisite(injections.resolveUnsentAndActionRequiredCountsZero)
  ) {
    return {
      ok: false,
      result:
        CHANGE_OPERATION_GATE_RESULT.UNSENT_OR_ACTION_REQUIRED_EVENTS_PRESENT_OR_UNCONFIRMED,
    }
  }

  return checkRequestBoundary(request, {
    v12Binding: injections.v12Binding,
    recoveryGeneration: injections.recoveryGeneration,
  })
}
