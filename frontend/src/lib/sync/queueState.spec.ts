import { describe, expect, it } from 'vitest'
import { readCanonQueueLifeRules, type CanonQueueLifeRule } from './canonOracle'
import {
  actionRequiredLabelId,
  I6_HOLDING_CONTRACT,
  QUEUE_ACTION_REQUIRED_LABELS,
  QUEUE_STATES,
  queueStateId,
  type QueueActionRequiredLabel,
  type QueueStateId,
} from './queueState'

type ComparableLabel = { id: string }
type ComparableQueueState = {
  id: string
  actionRequiredLabels: readonly ComparableLabel[]
}
type ComparableHoldingElement = { id: string }
type ComparableHoldingContract = {
  id: string
  name: string
  elements: readonly ComparableHoldingElement[]
}

function expectQueueStateDefinitionToMatchCanon(
  states: readonly ComparableQueueState[],
  actionRequiredLabels: readonly ComparableLabel[],
  holdingContract: ComparableHoldingContract,
  canonRules: readonly CanonQueueLifeRule[],
): void {
  const canonStateIds = canonRules
    .filter((rule) => rule.kind === 'state')
    .map((rule) => rule.id)
  const holdingRule = canonRules.find(
    (rule) => rule.kind === 'holding-contract',
  )

  expect(canonRules).toHaveLength(5)
  expect(new Set(states.map((state) => state.id))).toEqual(
    new Set(canonStateIds),
  )
  expect(states).toHaveLength(canonStateIds.length)

  const actionRequiredState = states.find((state) => state.id === '要操作')
  const actionRequiredLabelIds = actionRequiredLabels.map((label) => label.id)
  expect(actionRequiredState).toBeDefined()
  // 3 下位ラベルはオラクル JSON に無く、正本 7-2 の本文が唯一の出所である。
  // 逐語の一致は機械化できないため、H-59 の人間逐行確認（ステップ 13 の逐語照合表）へ送る。
  expect(actionRequiredLabels).toHaveLength(3)
  expect(actionRequiredLabelIds.every((id) => id.length > 0)).toBe(true)
  expect(new Set(actionRequiredLabelIds).size).toBe(
    actionRequiredLabelIds.length,
  )
  expect(
    actionRequiredState?.actionRequiredLabels.map((label) => label.id),
  ).toEqual(actionRequiredLabelIds)
  expect(
    states
      .filter((state) => state.id !== '要操作')
      .every((state) => state.actionRequiredLabels.length === 0),
  ).toBe(true)

  expect(holdingRule).toBeDefined()
  if (!holdingRule || holdingRule.kind !== 'holding-contract') {
    throw new Error('R-QUEUE-LIFE の I6 保持契約がありません')
  }
  expect(holdingContract.id).toBe(holdingRule.id)
  expect(holdingContract.name).toBe(holdingRule.name)
  expect(holdingContract.elements).toHaveLength(11)
  expect(holdingContract.elements.map((element) => element.id)).toEqual(
    holdingRule.elements.map((element) => element.id),
  )
}

function cloneQueueStates(): ComparableQueueState[] {
  return QUEUE_STATES.map((state) => ({
    id: state.id,
    actionRequiredLabels: state.actionRequiredLabels.map((label) => ({
      id: label.id,
    })),
  }))
}

function cloneActionRequiredLabels(): ComparableLabel[] {
  return QUEUE_ACTION_REQUIRED_LABELS.map((label) => ({ id: label.id }))
}

function cloneHoldingContract(): ComparableHoldingContract {
  return {
    id: I6_HOLDING_CONTRACT.id,
    name: I6_HOLDING_CONTRACT.name,
    elements: I6_HOLDING_CONTRACT.elements.map((element) => ({
      id: element.id,
    })),
  }
}

describe('queueState', () => {
  it('状態と下位ラベルの未知 ID を fail-closed で拒否する', () => {
    const unsent: '未送信' = queueStateId('未送信')
    const revisionPending: '改訂待ち' = actionRequiredLabelId('改訂待ち')

    expect(unsent).toBe('未送信')
    expect(revisionPending).toBe('改訂待ち')
    expect(() => queueStateId('未知状態' as QueueStateId)).toThrow(
      'キュー状態 ID が存在しません',
    )
    expect(() =>
      actionRequiredLabelId('未知ラベル' as QueueActionRequiredLabel['id']),
    ).toThrow('要操作の下位ラベル ID が存在しません')
  })

  it('4 状態・要操作の3下位ラベル・I6の11要素を正本と照合する', () => {
    expectQueueStateDefinitionToMatchCanon(
      QUEUE_STATES,
      QUEUE_ACTION_REQUIRED_LABELS,
      I6_HOLDING_CONTRACT,
      readCanonQueueLifeRules(),
    )
  })

  it('変異: 状態を1つ落としたことを検出する', () => {
    const mutatedStates = cloneQueueStates()
    mutatedStates.splice(0, 1)

    expect(() =>
      expectQueueStateDefinitionToMatchCanon(
        mutatedStates,
        QUEUE_ACTION_REQUIRED_LABELS,
        I6_HOLDING_CONTRACT,
        readCanonQueueLifeRules(),
      ),
    ).toThrow()
  })

  it('変異: 要操作の下位ラベルを1つ落としたことを検出する', () => {
    const mutatedLabels = cloneActionRequiredLabels()
    mutatedLabels.splice(0, 1)

    expect(() =>
      expectQueueStateDefinitionToMatchCanon(
        QUEUE_STATES,
        mutatedLabels,
        I6_HOLDING_CONTRACT,
        readCanonQueueLifeRules(),
      ),
    ).toThrow()
  })

  it.each(
    I6_HOLDING_CONTRACT.elements.map(
      (element, index) => [index, element.id] as const,
    ),
  )('変異: I6 の「%s:%s」を落としたことを検出する', (index) => {
    const mutatedContract = cloneHoldingContract()
    const mutatedElements = [...mutatedContract.elements]
    mutatedElements.splice(index, 1)

    expect(() =>
      expectQueueStateDefinitionToMatchCanon(
        QUEUE_STATES,
        QUEUE_ACTION_REQUIRED_LABELS,
        { ...mutatedContract, elements: mutatedElements },
        readCanonQueueLifeRules(),
      ),
    ).toThrow()
  })
})
