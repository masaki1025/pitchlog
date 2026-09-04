import { describe, expect, it, vi } from 'vitest'
import {
  EVENT_SLOT_IDS,
  REQUEST_ONLY_IDS,
  SYNC_EVENT_PATH,
  type EventSlotId,
  type RequestOnlyId,
} from './eventFieldRules'
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
): RequestBoundaryEnvelope {
  return {
    path: SYNC_EVENT_PATH.P3,
    p3State: P3_REQUEST_STATE.ENDED,
    requestValues: requestOnlyValues,
    recoveryGenerationAtCreation: {},
  }
}

const acceptsBinding: V12BindingVerifier = () => true

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

      expect(checkRequestBoundary(request, acceptsBinding)).toEqual({
        ok: true,
      })
      expect(checkRequestBoundary(request, () => false)).toEqual({
        ok: false,
        result: REQUEST_BOUNDARY_RESULT.B4,
      })
      expect(checkRequestBoundary(missingValue, acceptsBinding)).toEqual({
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

    expect(checkRequestBoundary(request, acceptsBinding)).toEqual({ ok: true })
    expect(checkRequestBoundary(request, () => false)).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B9,
    })
    expect(checkRequestBoundary(missingValue, acceptsBinding)).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B9,
    })
  })

  it('VF3: 終了後 P3 は V12 と verifier を不要とする', () => {
    const verifier = vi.fn<V12BindingVerifier>(() => false)

    expect(checkRequestBoundary(endedP3Request())).toEqual({ ok: true })
    expect(
      checkRequestBoundary(endedP3Request(requestValues({})), verifier),
    ).toEqual({ ok: true })
    expect(verifier).not.toHaveBeenCalled()
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

    expect(checkRequestBoundary(request, verifier)).toEqual({ ok: true })
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
        checkRequestBoundary(
          d1Request(SYNC_EVENT_PATH.P1, value),
          acceptsBinding,
        ),
      ).toEqual({
        ok: true,
      })
    },
  )

  it('verifier 未注入を fail-closed で拒否する', () => {
    const d1Result = checkRequestBoundary(d1Request())
    const p3Result = checkRequestBoundary(inProgressP3Request())

    expect(d1Result).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B4,
    })
    expect(p3Result).toEqual({
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

    expect(checkRequestBoundary(inProgressP3Request(), verifier)).toEqual({
      ok: false,
      result: REQUEST_BOUNDARY_RESULT.B9,
    })
  })

  it('V12 を EventSlotId に置けず、実行時にも未知スロットとして拒否する', () => {
    // @ts-expect-error V12 は要求レベルであり、イベントスロットではない。
    const invalidEventSlot: EventSlotId = 'V12'
    const event: SyncEvent = {
      kind: '6',
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
    expect(checkSyncEvent(event, { path: SYNC_EVENT_PATH.P1 })).toEqual({
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
