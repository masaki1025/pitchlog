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
    resolveUnsentQueueEmpty: () => true,
    v12Binding: () => true,
    recoveryGeneration: () => true,
  }
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
    {
      prerequisite: '未同期キュー空',
      injections: {
        ...confirmedInjections(),
        resolveUnsentQueueEmpty: () => false,
      },
      expectedResult:
        CHANGE_OPERATION_GATE_RESULT.UNSENT_QUEUE_NOT_EMPTY_OR_UNCONFIRMED,
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

  it('終了後はキュー非空・記録権証明なしでもオンラインなら許可する', () => {
    const resolveUnsentQueueEmpty = vi.fn(() => false)
    const v12Binding = vi.fn<V12BindingVerifier>(() => false)
    const recoveryGeneration = vi.fn<RecoveryGenerationVerifier>(() => true)

    expect(
      checkChangeOperationGate(endedRequest(), {
        resolveOnline: () => true,
        resolveUnsentQueueEmpty,
        v12Binding,
        recoveryGeneration,
      }),
    ).toEqual({ ok: true })
    expect(resolveUnsentQueueEmpty).not.toHaveBeenCalled()
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
        resolveUnsentQueueEmpty: () => true,
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
        resolveUnsentQueueEmpty: () => true,
        v12Binding: () => true,
        recoveryGeneration: () => true,
      },
    },
    {
      injection: 'キュー状態',
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
        resolveUnsentQueueEmpty: () => true,
        recoveryGeneration: () => true,
      },
    },
    {
      injection: '復旧世代 verifier',
      injections: {
        resolveOnline: () => true,
        resolveUnsentQueueEmpty: () => true,
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

  it.each(['オンライン判定', 'キュー状態'] as const)(
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
              resolveUnsentQueueEmpty: throwingResolver,
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
