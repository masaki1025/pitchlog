import { describe, expect, it, vi } from 'vitest'
import changeOperationGateSource from './changeOperationGate.ts?raw'
import { CLIENT_DISCIPLINE_RULES } from './clientDiscipline'
import {
  CHANGE_OPERATION_GATE_RESULT,
  checkChangeOperationGate,
  type ChangeOperationGateInjections,
  type ChangeOperationGateRequest,
} from './changeOperationGate'
import { REQUEST_ONLY_IDS, SYNC_EVENT_PATH } from './eventFieldRules'
import {
  P3_REQUEST_STATE,
  REQUEST_BOUNDARY_RESULT,
  type RecoveryGenerationVerifier,
  type V12BindingVerifier,
} from './requestBoundary'

const [REQUEST_ONLY_ID] = REQUEST_ONLY_IDS
if (!REQUEST_ONLY_ID) {
  throw new Error('要求レベルの値 ID がありません')
}

function inProgressRequest(): ChangeOperationGateRequest {
  return {
    path: SYNC_EVENT_PATH.P3,
    p3State: P3_REQUEST_STATE.IN_PROGRESS,
    requestValues: { [REQUEST_ONLY_ID]: {} },
    recoveryGenerationAtCreation: {},
  }
}

function endedRequest(): ChangeOperationGateRequest {
  return {
    path: SYNC_EVENT_PATH.P3,
    p3State: P3_REQUEST_STATE.ENDED,
    requestValues: {},
    recoveryGenerationAtCreation: {},
  }
}

function confirmedInjections(): Required<ChangeOperationGateInjections> {
  return {
    resolveOnline: () => true,
    resolveUnsentAndActionRequiredCountsZero: () => true,
    v12Binding: () => true,
    recoveryGeneration: () => true,
  }
}

/**
 * FR-007 の修正許可条件④を表す注入値をキュー状態別の件数から作る。
 *
 * Args:
 *   counts: `未送信`・`要操作`・`退避済み`の件数。
 *
 * Returns:
 *   `未送信`と`要操作`がともに 0 件の場合だけ `true`。`退避済み`は判定に用いない。
 */
function queueConditionInjection(counts: {
  readonly unsent: number
  readonly actionRequired: number
  readonly evacuated: number
}): () => boolean {
  return () => counts.unsent === 0 && counts.actionRequired === 0
}

