// この表と検査器は docs/design/sync-protocol.md 4-3 の V12 条件・結果写像の写しである。
// 値は実装で決めず、変更は正本の改訂ゲートを通すこと。
// V12 の物理形式は解釈せず、結合判定は注入した verifier に委ねる。

import {
  REQUEST_ONLY_IDS,
  SYNC_EVENT_PATH,
  type RequestOnlyId,
  type SyncEventPath,
} from './eventFieldRules'

export const P3_REQUEST_STATE = {
  IN_PROGRESS: '進行中',
  ENDED: '終了後',
} as const

export type P3RequestState =
  (typeof P3_REQUEST_STATE)[keyof typeof P3_REQUEST_STATE]

type D1RequestPath = Exclude<SyncEventPath, typeof SYNC_EVENT_PATH.P3>
type RequiredRequestValues = Readonly<Record<RequestOnlyId, unknown>>
type OptionalRequestValues = Readonly<Partial<Record<RequestOnlyId, unknown>>>

export type RequestBoundaryEnvelope =
  | Readonly<{
      path: D1RequestPath
      p3State?: never
      requestValues: RequiredRequestValues
      recoveryGenerationAtCreation: unknown
    }>
  | Readonly<{
      path: typeof SYNC_EVENT_PATH.P3
      p3State: typeof P3_REQUEST_STATE.IN_PROGRESS
      requestValues: RequiredRequestValues
      recoveryGenerationAtCreation: unknown
    }>
  | Readonly<{
      path: typeof SYNC_EVENT_PATH.P3
      p3State: typeof P3_REQUEST_STATE.ENDED
      requestValues: OptionalRequestValues
      recoveryGenerationAtCreation: unknown
    }>

export const REQUEST_BOUNDARY_RESULT = {
  B4: 'B4',
  B9: 'B9',
} as const

export type RequestBoundaryResult =
  (typeof REQUEST_BOUNDARY_RESULT)[keyof typeof REQUEST_BOUNDARY_RESULT]

export const V12_BINDING_COMPONENTS = [
  '現D4',
  '現復旧世代',
  '保持端末',
] as const

export type V12BindingComponent = (typeof V12_BINDING_COMPONENTS)[number]

type RequestSelector = Readonly<{
  paths: readonly SyncEventPath[]
  p3States?: readonly P3RequestState[]
}>

type V12BoundaryEffect =
  | Readonly<{ kind: 'presence'; required: boolean }>
  | Readonly<{ kind: 'failure'; result: RequestBoundaryResult }>
  | Readonly<{
      kind: 'binding'
      components: readonly V12BindingComponent[]
    }>

type V12BoundaryRule = Readonly<{
  id: `VF${number}`
  condition: string
  outcomes: readonly string[]
  selectors: readonly RequestSelector[]
  effect: V12BoundaryEffect
}>

const D1_REQUEST_PATHS = [
  SYNC_EVENT_PATH.P1,
  SYNC_EVENT_PATH.P2,
  SYNC_EVENT_PATH.P4,
] as const

const IN_PROGRESS_P3_SELECTOR = {
  paths: [SYNC_EVENT_PATH.P3],
  p3States: [P3_REQUEST_STATE.IN_PROGRESS],
} as const

export const V12_BOUNDARY_RULES = [
  {
    id: 'VF1',
    condition: 'P1・P2・P4',
    outcomes: ['V12必須'],
    selectors: [{ paths: D1_REQUEST_PATHS }],
    effect: { kind: 'presence', required: true },
  },
  {
    id: 'VF2',
    condition: '進行中P3',
    outcomes: ['V12必須'],
    selectors: [IN_PROGRESS_P3_SELECTOR],
    effect: { kind: 'presence', required: true },
  },
  {
    id: 'VF3',
    condition: '終了後P3',
    outcomes: ['V12不要'],
    selectors: [
      {
        paths: [SYNC_EVENT_PATH.P3],
        p3States: [P3_REQUEST_STATE.ENDED],
      },
    ],
    effect: { kind: 'presence', required: false },
  },
  {
    id: 'VF4',
    condition: 'P1・P2・P4のV12不成立',
    outcomes: [REQUEST_BOUNDARY_RESULT.B4],
    selectors: [{ paths: D1_REQUEST_PATHS }],
    effect: { kind: 'failure', result: REQUEST_BOUNDARY_RESULT.B4 },
  },
  {
    id: 'VF5',
    condition: '進行中P3のV12不成立',
    outcomes: [REQUEST_BOUNDARY_RESULT.B9],
    selectors: [IN_PROGRESS_P3_SELECTOR],
    effect: { kind: 'failure', result: REQUEST_BOUNDARY_RESULT.B9 },
  },
  {
    id: 'VF6',
    condition: 'V12の復旧世代結合',
    outcomes: V12_BINDING_COMPONENTS,
    selectors: [{ paths: D1_REQUEST_PATHS }, IN_PROGRESS_P3_SELECTOR],
    effect: { kind: 'binding', components: V12_BINDING_COMPONENTS },
  },
] as const satisfies readonly V12BoundaryRule[]

