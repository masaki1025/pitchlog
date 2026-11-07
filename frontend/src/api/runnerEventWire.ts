import type { RunnerOutcomeMap } from '../domain/runnerEvent'

/** 正式perPitchの今回供給範囲。値の書換や計算・認可を行わない。 */
export type RunnerPerPitch = Readonly<{
  kind: 'batting-result' | 'secondary-result' | 'runner-event'
  pitchEventKind: 'pitch-event' | 'non-pitch-event'
  resultId: string
  runnerEventPayload:
    | Readonly<{ kind: 'not-applicable' }>
    | Readonly<{
        kind: 'runner-event'
        event_kind: string
        by_runner: RunnerOutcomeMap
      }>
  runnerAdvanceOverridesByRunner:
    | Readonly<{ kind: 'not-applied' }>
    | Readonly<{ kind: 'overridden'; by_runner: RunnerOutcomeMap }>
  thirdOutObservation:
    | Readonly<{ kind: 'not-required' | 'none' }>
    | Readonly<{
        kind: 'other-third-out'
        out_person: Readonly<{ kind: 'official'; player_id: string }>
      }>
    | Readonly<{
        kind: 'missed-base-appeal'
        runner: Readonly<{ kind: 'official'; player_id: string }>
      }>
  thirdOutTimingByRunner: Readonly<
    Partial<
      Record<
        'first' | 'second' | 'third' | 'batter',
        'home-before-third-out' | 'not-before-third-out'
      >
    >
  >
  officialScoringPayload: Readonly<{ kind: 'no-error' }>
  interferenceRuling: Readonly<{ kind: 'not-required' }>
  rbi: Readonly<{
    doublePlayRelayError: 'not-required'
    runnerContinuityByRunner: Readonly<{ kind: 'not-required' }>
    wouldScoreWithoutErrorByRunner: Readonly<{ kind: 'not-required' }>
    cause_by_runner: Readonly<{ kind: 'not-required' }>
    restart_by_runner: Readonly<{ kind: 'not-required' }>
  }>
  homeTouchOrder: Readonly<{ kind: 'not-required' }>
}>
export type RunnerObservationWire = Readonly<{
  perPitch: RunnerPerPitch
  primaryResultId: string | null
}>
