import { ordinaryStateSupported } from './ordinaryState'
import type {
  BattingOrderBySide,
  Derived,
  Rule,
  Scoreboard,
  StateFields,
} from './stateTypes'

/** 無走者で観測を閉じる最初の4安打。公開wireの型ではない。 */
export type BattedHitResultId =
  | 'batting-result.single'
  | 'batting-result.double'
  | 'batting-result.triple'
  | 'batting-result.home-run'

/** 結果から推定せず、記録者が確定した無併発の観測。 */
export type BattedHitObservation = {
  eventKind: 'batting-result'
  resultId: BattedHitResultId
  pitchEventKind: 'pitch-event'
  officialScoringPayload: 'no-error'
  interferenceRuling: 'not-required'
  runnerAdvanceOverrides: 'not-applied'
  thirdOutObservation: 'none'
}

/** 旧公開Derivedを広げず、新操作で両side cursorを保持する。 */
export type BattedHitDerived = Derived & {
  after: {
    stateFields: StateFields
    scoreboard: Scoreboard
    battingOrderBySide: BattingOrderBySide
  }
}

const OBSERVATION_KEYS: Array<string> = [
  'eventKind',
  'resultId',
  'pitchEventKind',
  'officialScoringPayload',
  'interferenceRuling',
  'runnerAdvanceOverrides',
  'thirdOutObservation',
]

type QualifiedBattedHitRule = Rule & { resultId: BattedHitResultId }

/** 4結果と実観測/状態が一致した場合だけ共通核へ渡す規則を作る。 */
export function battedHitRule(
  before: StateFields,
  board: Scoreboard,
  observation: unknown,
  cursors: BattingOrderBySide,
): QualifiedBattedHitRule | null {
  if (
    typeof observation !== 'object' ||
    observation === null ||
    Array.isArray(observation) ||
    !Object.getOwnPropertySymbols(observation).every(() => false) ||
    !Object.getOwnPropertyNames(observation).every((key) =>
      OBSERVATION_KEYS.includes(key),
    ) ||
    !OBSERVATION_KEYS.every((key) => {
      const field = Object.getOwnPropertyDescriptor(observation, key)
      return typeof field === 'object' && Object.hasOwn(field, 'value')
    })
  )
    return null
  const value = observation as Record<string, unknown>
  let activeOrder = cursors.away
  if (before.half === 'bottom') activeOrder = cursors.home
  if (
    value.eventKind !== 'batting-result' ||
    value.pitchEventKind !== 'pitch-event' ||
    value.officialScoringPayload !== 'no-error' ||
    value.interferenceRuling !== 'not-required' ||
    value.runnerAdvanceOverrides !== 'not-applied' ||
    value.thirdOutObservation !== 'none' ||
    ![
      before.inning,
      before.outs,
      before.battingOrder,
      before.strikes,
      before.balls,
      before.home,
      before.away,
      board.home,
      board.away,
      board.hits,
      board.errors,
      board.strikeouts,
      board.walks,
      cursors.away,
      cursors.home,
    ].every((number) => typeof number === 'bigint') ||
    !ordinaryStateSupported(before, board) ||
    before.runners !== 'empty' ||
    before.tiebreakActive !== false ||
    before.strikes < 0n ||
    before.strikes > 2n ||
    before.balls < 0n ||
    before.balls > 3n ||
    before.home !== board.home ||
    before.away !== board.away ||
    cursors.away < 1n ||
    cursors.away > 9n ||
    cursors.home < 1n ||
    cursors.home > 9n ||
    activeOrder !== before.battingOrder
  )
    return null
  const resultId = value.resultId
  let base: bigint
  switch (resultId) {
    case 'batting-result.single':
      base = 1n
      break
    case 'batting-result.double':
      base = 2n
      break
    case 'batting-result.triple':
      base = 3n
      break
    case 'batting-result.home-run':
      base = 0n
      break
    default:
      return null
  }
  let batter: 'score' | 'reach' = 'reach'
  if (base === 0n) batter = 'score'
  return {
    resultId,
    pa: true,
    batter,
    batterBase: base,
    outs: 0n,
    targets: [],
    advance: 'hold_all',
    step: 0n,
    explicit: {},
    strikeEffect: 'reset',
    strikeDelta: 0n,
    ballEffect: 'reset',
    ballDelta: 0n,
  }
}
