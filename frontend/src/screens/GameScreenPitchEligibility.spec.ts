import { describe, expect, it } from 'vitest'
import {
  judgePitchInputEligibility,
  PITCH_INPUT_INELIGIBILITY,
  type PitchInputObservation,
} from './GameScreenPitchEligibility'
import eligibilitySource from './GameScreenPitchEligibility.ts?raw'

function observation(
  overrides: Partial<PitchInputObservation> = {},
): PitchInputObservation {
  return {
    battedBall: false,
    rbiRulingRequired: false,
    scoringCandidateRunners: [],
    ...overrides,
  }
}

describe('第 1 期で許す 1 球の入力', () => {
  it('打球がなく、打点の裁定が要らず、生還候補走者も居なければ可とする', () => {
    expect(judgePitchInputEligibility(observation())).toEqual({
      eligible: true,
    })
  })

  it('生還候補走者が全員 OUT3-01〜03 に該当するなら可とする', () => {
    const result = judgePitchInputEligibility(
      observation({
        scoringCandidateRunners: [
          { runnerKey: 'runner-3b', excludedByThirdOutRule: true },
          { runnerKey: 'runner-2b', excludedByThirdOutRule: true },
        ],
      }),
    )

    expect(result).toEqual({ eligible: true })
  })
})

describe('第 1 期で確定させない入力', () => {
  it('RBI-02〜05 を判定するプレイは不可とする', () => {
    const result = judgePitchInputEligibility(
      observation({ rbiRulingRequired: true }),
    )

    expect(result).toEqual({
      eligible: false,
      reasons: [PITCH_INPUT_INELIGIBILITY.RBI_RULING_REQUIRED],
    })
  })

  it('OUT3-01〜03 に該当しない生還候補走者が 1 人でも居れば不可とする', () => {
    const result = judgePitchInputEligibility(
      observation({
        scoringCandidateRunners: [
          { runnerKey: 'runner-3b', excludedByThirdOutRule: true },
          { runnerKey: 'runner-2b', excludedByThirdOutRule: false },
        ],
      }),
    )

    expect(result).toEqual({
      eligible: false,
      reasons: [PITCH_INPUT_INELIGIBILITY.THIRD_OUT_TIMING_REQUIRED],
    })
  })

  it('打球が発生したプレイは不可とする（インプレーは第 2 期）', () => {
    const result = judgePitchInputEligibility(observation({ battedBall: true }))

    expect(result).toEqual({
      eligible: false,
      reasons: [PITCH_INPUT_INELIGIBILITY.IN_PLAY_NOT_SUPPORTED],
    })
  })

  it('不可の理由をすべて返し、並びは入力の順番で変わらない', () => {
    const result = judgePitchInputEligibility(
      observation({
        battedBall: true,
        rbiRulingRequired: true,
        scoringCandidateRunners: [
          { runnerKey: 'runner-1b', excludedByThirdOutRule: false },
        ],
      }),
    )

    expect(result).toEqual({
      eligible: false,
      reasons: [
        PITCH_INPUT_INELIGIBILITY.IN_PLAY_NOT_SUPPORTED,
        PITCH_INPUT_INELIGIBILITY.RBI_RULING_REQUIRED,
        PITCH_INPUT_INELIGIBILITY.THIRD_OUT_TIMING_REQUIRED,
      ],
    })
  })
})

describe('観測が欠けているときの扱い', () => {
  it('打球の有無が観測されていなければ不可とする', () => {
    const result = judgePitchInputEligibility(
      observation({ battedBall: undefined as unknown as boolean }),
    )

    expect(result).toEqual({
      eligible: false,
      reasons: [PITCH_INPUT_INELIGIBILITY.BATTED_BALL_UNOBSERVED],
    })
  })

  it('打点の裁定の要否が観測されていなければ不可とする', () => {
    const result = judgePitchInputEligibility(
      observation({ rbiRulingRequired: undefined as unknown as boolean }),
    )

    expect(result).toEqual({
      eligible: false,
      reasons: [PITCH_INPUT_INELIGIBILITY.RBI_RULING_UNOBSERVED],
    })
  })

  it('走者の観測の形が不正なら、第 3 アウト時機の入力が要るものとして不可にする', () => {
    const result = judgePitchInputEligibility(
      observation({
        scoringCandidateRunners: [{ runnerKey: 'runner-3b' } as never],
      }),
    )

    expect(result).toEqual({
      eligible: false,
      reasons: [
        PITCH_INPUT_INELIGIBILITY.SCORING_CANDIDATE_MALFORMED,
        PITCH_INPUT_INELIGIBILITY.THIRD_OUT_TIMING_REQUIRED,
      ],
    })
  })

  it('走者キーが重複する観測は不正として扱う', () => {
    const result = judgePitchInputEligibility(
      observation({
        scoringCandidateRunners: [
          { runnerKey: 'runner-3b', excludedByThirdOutRule: true },
          { runnerKey: 'runner-3b', excludedByThirdOutRule: true },
        ],
      }),
    )

    expect(result).toEqual({
      eligible: false,
      reasons: [PITCH_INPUT_INELIGIBILITY.SCORING_CANDIDATE_MALFORMED],
    })
  })

  it('走者の観測が配列でなければ不正として扱う', () => {
    const result = judgePitchInputEligibility(
      observation({
        scoringCandidateRunners: undefined as never,
      }),
    )

    expect(result).toEqual({
      eligible: false,
      reasons: [PITCH_INPUT_INELIGIBILITY.SCORING_CANDIDATE_MALFORMED],
    })
  })
})

describe('判定が確定の経路を起動しないこと', () => {
  it('判定モジュールが何も import しない（永続キュー・送信・計算核に依存しない）', () => {
    const importLines = eligibilitySource
      .split(/\r\n?|\n/)
      .filter((line) => /^\s*import\b/.test(line))

    expect(importLines).toEqual([])
  })

  it.each([
    'durableQueue',
    'clientDiscipline',
    'appendUnderQueueDiscipline',
    'singleWriter',
    'queueTransition',
    'fetch(',
    'XMLHttpRequest',
  ])('判定モジュールが %s を参照しない', (identifier) => {
    expect(eligibilitySource).not.toContain(identifier)
  })

  it('観測オブジェクトを変更しない', () => {
    const source = observation({
      scoringCandidateRunners: [
        { runnerKey: 'runner-1b', excludedByThirdOutRule: false },
      ],
    })
    const snapshot = structuredClone(source)

    judgePitchInputEligibility(source)

    expect(source).toEqual(snapshot)
  })
})