export type V12BindingVerifier = (input: {
  readonly value: unknown
  readonly recoveryGenerationAtCreation: unknown
  readonly bindingComponents: readonly V12BindingComponent[]
  readonly request: RequestBoundaryEnvelope
}) => boolean

export type RequestBoundaryCheckResult =
  | Readonly<{ ok: true }>
  | Readonly<{ ok: false; result: RequestBoundaryResult }>

export class RequestBoundaryError extends Error {
  readonly result: RequestBoundaryResult

  constructor(result: RequestBoundaryResult) {
    super(result)
    this.name = 'RequestBoundaryError'
    this.result = result
  }
}

function selectorMatches(
  selector: RequestSelector,
  request: RequestBoundaryEnvelope,
): boolean {
  if (!selector.paths.includes(request.path)) {
    return false
  }

  if (selector.p3States === undefined) {
    return true
  }

  return (
    request.path === SYNC_EVENT_PATH.P3 &&
    selector.p3States.includes(request.p3State)
  )
}

function ruleMatches(
  rule: V12BoundaryRule,
  request: RequestBoundaryEnvelope,
): boolean {
  return rule.selectors.some((selector) => selectorMatches(selector, request))
}

export function checkRequestBoundary(
  request: RequestBoundaryEnvelope,
  verifier?: V12BindingVerifier,
): RequestBoundaryCheckResult {
  let required: boolean | undefined
  let failureResult: RequestBoundaryResult | undefined
  let bindingComponents: readonly V12BindingComponent[] | undefined

  for (const rule of V12_BOUNDARY_RULES) {
    if (!ruleMatches(rule, request)) {
      continue
    }

    switch (rule.effect.kind) {
      case 'presence':
        required = rule.effect.required
        break
      case 'failure':
        failureResult = rule.effect.result
        break
      case 'binding':
        bindingComponents = rule.effect.components
        break
    }
  }

  if (required === false) {
    return { ok: true }
  }

  if (
    required === undefined ||
    failureResult === undefined ||
    bindingComponents === undefined
  ) {
    throw new Error('V12_BOUNDARY_RULES')
  }

  const requestOnlyId = REQUEST_ONLY_IDS[0]
  const hasValue = Object.prototype.hasOwnProperty.call(
    request.requestValues,
    requestOnlyId,
  )

  if (!hasValue || verifier === undefined) {
    return { ok: false, result: failureResult }
  }

  try {
    return verifier({
      value: request.requestValues[requestOnlyId],
      recoveryGenerationAtCreation: request.recoveryGenerationAtCreation,
      bindingComponents,
      request,
    })
      ? { ok: true }
      : { ok: false, result: failureResult }
  } catch {
    return { ok: false, result: failureResult }
  }
}

export function validateRequestBoundary(
  request: RequestBoundaryEnvelope,
  verifier?: V12BindingVerifier,
): void {
  const result = checkRequestBoundary(request, verifier)

  if (!result.ok) {
    throw new RequestBoundaryError(result.result)
  }
}

export function retryRequestBoundary<T extends RequestBoundaryEnvelope>(
  request: T,
): Readonly<T> {
  return Object.freeze({
    ...request,
    requestValues: Object.freeze({ ...request.requestValues }),
    recoveryGenerationAtCreation: request.recoveryGenerationAtCreation,
  })
}
