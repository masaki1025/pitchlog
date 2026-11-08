import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import GameScreenInterferenceObservation from './GameScreenInterferenceObservation.vue'

const batter = '22222222-2222-4222-8222-222222222222'
const first = '33333333-3333-4333-8333-333333333333'
const props = {
  contextKey: 'game:checkpoint:1',
  batterId: batter,
  runners: [{ base: '1' as const, runnerId: first, label: '一塁走者' }],
}

it('打撃妨害は三塁走者の実企図が未入力なら裁定を出さない', async () => {
  const w = mount(GameScreenInterferenceObservation, {
    props: {
      ...props,
      resultId: 'secondary-result.batting-interference',
      runners: [
        ...props.runners,
        {
          base: '3' as const,
          runnerId: '44444444-4444-4444-8444-444444444444',
          label: '三塁走者',
        },
      ],
    },
  })
  await w.get('[data-testid="interference-confirm"]').setValue(true)
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w.get('[data-testid="interference-third-attempt"]').setValue('squeeze')
  expect(w.emitted('change')?.at(-1)?.[0]).toEqual({
    resultId: 'secondary-result.batting-interference',
    interferenceRuling: {
      kind: 'batting-interference',
      adopted: { kind: 'penalty-award' },
      third_base_scoring_attempt: { kind: 'observed', value: 'squeeze' },
    },
  })
  await w.setProps({ contextKey: 'game:checkpoint:2' })
  expect(w.emitted('change')?.at(-1)).toEqual([null])
})

it('走塁妨害は対象・授与塁・一塁前を選ぶまで保留する', async () => {
  const w = mount(GameScreenInterferenceObservation, {
    props: { ...props, resultId: 'secondary-result.obstruction' },
  })
  await w.get('[data-testid="interference-confirm"]').setValue(true)
  await w
    .get('[data-testid="obstruction-play-kind"]')
    .setValue('play-on-obstructed-runner')
  await w.get('[data-testid="obstruction-person"]').setValue('batter')
  await w.get('[data-testid="obstruction-award-batter"]').setValue('first')
  await w.get('[data-testid="obstruction-award-1"]').setValue('second')
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w.get('[data-testid="obstruction-before-first"]').setValue('yes')
  expect(w.emitted('change')?.at(-1)?.[0]).toMatchObject({
    interferenceRuling: {
      kind: 'obstruction',
      obstructed: {
        kind: 'batter',
        batter_id: { kind: 'official', player_id: batter },
      },
      awarded_destinations: [
        { destination: 'first' },
        { destination: 'second' },
      ],
      out_targets: [],
      batter_before_first: true,
    },
  })
})

it('一塁前の打者走者はno-play表記でも授与を要しアウトを送らない', async () => {
  const w = mount(GameScreenInterferenceObservation, {
    props: { ...props, resultId: 'secondary-result.obstruction' },
  })
  await w.get('[data-testid="interference-confirm"]').setValue(true)
  await w.get('[data-testid="obstruction-play-kind"]').setValue('no-play-on-obstructed-runner')
  await w.get('[data-testid="obstruction-person"]').setValue('batter')
  await w.get('[data-testid="obstruction-before-first"]').setValue('yes')
  await w.get('[data-testid="obstruction-award-batter"]').setValue('first')
  await w.get('[data-testid="obstruction-award-1"]').setValue('second')
  expect(w.emitted('change')?.at(-1)?.[0]).toMatchObject({
    interferenceRuling: { out_targets: [], batter_before_first: true },
  })
  await w.get('[data-testid="obstruction-award-1"]').setValue('none')
  await w.get('[data-testid="obstruction-out-1"]').setValue(true)
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w.get('[data-testid="obstruction-out-1"]').setValue(false)
  await w.get('[data-testid="obstruction-award-batter"]').setValue('none')
  expect(w.emitted('change')?.at(-1)).toEqual([null])
})

it('守備妨害は非空アウトと他走者の明示帰塁先を要する', async () => {
  const w = mount(GameScreenInterferenceObservation, {
    props: { ...props, resultId: 'secondary-result.offensive-interference' },
  })
  await w.get('[data-testid="interference-confirm"]').setValue(true)
  await w.get('[data-testid="offensive-return-1"]').setValue('first')
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w.get('input[type="checkbox"]:not([data-testid])').setValue(true)
  expect(w.emitted('change')?.at(-1)?.[0]).toMatchObject({
    interferenceRuling: {
      kind: 'offensive-interference',
      out_targets: [
        { kind: 'batter', batter_id: { kind: 'official', player_id: batter } },
      ],
      return_bases: [
        {
          person: {
            kind: 'runner',
            runner_id: { kind: 'official', player_id: first },
          },
          destination: 'first',
        },
      ],
    },
  })
})
