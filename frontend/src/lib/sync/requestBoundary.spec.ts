import { describe, expect, it, vi } from 'vitest'
import {
  EVENT_SLOT_IDS,
  REQUEST_ONLY_IDS,
  SYNC_EVENT_PATH,
  type EventSlotId,
  type RequestOnlyId,
} from './eventFieldRules'
import { buildSyncEventKindSet } from './eventKinds'
import type { SyncEvent } from './syncEvent'
import { checkSyncEvent, SYNC_EVENT_VIOLATION } from './validateSyncEvent'
import {
  checkRequestBoundary,
  P3_REQUEST_STATE,
  REQUEST_BOUNDARY_RESULT,
  RequestBoundaryError,
  retryRequestBoundary,
  V12_BINDING_COMPONENTS,
  V12_BOUNDARY_RULES,
  validateRequestBoundary,
  type RecoveryGenerationVerifier,
  type RequestBoundaryEnvelope,
  type V12BindingVerifier,
} from './requestBoundary'

const EXPECTED_VF_ROWS = [
  { id: 'VF1', condition: 'P1・P2・P4', outcomes: ['V12必須'] },
  { id: 'VF2', condition: '進行中P3', outcomes: ['V12必須'] },
  { id: 'VF3', condition: '終了後P3', outcomes: ['V12不要'] },
  {
    id: 'VF4',
    condition: 'P1・P2・P4のV12不成立',
    outcomes: ['B4'],
  },
  { id: 'VF5', condition: '進行中P3のV12不成立', outcomes: ['B9'] },
  {
    id: 'VF6',
    condition: 'V12の復旧世代結合',
    outcomes: ['現D4', '現復旧世代', '保持端末'],
  },
] as const

function requestValues(value: unknown): Record<RequestOnlyId, unknown> {
  return { V12: value }
}

function d1Request(
  path:
    | typeof SYNC_EVENT_PATH.P1
    | typeof SYNC_EVENT_PATH.P2
    | typeof SYNC_EVENT_PATH.P4 = SYNC_EVENT_PATH.P1,
  value: unknown = {},
  recoveryGenerationAtCreation: unknown = {},
): RequestBoundaryEnvelope {
  return {
    path,
    requestValues: requestValues(value),
    recoveryGenerationAtCreation,
  }
}

function inProgressP3Request(
  value: unknown = {},
  recoveryGenerationAtCreation: unknown = {},
): RequestBoundaryEnvelope {
  return {
    path: SYNC_EVENT_PATH.P3,
    p3State: P3_REQUEST_STATE.IN_PROGRESS,
    requestValues: requestValues(value),
    recoveryGenerationAtCreation,
  }
}

function endedP3Request(
  requestOnlyValues: Partial<Record<RequestOnlyId, unknown>> = {},
  recoveryGenerationAtCreation: unknown = {},
): RequestBoundaryEnvelope {
  return {
    path: SYNC_EVENT_PATH.P3,
    p3State: P3_REQUEST_STATE.ENDED,
    requestValues: requestOnlyValues,
    recoveryGenerationAtCreation,
  }
}

const acceptsBinding: V12BindingVerifier = () => true
const acceptsRecoveryGeneration: RecoveryGenerationVerifier = () => true
const adoptedEventKinds = buildSyncEventKindSet({
  stateCorrectionAdopted: true,
})

