import { describe, expect, it, vi } from 'vitest'
import k5TombstoneSource from './k5Tombstone.ts?raw'
import { readCanonTombstoneRule } from './canonOracle'
import { REQUEST_ONLY_IDS, SYNC_EVENT_PATH } from './eventFieldRules'
import {
  K5_ACTION_GENERATION_RULES,
  K5_TOMBSTONE_RULE,
  prepareTombstoneReplacement,
  TOMBSTONE_ONLINE_STATE,
  type TombstoneBoundaryRequest,
  type TombstoneGenerationInjections,
  type TombstoneGenerationRequest,
  type TombstoneRecordingRightVerifier,
  type TombstoneSourceSlot,
} from './k5Tombstone'
import { V12_BINDING_COMPONENTS } from './requestBoundary'
import { QUEUE_ACTION_REQUIRED_LABELS, QUEUE_STATES } from './queueState'
import {
  evaluateQueueTransition,
  type QueueEventKey,
  type QueueSlot,
  type QueueTransitionInjections,
} from './queueTransition'

const UNSENT_STATE = QUEUE_STATES[0].id
const ACTION_REQUIRED_STATE = QUEUE_STATES[1].id
const REVISION_ACTION_LABEL = QUEUE_ACTION_REQUIRED_LABELS[0]
const TOMBSTONE_ACTION_LABEL = QUEUE_ACTION_REQUIRED_LABELS[1]
const REQUEST_ONLY_ID = REQUEST_ONLY_IDS[0]
if (!REQUEST_ONLY_ID) {
  throw new Error('要求レベル ID がありません')
}

const BASE_KEY: QueueEventKey = {
  d4: {},
  d1: 1,
  d5: {},
}
const TOMBSTONE_VERSION = {}

function tombstoneSourceSlot(): TombstoneSourceSlot {
  return {
    game: {},
    d4: BASE_KEY.d4,
    d1: BASE_KEY.d1 as number,
    d5: BASE_KEY.d5,
    version: {},
    event: { fields: { V7: { rejected: true } } },
    state: ACTION_REQUIRED_STATE,
    actionRequiredLabel: TOMBSTONE_ACTION_LABEL.id,
  }
}

function boundaryRequest(
  slot: TombstoneSourceSlot = tombstoneSourceSlot(),
): TombstoneBoundaryRequest {
  return {
    path: SYNC_EVENT_PATH.P1,
    requestValues: { [REQUEST_ONLY_ID]: {} },
    recoveryGenerationAtCreation: {},
    game: slot.game,
    d4: slot.d4,
    d1: slot.d1,
  }
}

function generationRequest(
  slot: TombstoneSourceSlot = tombstoneSourceSlot(),
): TombstoneGenerationRequest {
  return {
    slot,
    tombstoneVersion: TOMBSTONE_VERSION,
    boundaryRequest: boundaryRequest(slot),
  }
}

function successfulInjections(
  newD5: unknown,
  overrides: Partial<TombstoneGenerationInjections> = {},
): TombstoneGenerationInjections {
  return {
    resolveOnlineState: () => TOMBSTONE_ONLINE_STATE.ONLINE,
    v12Binding: () => true,
    generateD5: () => newD5,
    ...overrides,
  }
}

