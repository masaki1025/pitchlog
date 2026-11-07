import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Panel from './GameScreenRunnerEventObservation.vue'
const id = '10000000-0000-0000-0000-000000000299'
const pitcher = '10000000-0000-0000-0000-000000000310'
const runner = {
  base: '1' as const,
  runnerId: id,
  responsiblePitcherId: pitcher,
}
const make = () =>
  mount(Panel, {
    props: {
      runners: [runner],
      primaryResultId: 'batting-result.ball',
      sourceKey: 'confirmed-source:1',
    },
  })
it('未確認走者/原因/失策判定を既定観測にしない', async () => {
  const w = make()
  await w.get('[data-testid="runner-observation-confirm"]').trigger('click')
  expect(w.emitted('confirmed')).toBeUndefined()
  expect(w.get('[role="alert"]').text()).toContain('確認')
})
it('記録者の非投球盗塁の実結果をsource IDでそのまま確定する', async () => {
  const w = make()
  await w
    .get('[data-testid="runner-operation-kind"]')
    .setValue('steal-nonpitch')
  await w.get('[data-testid="runner-1-outcome"]').setValue('safe-advance')
  await w.get('[data-testid="runner-1-destination"]').setValue('second')
  await w.get('[data-testid="runner-third-out"]').setValue('none')
  await w.get('[data-testid="runner-no-error"]').setValue(true)
  await w.get('[data-testid="runner-observation-confirm"]').trigger('click')
  expect(w.emitted('confirmed')?.[0]?.[0]).toEqual({
    primaryResultId: null,
    perPitch: {
      kind: 'runner-event',
      pitchEventKind: 'non-pitch-event',
      resultId: 'strategy-category.steal',
      runnerEventPayload: {
        kind: 'runner-event',
        event_kind: 'strategy-category.steal',
        by_runner: {
          first: {
            kind: 'safe-advance',
            runner: { kind: 'official', player_id: id },
            destination: 'second',
          },
        },
      },
      runnerAdvanceOverridesByRunner: { kind: 'not-applied' },
      thirdOutObservation: { kind: 'none' },
      thirdOutTimingByRunner: {},
      officialScoringPayload: { kind: 'no-error' },
      interferenceRuling: { kind: 'not-required' },
      rbi: {
        doublePlayRelayError: 'not-required',
        runnerContinuityByRunner: { kind: 'not-required' },
        wouldScoreWithoutErrorByRunner: { kind: 'not-required' },
        cause_by_runner: { kind: 'not-required' },
        restart_by_runner: { kind: 'not-required' },
      },
      homeTouchOrder: { kind: 'not-required' },
    },
  })
  expect(w.text()).not.toContain(id)
})
it('アウトには企図塁と原因が必要で、牽制死へ推測しない', async () => {
  const w = make()
  await w
    .get('[data-testid="runner-operation-kind"]')
    .setValue('pitcher-pickoff-destination.first')
  await w.get('[data-testid="runner-1-outcome"]').setValue('out')
  await w.get('[data-testid="runner-1-destination"]').setValue('first')
  await w.get('[data-testid="runner-third-out"]').setValue('not-required')
  await w.get('[data-testid="runner-no-error"]').setValue(true)
  await w.get('[data-testid="runner-observation-confirm"]').trigger('click')
  expect(w.emitted('confirmed')).toBeUndefined()
  await w.get('[data-testid="runner-1-cause"]').setValue('pitcher-pickoff-out')
  await w.get('[data-testid="runner-observation-confirm"]').trigger('click')
  expect(w.emitted('confirmed')).toHaveLength(1)
})
it('再取得でrunnerが変われば旧観測の確認を引き継がない', async () => {
  const w = make()
  await w.get('[data-testid="runner-no-error"]').setValue(true)
  await w.get('[data-testid="runner-1-outcome"]').setValue('hold')
  await w.setProps({
    runners: [{ ...runner, runnerId: '10000000-0000-0000-0000-000000000298' }],
  })
  expect(
    (w.get('[data-testid="runner-no-error"]').element as HTMLInputElement)
      .checked,
  ).toBe(false)
  expect(
    (w.get('[data-testid="runner-1-outcome"]').element as HTMLSelectElement)
      .value,
  ).toBe('')
})
describe('表示の既定は観測の確定ではない', () => {
  it('空走者で古い観測を発行しない', async () => {
    const w = make()
    await w.setProps({ runners: [] })
    await w.get('[data-testid="runner-observation-confirm"]').trigger('click')
    expect(w.emitted('confirmed')).toBeUndefined()
  })
})

it('同じ走者IDでも新sourceでは旧確認を再使用しない', async () => {
  const w = make()
  await w.get('[data-testid="runner-no-error"]').setValue(true)
  await w.get('[data-testid="runner-1-outcome"]').setValue('hold')
  await w.setProps({ sourceKey: 'confirmed-source:2' })
  expect(
    (w.get('[data-testid="runner-no-error"]').element as HTMLInputElement)
      .checked,
  ).toBe(false)
  expect(
    (w.get('[data-testid="runner-1-outcome"]').element as HTMLSelectElement)
      .value,
  ).toBe('')
})

it('SO05を選んだ時点で親主結果の変更を求め、ballのまま確定しない', async () => {
  const w = make()
  await w
    .get('[data-testid="runner-operation-kind"]')
    .setValue('batting-result.strikeout-double-play')
  expect(w.emitted('select-primary-result')).toEqual([
    ['batting-result.strikeout-double-play'],
  ])
  await w.get('[data-testid="runner-1-outcome"]').setValue('out')
  await w.get('[data-testid="runner-1-destination"]').setValue('second')
  await w.get('[data-testid="runner-1-cause"]').setValue('caught-stealing')
  await w.get('[data-testid="runner-third-out"]').setValue('not-required')
  await w.get('[data-testid="runner-no-error"]').setValue(true)
  await w.get('[data-testid="runner-observation-confirm"]').trigger('click')
  expect(w.emitted('confirmed')).toBeUndefined()
  expect(w.get('[role="alert"]').text()).toContain('主結果')
  await w.setProps({ primaryResultId: 'batting-result.strikeout-double-play' })
  await w.get('[data-testid="runner-observation-confirm"]').trigger('click')
  const p = w.emitted('confirmed')?.[0]?.[0]
  expect(p).toMatchObject({
    primaryResultId: null,
    perPitch: {
      kind: 'batting-result',
      resultId: 'batting-result.strikeout-double-play',
      pitchEventKind: 'pitch-event',
    },
  })
  await w.setProps({ primaryResultId: 'batting-result.ball' })
  expect(
    (
      w.get('[data-testid="runner-operation-kind"]')
        .element as HTMLSelectElement
    ).value,
  ).toBe('')
  await w.get('[data-testid="runner-observation-confirm"]').trigger('click')
  expect(w.emitted('confirmed')).toHaveLength(1)
})
