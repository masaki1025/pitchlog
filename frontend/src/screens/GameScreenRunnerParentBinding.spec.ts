import { expect, it } from 'vitest'
import cases from '../../../docs/features/mvp-runner-operations-connection/candidate-cases.json'
import {
  isRunnerObservation,
  type RunnerObservationWire,
} from '../api/runnerEventWire'
import {
  runnerObservationMatchesParent,
  type PlayScreenObservation,
} from './GameScreenOrdinaryPitchProvider'
function child(index: number): RunnerObservationWire {
  const raw: unknown = structuredClone(
    cases.cases[index]!.request.t1.runnerObservation,
  )
  if (!isRunnerObservation(raw)) throw Error('作者の閉観測候補が不一致')
  return raw
}
const ball: PlayScreenObservation = {
  resultId: 'batting-result.ball',
  pitchTypeKey: 'pitch-type.straight',
  screenX: 100,
  screenY: 100,
  view: 'catcher',
  pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
  stance: null,
  battingSide: null,
}
it('親ball/子SO05はprimaryResultId=nullでも拒否し、一致SO05は通す', () => {
  const so = child(2)
  expect(runnerObservationMatchesParent(ball, so)).toBe(false)
  expect(
    runnerObservationMatchesParent(
      { ...ball, resultId: 'batting-result.strikeout-double-play' },
      so,
    ),
  ).toBe(true)
})
it('WP/PBは実主結果を比較し、子副結果を親の打撃結果へ偽装しない', () => {
  for (const index of [3, 4]) {
    const wp = child(index)
    expect(runnerObservationMatchesParent(ball, wp)).toBe(true)
    expect(
      runnerObservationMatchesParent(
        { ...ball, resultId: 'batting-result.called-pitch' },
        wp,
      ),
    ).toBe(false)
  }
})
it('投球を伴う盗塁の親結果/実主結果を同じ値に束縛する', () => {
  const steal = child(6)
  expect(runnerObservationMatchesParent(ball, steal)).toBe(true)
  expect(
    runnerObservationMatchesParent(
      { ...ball, resultId: 'batting-result.foul' },
      steal,
    ),
  ).toBe(false)
})
it('非投球には親の架空ballや座標を要求しないが、SO05を非投球へ落とせない', () => {
  const pickoff = child(0)
  expect(
    runnerObservationMatchesParent(
      { kind: 'non-pitch-event', runnerEvent: pickoff },
      pickoff,
    ),
  ).toBe(true)
  expect(runnerObservationMatchesParent(ball, pickoff)).toBe(false)
  const so = child(2)
  expect(
    runnerObservationMatchesParent(
      { kind: 'non-pitch-event', runnerEvent: so },
      so,
    ),
  ).toBe(false)
})
