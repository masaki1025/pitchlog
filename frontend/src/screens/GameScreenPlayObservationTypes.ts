/** 単一計算側が指定する表示候補。ID に意味判定を持たせない。 */
export interface PlayObservationOption {
  id: string
  label: string
}

/** 必要な質問と選択肢は呼出元が決める。未選択は null。 */
export interface PlayObservationQuestion {
  key: string
  label: string
  options: readonly PlayObservationOption[]
  required: boolean
  multiple?: boolean
}

export interface RunnerObservationRequest {
  runnerKey: string
  displayName: string
  advanceResult?: PlayObservationQuestion
  destinationBase?: PlayObservationQuestion
  attemptedBase?: PlayObservationQuestion
  thirdOutTiming?: PlayObservationQuestion
  rbiRuling?: PlayObservationQuestion
  interferenceQuestions?: readonly PlayObservationQuestion[]
  officialScoringQuestions?: readonly PlayObservationQuestion[]
}

export interface PlayObservationCase {
  /** 座標は供給側の座標系の値を文字列として受ける。画面では変換しない。 */
  battedBall?: {
    fielderCandidates: readonly PlayObservationOption[]
    suggestedFielderId?: string | null
  }
  playResult?: PlayObservationQuestion
  runners: readonly RunnerObservationRequest[]
  rbiRuling?: PlayObservationQuestion
  interferenceQuestions?: readonly PlayObservationQuestion[]
  officialScoringQuestions?: readonly PlayObservationQuestion[]
}

export interface NonPitchActionRequest {
  id: string
  label: string
  observation: PlayObservationCase
}

/** 正式 wire DTO ではない、隔離された表示用入力要求。 */
export type PlayObservationRequest =
  | { contextKey: string; mode: 'pitch'; observation: PlayObservationCase }
  | {
      contextKey: string
      mode: 'non-pitch'
      actions: readonly NonPitchActionRequest[]
    }

export type ObservationAnswer = string | readonly string[] | null

/** payload の raw 観測。正式 wire DTO や確定イベントとして使わない。 */
export interface RawPlayObservation {
  contextKey: string
  mode: 'pitch' | 'non-pitch'
  actionId: string | null
  playResultId: string | null
  battedBall: {
    x: string | null
    y: string | null
    fielderId: string | null
  } | null
  runnerAdvanceOverridesByRunner: Record<
    string,
    { resultId: string | null; destinationBaseId: string | null }
  >
  runnerEventsByRunner: Record<
    string,
    {
      resultId: string | null
      destinationBaseId: string | null
      attemptedBaseId: string | null
    }
  >
  thirdOutTimingByRunner: Record<string, string | null>
  rbiRuling: {
    play: string | null
    byRunner: Record<string, string | null>
  }
  interferenceRuling: {
    play: Record<string, ObservationAnswer>
    byRunner: Record<string, Record<string, ObservationAnswer>>
  }
  officialScoringPayload: {
    play: Record<string, ObservationAnswer>
    byRunner: Record<string, Record<string, ObservationAnswer>>
  }
}