// オラクルに無い同一 D1 の不可分置換・新しい D1 を採番しないこと・旧保持端末と
// オフライン時の非提供は正本 7-2 本文が唯一の出所である。期待集合を再掲せず、
// 実装構造を検査し、逐語一致は H-59 の人間逐行確認（ステップ 13）へ送る。
describe('k5Tombstone', () => {
  it('K5 の右辺2トークンをオラクルと逐語・順序一致させる', () => {
    const canonRule = readCanonTombstoneRule()

    expect(K5_TOMBSTONE_RULE.id).toBe(canonRule.id)
    expect(K5_TOMBSTONE_RULE.name).toBe(canonRule.name)
    expect(
      K5_TOMBSTONE_RULE.conditions.map((condition) => condition.id),
    ).toEqual(canonRule.tokens)
    expect(K5_TOMBSTONE_RULE.conditions).toHaveLength(2)
  })

  it('改訂版と墓標の生成条件を非対称な表で固定する', () => {
    const revisionRule = K5_ACTION_GENERATION_RULES.find(
      (rule) => rule.actionRequiredLabel === REVISION_ACTION_LABEL.id,
    )
    const tombstoneRule = K5_ACTION_GENERATION_RULES.find(
      (rule) => rule.actionRequiredLabel === TOMBSTONE_ACTION_LABEL.id,
    )

    expect(K5_ACTION_GENERATION_RULES).toHaveLength(2)
    expect(revisionRule?.localGenerationAllowed).toBe(true)
    expect(revisionRule?.onlineRecordingRightRequired).toBe(false)
    expect(tombstoneRule?.localGenerationAllowed).toBe(false)
    expect(tombstoneRule?.onlineRecordingRightRequired).toBe(true)
  })

  it.each([
    ['オフライン', TOMBSTONE_ONLINE_STATE.OFFLINE],
    ['不明', TOMBSTONE_ONLINE_STATE.UNKNOWN],
  ] as const)('%s では墓標操作を提供しない', (_name, onlineState) => {
    const verifier = vi.fn<TombstoneRecordingRightVerifier>(() => true)
    const result = prepareTombstoneReplacement(generationRequest(), {
      ...successfulInjections({}),
      resolveOnlineState: () => onlineState,
      v12Binding: verifier,
    })

    expect(result.offered).toBe(false)
    expect(verifier).not.toHaveBeenCalled()
  })

  it('オンライン状態が未注入なら墓標操作を提供しない', () => {
    const result = prepareTombstoneReplacement(generationRequest(), {
      v12Binding: () => true,
      generateD5: () => ({}),
    })

    expect(result.offered).toBe(false)
  })

  it('旧保持端末では墓標操作を提供しない', () => {
    const result = prepareTombstoneReplacement(
      generationRequest(),
      successfulInjections({}, { v12Binding: () => false }),
    )

    expect(result.offered).toBe(false)
  })

  const unavailableVerifierCases = [
    ['未注入', undefined],
    [
      '例外',
      () => {
        throw new Error('照合失敗')
      },
    ],
    ['不明', () => undefined],
  ] as const satisfies readonly (readonly [
    string,
    TombstoneRecordingRightVerifier | undefined,
  ])[]

  it.each(unavailableVerifierCases)(
    '記録権 verifier が%sなら fail-closed にする',
    (_name, verifier) => {
      const result = prepareTombstoneReplacement(
        generationRequest(),
        successfulInjections({}, { v12Binding: verifier }),
      )

      expect(result.offered).toBe(false)
    },
  )

  it('requestBoundary の verifier を通して現保持端末を照合する', () => {
    const verifier = vi.fn<TombstoneRecordingRightVerifier>(() => true)
    const result = prepareTombstoneReplacement(
      generationRequest(),
      successfulInjections({}, { v12Binding: verifier }),
    )

    expect(result.offered).toBe(true)
    expect(verifier).toHaveBeenCalledOnce()
    expect(verifier.mock.calls[0]?.[0].bindingComponents).toBe(
      V12_BINDING_COMPONENTS,
    )
  })

  it('同じ D1・新しい D5・版・空の内容・未送信状態を一つの置換にする', () => {
    const newD5 = {}
    const allocateD1 = vi.fn(() => ({}))
    const result = prepareTombstoneReplacement(
      generationRequest(),
      successfulInjections(newD5, { allocateD1 }),
    )

    expect(result.offered).toBe(true)
    expect(allocateD1).not.toHaveBeenCalled()
    if (!result.offered) {
      throw new Error('墓標置換がありません')
    }
    expect(result.replacement.d4).toBe(BASE_KEY.d4)
    expect(result.replacement.d1).toBe(BASE_KEY.d1)
    expect(result.replacement.d5).toBe(newD5)
    expect(result.replacement.version).toBe(TOMBSTONE_VERSION)
    expect(Reflect.ownKeys(result.replacement.event.fields)).toHaveLength(0)
    expect(result.replacement.state).toBe(UNSENT_STATE)
    expect(Object.isFrozen(result.replacement)).toBe(true)
    expect(Object.isFrozen(result.replacement.event)).toBe(true)
    expect(Object.isFrozen(result.replacement.event.fields)).toBe(true)
  })

  it('slot と要求境界が別イベントなら墓標操作を提供しない', () => {
    const request = generationRequest()

    expect(
      prepareTombstoneReplacement(
        {
          ...request,
          boundaryRequest: { ...request.boundaryRequest, game: {} },
        },
        successfulInjections({}),
      ).offered,
    ).toBe(false)
  })

  it('新しい D5 が undefined なら墓標操作を提供しない', () => {
    expect(
      prepareTombstoneReplacement(
        generationRequest(),
        successfulInjections(undefined),
      ).offered,
    ).toBe(false)
  })

  it('既存 D5 を再利用する墓標置換を拒否する', () => {
    const result = prepareTombstoneReplacement(
      generationRequest(),
      successfulInjections(BASE_KEY.d5),
    )

    expect(result.offered).toBe(false)
  })

  it("k5Tombstone.ts に 'V12' と完全一致する文字列リテラルを置かない", () => {
    expect(k5TombstoneSource.match(/(['"`])V12\1/g) ?? []).toHaveLength(0)
  })

  const transitionCases = [
    {
      name: 'オンラインかつ現保持端末',
      onlineState: TOMBSTONE_ONLINE_STATE.ONLINE,
      verifierResult: true,
      expectedApplied: true,
    },
    {
      name: 'オフライン',
      onlineState: TOMBSTONE_ONLINE_STATE.OFFLINE,
      verifierResult: true,
      expectedApplied: false,
    },
    {
      name: '旧保持端末',
      onlineState: TOMBSTONE_ONLINE_STATE.ONLINE,
      verifierResult: false,
      expectedApplied: false,
    },
  ] as const

  it.each(transitionCases)(
    'queueTransition との結合: $name は遷移可否が $expectedApplied',
    ({ onlineState, verifierResult, expectedApplied }) => {
      const sourceSlot = tombstoneSourceSlot()
      const slot: Extract<QueueSlot, { source: 'd1-event' }> = {
        state: sourceSlot.state,
        source: 'd1-event',
        key: {
          d4: sourceSlot.d4,
          d1: sourceSlot.d1,
          d5: sourceSlot.d5,
        },
        content: sourceSlot.event.fields,
        actionRequiredLabel: sourceSlot.actionRequiredLabel,
      }
      const newD5 = {}
      const replacement = {
        key: { d4: slot.key.d4, d1: slot.key.d1, d5: newD5 },
        content: {},
      }
      const prepared = prepareTombstoneReplacement(
        generationRequest(sourceSlot),
        {
          resolveOnlineState: () => onlineState,
          v12Binding: () => verifierResult,
          generateD5: () => newD5,
        },
      )
      const confirmTombstoneGeneration: NonNullable<
        QueueTransitionInjections['confirmTombstoneGeneration']
      > = ({ slot: candidate, replacement: candidateReplacement }) => {
        return (
          candidate === slot &&
          candidateReplacement === replacement &&
          prepared.offered
        )
      }
      const result = evaluateQueueTransition(
        {
          kind: 'action-replacement-persisted',
          slot,
          replacement,
        },
        { confirmTombstoneGeneration },
      )

      expect(result.applied).toBe(expectedApplied)
    },
  )
})
