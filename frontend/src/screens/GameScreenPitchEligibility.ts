// 第 1 期で許す 1 球の入力かどうかを判定する純関数。
//
// 判定するだけで確定はしない。結果の用途は画面の表示(入力欄の活性と、入力できない
// 理由の提示)に限る。本モジュールは永続キュー・送信経路・状況計算核のいずれにも
// 依存しない(docs/features/uf8-game-recording/plan.md のステップ 2)。
//
// 判定は記録者の観測だけから行い、推定しない。付録A-1 の OUT3-01〜03 の該当も、
// 付録A-3 の RBI-02〜05 の該当も、プレイ結果だけからは一意に決まらない現場の
// 時間的前後・因果・記録員判断であり、要件書 FR-003 が「自動推定せず、既定値も
// 置かず、記録者の観測入力を正とする」と定めているためである
// (docs/requirements/requirements-pitchlog-2026-07-22.md:233-234, 1171)。
//
// 観測が欠けている場合は「不可」へ倒す(fail-closed)。要件書 :233 と :234 が
// 「必要な走者の入力が 1 人分でも欠落していれば確定できない」と定めている。
//
// 打撃結果の語彙は管理者管理(要件書 4.0-3)で、画面は不透明な ID として扱う。
// したがって結果 ID そのものを判定の条件にせず、打球の発生という観測で区別する。

export const PITCH_INPUT_INELIGIBILITY = {
  /** 打球が発生した。インプレーの完全な入力は第 2 期。 */
  IN_PLAY_NOT_SUPPORTED: 'in-play-not-supported',
  /** 付録A-3 の RBI-02〜05 を判定するプレイ。打点の裁定は第 2 期。 */
  RBI_RULING_REQUIRED: 'rbi-ruling-required',
  /** 付録A-1 の OUT3-01〜03 に該当しない生還候補走者が居る。第 3 アウト時機の入力が要る。 */
  THIRD_OUT_TIMING_REQUIRED: 'third-out-timing-required',
  /** 打球の有無が観測されていない。 */
  BATTED_BALL_UNOBSERVED: 'batted-ball-unobserved',
  /** 打点の裁定の要否が観測されていない。 */
  RBI_RULING_UNOBSERVED: 'rbi-ruling-unobserved',
  /** 生還候補走者の観測の形が不正(走者キーの欠落・重複を含む)。 */
  SCORING_CANDIDATE_MALFORMED: 'scoring-candidate-malformed',
} as const

export type PitchInputIneligibility =
  (typeof PITCH_INPUT_INELIGIBILITY)[keyof typeof PITCH_INPUT_INELIGIBILITY]

/** 生還候補走者 1 人分の観測。走者キー付きで、走者ごとに別々に保持する(FR-003)。 */
export type ScoringCandidateObservation = {
  /** 走者キー。同一プレイの中で一意。 */
  runnerKey: string
  /**
   * 付録A-1 の OUT3-01〜03 のいずれかに該当すると記録者が観測したか。
   * 該当する走者は前後関係によらず得点無効なので、第 3 アウト時機を要求しない
   * (要件書 :233)。観測が無い場合は該当しない側へ倒す。
   */
  excludedByThirdOutRule: boolean
}

export type PitchInputObservation = {
  /** 打球が発生したか。FR-004 の打球位置入力の有無と同じ観測。 */
  battedBall: boolean
  /** 付録A-3 の RBI-02〜05 のいずれかを判定するプレイか。 */
  rbiRulingRequired: boolean
  /** 生還候補走者ごとの観測。1 人も居なければ空。 */
  scoringCandidateRunners: readonly ScoringCandidateObservation[]
}

export type PitchInputEligibility =
  | { eligible: true }
  | { eligible: false; reasons: readonly PitchInputIneligibility[] }

// 表示の並びを入力の順番で揺らさないための固定順。
const INELIGIBILITY_ORDER: readonly PitchInputIneligibility[] = Object.freeze([
  PITCH_INPUT_INELIGIBILITY.BATTED_BALL_UNOBSERVED,
  PITCH_INPUT_INELIGIBILITY.IN_PLAY_NOT_SUPPORTED,
  PITCH_INPUT_INELIGIBILITY.RBI_RULING_UNOBSERVED,
  PITCH_INPUT_INELIGIBILITY.RBI_RULING_REQUIRED,
  PITCH_INPUT_INELIGIBILITY.SCORING_CANDIDATE_MALFORMED,
  PITCH_INPUT_INELIGIBILITY.THIRD_OUT_TIMING_REQUIRED,
])

function isScoringCandidateObservation(
  value: unknown,
): value is ScoringCandidateObservation {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const candidate = value as Partial<ScoringCandidateObservation>
  return (
    typeof candidate.runnerKey === 'string' &&
    candidate.runnerKey.length > 0 &&
    typeof candidate.excludedByThirdOutRule === 'boolean'
  )
}

/**
 * 第 1 期で許す 1 球の入力かどうかを判定する。
 *
 * 確定はせず、永続追記・送信のいずれも起動しない。
 *
 * Args:
 *     observation: 記録者の観測。
 *
 * Returns:
 *     可否と、不可の場合の理由(固定順)。
 */
export function judgePitchInputEligibility(
  observation: PitchInputObservation,
): PitchInputEligibility {
  const reasons = new Set<PitchInputIneligibility>()

  if (typeof observation.battedBall !== 'boolean') {
    reasons.add(PITCH_INPUT_INELIGIBILITY.BATTED_BALL_UNOBSERVED)
  } else if (observation.battedBall) {
    reasons.add(PITCH_INPUT_INELIGIBILITY.IN_PLAY_NOT_SUPPORTED)
  }

  if (typeof observation.rbiRulingRequired !== 'boolean') {
    reasons.add(PITCH_INPUT_INELIGIBILITY.RBI_RULING_UNOBSERVED)
  } else if (observation.rbiRulingRequired) {
    reasons.add(PITCH_INPUT_INELIGIBILITY.RBI_RULING_REQUIRED)
  }

  const runners = observation.scoringCandidateRunners
  if (!Array.isArray(runners)) {
    reasons.add(PITCH_INPUT_INELIGIBILITY.SCORING_CANDIDATE_MALFORMED)
  } else {
    const runnerKeys = new Set<string>()
    for (const runner of runners) {
      if (!isScoringCandidateObservation(runner)) {
        reasons.add(PITCH_INPUT_INELIGIBILITY.SCORING_CANDIDATE_MALFORMED)
        // 形が不正な観測は「該当しない」と同じく第 3 アウト時機の入力を要する。
        reasons.add(PITCH_INPUT_INELIGIBILITY.THIRD_OUT_TIMING_REQUIRED)
        continue
      }
      if (runnerKeys.has(runner.runnerKey)) {
        reasons.add(PITCH_INPUT_INELIGIBILITY.SCORING_CANDIDATE_MALFORMED)
      }
      runnerKeys.add(runner.runnerKey)
      if (!runner.excludedByThirdOutRule) {
        reasons.add(PITCH_INPUT_INELIGIBILITY.THIRD_OUT_TIMING_REQUIRED)
      }
    }
  }

  if (reasons.size === 0) {
    return { eligible: true }
  }
  return {
    eligible: false,
    reasons: Object.freeze(
      INELIGIBILITY_ORDER.filter((reason) => reasons.has(reason)),
    ),
  }
}
