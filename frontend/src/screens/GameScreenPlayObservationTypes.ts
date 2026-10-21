/** 単一計算側が指定する表示候補。ID に意味判定を持たせない。 */
export interface PlayObservationOption {
  id: string
  label: string
}

/** 必要な質問と選択肢は呼出元が決める。未選択は null。 */
interface ObservationQuestionBase {
  key: string
  label: string
  options: readonly PlayObservationOption[]
  required: boolean
}

export interface SingleObservationQuestion extends ObservationQuestionBase {
  multiple?: false
}

export interface MultipleObservationQuestion extends ObservationQuestionBase {
  multiple: true
}

export type PlayObservationQuestion =
  SingleObservationQuestion | MultipleObservationQuestion

export interface RunnerObservationRequest {
  runnerKey: string
  displayName: string
  advanceResult?: SingleObservationQuestion
  destinationBase?: SingleObservationQuestion
  attemptedBase?: SingleObservationQuestion
  thirdOutTiming?: SingleObservationQuestion
  rbiRuling?: SingleObservationQuestion
  interferenceQuestions?: readonly PlayObservationQuestion[]
  officialScoringQuestions?: readonly PlayObservationQuestion[]
}

interface ObservationCaseBase {
  runners: readonly RunnerObservationRequest[]
  rbiRuling?: SingleObservationQuestion
  interferenceQuestions?: readonly PlayObservationQuestion[]
  officialScoringQuestions?: readonly PlayObservationQuestion[]
}

export interface PitchObservationCase extends ObservationCaseBase {
  /** 座標は供給側の座標系の値を文字列として受ける。画面では変換しない。 */
  battedBall?: {
    fielderCandidates: readonly PlayObservationOption[]
    suggestedFielderId?: string | null
  }
  playResult?: SingleObservationQuestion
}

/** 非投球の要求に打撃結果・打球欄を混入させない。 */
export interface NonPitchObservationCase extends ObservationCaseBase {
  playResult?: never
  battedBall?: never
}

export type PlayObservationCase = PitchObservationCase | NonPitchObservationCase

export interface NonPitchActionRequest {
  id: string
  label: string
  observation: NonPitchObservationCase
}

/** 正式 wire DTO ではない、隔離された表示用入力要求。 */
export type PlayObservationRequest =
  | { contextKey: string; mode: 'pitch'; observation: PitchObservationCase }
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
    {
      resultId: string | null
      destinationBaseId: string | null
      attemptedBaseId: string | null
    }
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