describe('requestBoundary', () => {
  it.each(EXPECTED_VF_ROWS)(
    '$id の条件・帰結を正本どおり保持する',
    (expected) => {
      const rule = V12_BOUNDARY_RULES.find(
        (candidate) => candidate.id === expected.id,
      )

      expect(rule).toBeDefined()
      expect(rule).toMatchObject(expected)
    },
  )

  it.each([SYNC_EVENT_PATH.P1, SYNC_EVENT_PATH.P2, SYNC_EVENT_PATH.P4])(
    'VF1・VF4: %s は V12 を必須とし、不成立を B4 へ写す',
    (path) => {
      const request = d1Request(path)
      const missingValue = {
        ...request,
        requestValues: {},
      } as RequestBoundaryEnvelope

      expect(
        checkRequestBoundary(request, { v12Binding: acceptsBinding }),
      ).toEqual({
        ok: true,
      })
      expect(
        checkRequestBoundary(request, { v12Binding: () => false }),
      ).toEqual({
        ok: false,
        result: REQUEST_BOUNDARY_RESULT.B4,
      })
      expect(
        checkRequestBoundary(missingValue, { v12Binding: acceptsBinding }),
      ).toEqual({
        ok: false,
        result: REQUEST_BOUNDARY_RESULT.B4,
      })
    },
  )

  it('VF2・VF5: 進行中 P3 は V12 を必須とし、不成立を B9 へ写す', () => {
    const request = inProgressP3Request()
    const missingValue = {
      ...request,
      requestValues: {},
    } as RequestBoundaryEnvelope

    const recoveryGeneration = acceptsRecoveryGeneration

    expect(
      checkRequestBoundary(request, {
        recoveryGeneration,
        v12Binding: acceptsBinding,
      }),
    ).toEqual({ ok: true })
    expect(
      checkRequestBoundary(request, {
        recoveryGeneration,
        v12Binding: () => false,
      }),
    ).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B9,
    })
    expect(
      checkRequestBoundary(missingValue, {
        recoveryGeneration,
        v12Binding: acceptsBinding,
      }),
    ).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B9,
    })
  })

  it('VF3: 終了後 P3 は V12 不要でも復旧世代照合を必要とする', () => {
    const verifier = vi.fn<V12BindingVerifier>(() => false)
    const recoveryGeneration = vi.fn<RecoveryGenerationVerifier>(() => true)

    // VF3 が不要とするのは V12 だけであり、復旧世代照合は終了後にも行う。
    expect(
      checkRequestBoundary(endedP3Request(), {
        recoveryGeneration,
        v12Binding: verifier,
      }),
    ).toEqual({ ok: true })
    expect(
      checkRequestBoundary(endedP3Request(requestValues({})), {
        recoveryGeneration,
        v12Binding: verifier,
      }),
    ).toEqual({ ok: true })
    expect(recoveryGeneration).toHaveBeenCalledTimes(2)
    expect(verifier).not.toHaveBeenCalled()
  })

  it('終了後 P3 の旧復旧世代を B9 へ写す', () => {
    const recoveryGenerationAtCreation = { 世代: '復元前' }
    const request = endedP3Request({}, recoveryGenerationAtCreation)
    const recoveryGeneration = vi.fn<RecoveryGenerationVerifier>(() => false)

    expect(checkRequestBoundary(request, { recoveryGeneration })).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B9,
    })
    expect(recoveryGeneration).toHaveBeenCalledWith({
      recoveryGenerationAtCreation,
      request,
    })
  })

  it('進行中 P3 の旧復旧世代を B9 へ写し、V12 を照合しない', () => {
    const v12Binding = vi.fn<V12BindingVerifier>(() => true)

    expect(
      checkRequestBoundary(inProgressP3Request(), {
        recoveryGeneration: () => false,
        v12Binding,
      }),
    ).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B9,
    })
    expect(v12Binding).not.toHaveBeenCalled()
  })

  it('P3 の復旧世代 verifier 未注入を fail-closed で拒否する', () => {
    expect(
      checkRequestBoundary(inProgressP3Request(), {
        v12Binding: acceptsBinding,
      }),
    ).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B9,
    })
    expect(checkRequestBoundary(endedP3Request())).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B9,
    })
    expect(() => validateRequestBoundary(endedP3Request())).toThrowError(
      RequestBoundaryError,
    )
  })

  it.each([
    ['進行中', inProgressP3Request()],
    ['終了後', endedP3Request()],
  ] as const)(
    '%s P3 で復旧世代 verifier の例外を fail-closed で拒否する',
    (_, request) => {
      const v12Binding = vi.fn<V12BindingVerifier>(() => true)
      const recoveryGeneration: RecoveryGenerationVerifier = () => {
        throw new Error('recovery generation verifier failure')
      }

      expect(
        checkRequestBoundary(request, { recoveryGeneration, v12Binding }),
      ).toEqual({
        ok: false,
        result: REQUEST_BOUNDARY_RESULT.B9,
      })
      expect(v12Binding).not.toHaveBeenCalled()
    },
  )

  it('進行中 P3 では復旧世代照合を V12 照合より先に行う', () => {
    const recoveryGeneration = vi.fn<RecoveryGenerationVerifier>(() => true)
    const v12Binding = vi.fn<V12BindingVerifier>(() => true)

    expect(
      checkRequestBoundary(inProgressP3Request(), {
        recoveryGeneration,
        v12Binding,
      }),
    ).toEqual({ ok: true })
    expect(recoveryGeneration).toHaveBeenCalledOnce()
    expect(v12Binding).toHaveBeenCalledOnce()
    expect(recoveryGeneration.mock.invocationCallOrder[0]).toBeLessThan(
      v12Binding.mock.invocationCallOrder[0]!,
    )
  })

  it('VF6: verifier に現 D4・現復旧世代・保持端末の結合を委ねる', () => {
    const value = { 任意: ['不透明な値'] }
    const recoveryGenerationAtCreation = { 世代: '要求作成時' }
    const request = d1Request(
      SYNC_EVENT_PATH.P1,
      value,
      recoveryGenerationAtCreation,
    )
    const verifier = vi.fn<V12BindingVerifier>(() => true)

    expect(checkRequestBoundary(request, { v12Binding: verifier })).toEqual({
      ok: true,
    })
    expect(verifier).toHaveBeenCalledOnce()
    expect(verifier).toHaveBeenCalledWith({
      value,
      recoveryGenerationAtCreation,
      bindingComponents: V12_BINDING_COMPONENTS,
      request,
    })
  })

  it.each([undefined, {}, { 巨大: { 入れ子: Array.from({ length: 100 }) } }])(
    'V12 の物理形式を検査しない',
    (value) => {
      expect(
        checkRequestBoundary(d1Request(SYNC_EVENT_PATH.P1, value), {
          v12Binding: acceptsBinding,
        }),
      ).toEqual({
        ok: true,
      })
    },
  )

  it('verifier 未注入を fail-closed で拒否する', () => {
    const d1Result = checkRequestBoundary(d1Request())
    const p3Result = checkRequestBoundary(inProgressP3Request())
    const endedP3Result = checkRequestBoundary(endedP3Request())

    expect(d1Result).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B4,
    })
    expect(p3Result).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B9,
    })
    expect(endedP3Result).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B9,
    })
    expect(() => validateRequestBoundary(d1Request())).toThrowError(
      RequestBoundaryError,
    )
  })

  it('verifier の例外を fail-closed で拒否する', () => {
    const verifier: V12BindingVerifier = () => {
      throw new Error('verifier failure')
    }

    expect(
      checkRequestBoundary(inProgressP3Request(), {
        recoveryGeneration: acceptsRecoveryGeneration,
        v12Binding: verifier,
      }),
    ).toEqual({ ok: false, result: REQUEST_BOUNDARY_RESULT.B9 })
  })

  it('V12 を EventSlotId に置けず、実行時にも未知スロットとして拒否する', () => {
    // @ts-expect-error V12 は要求レベルであり、イベントスロットではない。
    const invalidEventSlot: EventSlotId = 'V12'
    const event: SyncEvent = {
      fields: {
        V1: 'd5',
        V2: 'd1',
        V3: 'd4',
        V4: 'game',
        V5: '6',
        V7: {},
      },
    }
    ;(event.fields as Record<string, unknown>)[invalidEventSlot] = {}

    expect(EVENT_SLOT_IDS).not.toContain(invalidEventSlot)
    expect(
      checkSyncEvent(event, {
        path: SYNC_EVENT_PATH.P1,
        eventKinds: adoptedEventKinds,
      }),
    ).toEqual({
      ok: false,
      reason: {
        violation: SYNC_EVENT_VIOLATION.UNKNOWN_SLOT,
        target: invalidEventSlot,
      },
    })
  })

  it('復旧世代をイベント値にも要求値にも含めない', () => {
    const excludedFromEventSlots: '復旧世代' extends EventSlotId
      ? false
      : true = true
    const excludedFromRequestOnlyIds: '復旧世代' extends RequestOnlyId
      ? false
      : true = true

    expect(excludedFromEventSlots).toBe(true)
    expect(excludedFromRequestOnlyIds).toBe(true)
    expect(EVENT_SLOT_IDS).not.toContain('復旧世代')
    expect(REQUEST_ONLY_IDS).not.toContain('復旧世代')
  })

  it('再試行で要求作成時の復旧世代を変えない', () => {
    const recoveryGenerationAtCreation = { 世代: '作成時' }
    const request = d1Request(
      SYNC_EVENT_PATH.P1,
      {},
      recoveryGenerationAtCreation,
    )
    const retried = retryRequestBoundary(request)

    expect(retried).not.toBe(request)
    expect(retried.recoveryGenerationAtCreation).toBe(
      recoveryGenerationAtCreation,
    )
    expect(retryRequestBoundary(retried).recoveryGenerationAtCreation).toBe(
      recoveryGenerationAtCreation,
    )
  })
})