describe('changeOperationGate', () => {
  it.each([
    {
      prerequisite: 'オンライン',
      injections: {
        ...confirmedInjections(),
        resolveOnline: () => false,
      },
      expectedResult: CHANGE_OPERATION_GATE_RESULT.ONLINE_NOT_CONFIRMED,
    },
    {
      prerequisite: '記録権保持',
      injections: {
        ...confirmedInjections(),
        v12Binding: () => false,
      },
      expectedResult: REQUEST_BOUNDARY_RESULT.B9,
    },
  ])('進行中は $prerequisite の単独不成立を拒否する', (testCase) => {
    expect(
      checkChangeOperationGate(inProgressRequest(), testCase.injections),
    ).toEqual({ ok: false, result: testCase.expectedResult })
  })

  it('進行中は3前提と要求境界がすべて成立した場合だけ許可する', () => {
    expect(
      checkChangeOperationGate(inProgressRequest(), confirmedInjections()),
    ).toEqual({ ok: true })
  })

  it('未送信 0 件でも要操作が残る進行中修正を拒否する', () => {
    const resolveUnsentAndActionRequiredCountsZero = queueConditionInjection({
      unsent: 0,
      actionRequired: 1,
      evacuated: 0,
    })

    expect(
      checkChangeOperationGate(inProgressRequest(), {
        ...confirmedInjections(),
        resolveUnsentAndActionRequiredCountsZero,
      }),
    ).toEqual({
      ok: false,
      result:
        CHANGE_OPERATION_GATE_RESULT.UNSENT_OR_ACTION_REQUIRED_EVENTS_PRESENT_OR_UNCONFIRMED,
    })
  })

  it('未送信 0 件・要操作 0 件なら退避済みだけが残っても進行中修正を許可する', () => {
    const resolveUnsentAndActionRequiredCountsZero = queueConditionInjection({
      unsent: 0,
      actionRequired: 0,
      evacuated: 1,
    })

    expect(
      checkChangeOperationGate(inProgressRequest(), {
        ...confirmedInjections(),
        resolveUnsentAndActionRequiredCountsZero,
      }),
    ).toEqual({ ok: true })
  })

  it('終了後は未送信・要操作が残り記録権証明がなくてもオンラインなら許可する', () => {
    const resolveUnsentAndActionRequiredCountsZero = vi.fn(() => false)
    const v12Binding = vi.fn<V12BindingVerifier>(() => false)
    const recoveryGeneration = vi.fn<RecoveryGenerationVerifier>(() => true)

    expect(
      checkChangeOperationGate(endedRequest(), {
        resolveOnline: () => true,
        resolveUnsentAndActionRequiredCountsZero,
        v12Binding,
        recoveryGeneration,
      }),
    ).toEqual({ ok: true })
    expect(resolveUnsentAndActionRequiredCountsZero).not.toHaveBeenCalled()
    expect(v12Binding).not.toHaveBeenCalled()
    expect(recoveryGeneration).toHaveBeenCalledOnce()
  })

  it('終了後もオフラインなら拒否する', () => {
    const recoveryGeneration = vi.fn<RecoveryGenerationVerifier>(() => true)

    expect(
      checkChangeOperationGate(endedRequest(), {
        resolveOnline: () => false,
        recoveryGeneration,
      }),
    ).toEqual({
      ok: false,
      result: CHANGE_OPERATION_GATE_RESULT.ONLINE_NOT_CONFIRMED,
    })
    expect(recoveryGeneration).not.toHaveBeenCalled()
  })

  it.each([
    ['進行中', inProgressRequest()],
    ['終了後', endedRequest()],
  ] as const)('%sの旧復旧世代を B9 で拒否する', (_name, request) => {
    const v12Binding = vi.fn<V12BindingVerifier>(() => true)

    expect(
      checkChangeOperationGate(request, {
        resolveOnline: () => true,
        resolveUnsentAndActionRequiredCountsZero: () => true,
        v12Binding,
        recoveryGeneration: () => false,
      }),
    ).toEqual({ ok: false, result: REQUEST_BOUNDARY_RESULT.B9 })
    expect(v12Binding).not.toHaveBeenCalled()
  })

  it.each([
    {
      injection: 'オンライン判定',
      injections: {
        resolveUnsentAndActionRequiredCountsZero: () => true,
        v12Binding: () => true,
        recoveryGeneration: () => true,
      },
    },
    {
      injection: '未送信・要操作の件数条件',
      injections: {
        resolveOnline: () => true,
        v12Binding: () => true,
        recoveryGeneration: () => true,
      },
    },
    {
      injection: '記録権 verifier',
      injections: {
        resolveOnline: () => true,
        resolveUnsentAndActionRequiredCountsZero: () => true,
        recoveryGeneration: () => true,
      },
    },
    {
      injection: '復旧世代 verifier',
      injections: {
        resolveOnline: () => true,
        resolveUnsentAndActionRequiredCountsZero: () => true,
        v12Binding: () => true,
      },
    },
  ] satisfies readonly {
    injection: string
    injections: ChangeOperationGateInjections
  }[])('$injection 未注入を fail-closed で拒否する', (testCase) => {
    expect(
      checkChangeOperationGate(inProgressRequest(), testCase.injections).ok,
    ).toBe(false)
  })

  it.each(['オンライン判定', '未送信・要操作の件数条件'] as const)(
    '%sの例外も fail-closed で拒否する',
    (name) => {
      const throwingResolver = () => {
        throw new Error(`${name} failure`)
      }
      const injections: ChangeOperationGateInjections =
        name === 'オンライン判定'
          ? {
              ...confirmedInjections(),
              resolveOnline: throwingResolver,
            }
          : {
              ...confirmedInjections(),
              resolveUnsentAndActionRequiredCountsZero: throwingResolver,
            }

      expect(checkChangeOperationGate(inProgressRequest(), injections).ok).toBe(
        false,
      )
    },
  )

  it('要求境界の既存 verifier を経由し、連続 prefix 水位を参照しない', () => {
    expect(changeOperationGateSource).toContain('checkRequestBoundary')
    expect(changeOperationGateSource).not.toMatch(/\bD3\b/)
    expect(changeOperationGateSource).not.toMatch(/(['"])V(?:[1-9]|1[0-2])\1/)
  })

  it('W4 由来の行をクライアント規律表へ追加しない', () => {
    expect(CLIENT_DISCIPLINE_RULES.map((rule) => rule.id)).toEqual(['Q3', 'Q7'])
  })
})
