import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { cwd } from 'node:process'
import { describe, expect, it } from 'vitest'
import {
  parseFailureScenarioContract,
  type FailureScenarioContract,
  type FailureScenarioObservation,
} from '../lib/sync/failureScenarioContract'
import { deriveFailureReaction } from './GameScreenFailureReaction'

const FIXTURE_DIRECTORY = resolve(
  cwd(),
  '../tests/fixtures/sync-protocol-failures',
)

/** 第 1 期で画面の反応を確かめる 3 シナリオ(design.md 7 節)。 */
const SCENARIO_FILES = {
  'leader-freeze-reelection': 'leader-freeze-reelection_v2.json',
  'waiting-input-not-accepted': 'waiting-input-not-accepted_v2.json',
  'durable-append-failure': 'durable-append-failure_v2.json',
} as const

function loadContract(
  scenarioId: keyof typeof SCENARIO_FILES,
): FailureScenarioContract {
  const fileName = SCENARIO_FILES[scenarioId]
  const raw = readFileSync(resolve(FIXTURE_DIRECTORY, fileName), 'utf8')
  const contract = parseFailureScenarioContract(fileName, raw)
  expect(contract.scenarioId).toBe(scenarioId)
  return contract
}

function observationsOf(
  scenarioId: keyof typeof SCENARIO_FILES,
): readonly FailureScenarioObservation[] {
  return loadContract(scenarioId).cases.flatMap((item) => item.observations)
}

function observationAt(
  scenarioId: keyof typeof SCENARIO_FILES,
  observationPoint: string,
): FailureScenarioObservation {
  const found = observationsOf(scenarioId).find((observation) =>
    Object.is(observation.observationPoint, observationPoint),
  )
  if (!found) {
    throw new Error(`観測点が契約資産にありません: ${observationPoint}`)
  }
  return found
}

describe('E5 の 3 シナリオに共通する画面の反応', () => {
  it.each(Object.keys(SCENARIO_FILES) as (keyof typeof SCENARIO_FILES)[])(
    '%s のどの観測点でも受理成功として表示しない',
    (scenarioId) => {
      const observations = observationsOf(scenarioId)

      expect(observations.length).toBeGreaterThan(0)
      for (const observation of observations) {
        expect(deriveFailureReaction(observation).showsAcceptance).toBe(false)
      }
    },
  )
})

describe('待機中入力の非受理', () => {
  it('記録できない旨を Q2-b で示し、ロック取得後の再入力を案内する', () => {
    const reaction = deriveFailureReaction(
      observationAt('waiting-input-not-accepted', 'ロック待機中の確定入力後'),
    )

    expect(reaction.blockedNoticeId).toBe('Q2-b')
    expect(reaction.offersReinput).toBe(true)
    expect(reaction.requiresReinput).toBe(false)
  })
})

describe('永続追記失敗', () => {
  it('再入力できることを示し、同じ次番号で再試行できる', () => {
    const reaction = deriveFailureReaction(
      observationAt('durable-append-failure', '永続追記失敗直後'),
    )

    expect(reaction.offersReinput).toBe(true)
    expect(reaction.retriesWithSameNextD1).toBe(true)
    expect(reaction.blockedNoticeId).toBeUndefined()
  })
})

describe('フリーズ後の再選出', () => {
  it('旧タブ終了前は再入力を要求せず、記録再開も示さない', () => {
    const reaction = deriveFailureReaction(
      observationAt('leader-freeze-reelection', '旧タブ終了前'),
    )

    expect(reaction.requiresReinput).toBe(false)
    expect(reaction.recordingResumed).toBe(false)
  })

  it('再選出後は再検証を経た記録再開を示し、再入力を要求しない', () => {
    const reaction = deriveFailureReaction(
      observationAt('leader-freeze-reelection', '待機タブ再選出後'),
    )

    expect(reaction.recordingResumed).toBe(true)
    expect(reaction.requiresReinput).toBe(false)
  })
})

describe('導出が観測値を実際に読んでいること', () => {
  it('受理成功・再入力の要求が真なら真を返す（定数化を検出する）', () => {
    const reaction = deriveFailureReaction({
      observationPoint: '合成の観測点',
      fields: {
        acceptanceDisplay: {
          shownAsAccepted: true,
          recordingResumedAfterRevalidation: true,
        },
        reinputAvailability: {
          required: true,
          possible: true,
          retryWithSameNextD1: true,
        },
      },
    })

    expect(reaction).toEqual({
      showsAcceptance: true,
      recordingResumed: true,
      offersReinput: true,
      requiresReinput: true,
      retriesWithSameNextD1: true,
      blockedNoticeId: undefined,
    })
  })

  it('待機側の受理表示だけが真の場合も受理として扱う', () => {
    expect(
      deriveFailureReaction({
        observationPoint: '合成の観測点',
        fields: { acceptanceDisplay: { waitingInputShownAsAccepted: true } },
      }).showsAcceptance,
    ).toBe(true)
  })

  it('読んでいるキー名が契約資産に実在する（改名を検出する）', () => {
    const corpus = (
      Object.keys(SCENARIO_FILES) as (keyof typeof SCENARIO_FILES)[]
    )
      .map((scenarioId) =>
        readFileSync(
          resolve(FIXTURE_DIRECTORY, SCENARIO_FILES[scenarioId]),
          'utf8',
        ),
      )
      .join('\n')

    for (const key of [
      'acceptanceDisplay',
      'reinputAvailability',
      'shownAsAccepted',
      'waitingInputShownAsAccepted',
      'recordingResumedAfterRevalidation',
      'possible',
      'afterLockAcquisition',
      'required',
      'retryWithSameNextD1',
      'noticeId',
    ]) {
      expect(corpus).toContain(key)
    }
  })
})

describe('観測値が欠けているときの扱い', () => {
  it('観測値が無ければ受理成功も再入力の導線も出さない', () => {
    const reaction = deriveFailureReaction({
      observationPoint: '空の観測点',
      fields: {},
    })

    expect(reaction).toEqual({
      showsAcceptance: false,
      recordingResumed: false,
      offersReinput: false,
      requiresReinput: false,
      retriesWithSameNextD1: false,
      blockedNoticeId: undefined,
    })
  })

  it.each([
    ['真偽値でない', { shownAsAccepted: 'true' }],
    ['配列', []],
    ['null', null],
  ])('acceptanceDisplay が %s なら受理成功として扱わない', (_label, value) => {
    const reaction = deriveFailureReaction({
      observationPoint: '壊れた観測点',
      fields: { acceptanceDisplay: value },
    })

    expect(reaction.showsAcceptance).toBe(false)
  })

  it('カタログに無い通知 ID は採らない', () => {
    const reaction = deriveFailureReaction({
      observationPoint: '未知の通知',
      fields: { acceptanceDisplay: { noticeId: 'Q999' } },
    })

    expect(reaction.blockedNoticeId).toBeUndefined()
  })
})
