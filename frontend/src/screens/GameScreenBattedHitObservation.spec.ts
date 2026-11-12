import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, disposePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as options from '../api/battedBallOptions'
import GameScreenBattedHitObservation from './GameScreenBattedHitObservation.vue'
let pinia: Pinia
beforeEach(() => {
  options.clearBattedBallOptionsCache()
  pinia = createPinia()
  setActivePinia(pinia)
  vi.spyOn(options, 'readBattedBallOptions').mockResolvedValue({
    items: [{ key: 'observed.line', display_name: '観測語彙' }],
    next_cursor: null,
  })
})
afterEach(() => {
  disposePinia(pinia)
  vi.restoreAllMocks()
})
const props = {
  contextKey: 'game:checkpoint:1',
  resultId: 'batting-result.single' as const,
  beforeOuts: '0' as const,
  batterId: '22222222-2222-4222-8222-222222222222',
  fielders: [{ id: '11111111-1111-4111-8111-111111111111', label: '右翼手' }],
}
const fields = [
  'typeKey',
  'strengthKey',
  'hitX',
  'hitY',
  'rawFielderPosition',
  'resolvedFielderId',
]
async function explicitNull(w: ReturnType<typeof mount>) {
  for (const key of fields)
    await w.get(`[data-testid="batted-mode-${key}"]`).setValue('unobserved')
}
async function confirm(w: ReturnType<typeof mount>) {
  for (const q of w.findAll('[data-question-key] select'))
    await q.setValue('confirmed')
}
it('凡打死の第3アウトは打者走者の一塁到達前を確認して公式refで保存する', async () => {
  const w = mount(GameScreenBattedHitObservation, {
    props: {
      ...props,
      resultId: 'batting-result.batted-out',
      beforeOuts: '2',
    },
  })
  await flushPromises()
  expect(w.text()).toContain('第3アウトは打者走者の一塁到達前')
  await explicitNull(w)
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await confirm(w)
  expect(w.emitted('change')?.at(-1)?.[0]).toMatchObject({
    resultId: 'batting-result.batted-out',
    thirdOutObservation: {
      kind: 'batter-before-first',
      batter: { kind: 'official', player_id: props.batterId },
    },
  })
  await w.setProps({ runners: [{ base: '1', label: '一塁走者' }] })
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  w.unmount()
})
it('打撃妨害で実プレイ採用は同結果IDと三塁企図の明示値だけを出す', async () => {
  const w = mount(GameScreenBattedHitObservation, {
    props: {
      ...props,
      adoptInterference: true,
      runners: [{ base: '3', label: '三塁走者' }],
    },
  })
  await flushPromises()
  await explicitNull(w)
  await w.get('[data-testid="batted-runner-3-destination"]').setValue('hold')
  await w.get('[data-testid="batted-runner-confirmed"]').setValue(true)
  await confirm(w)
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w
    .get('[data-testid="batted-interference-third-attempt"]')
    .setValue('none')
  expect(w.emitted('change')?.at(-1)?.[0]).toMatchObject({
    resultId: 'batting-result.single',
    interferenceRuling: {
      kind: 'batting-interference',
      adopted: { kind: 'play-result', resultId: 'batting-result.single' },
      third_base_scoring_attempt: { kind: 'observed', value: 'none' },
    },
  })
  await w.setProps({ adoptInterference: false })
  expect(w.emitted('change')?.at(-1)).toEqual([null])
})
it('走者の実到達を欠いた凡打・犠飛を閉じ、確認値だけをV7へ出す', async () => {
  const w = mount(GameScreenBattedHitObservation, {
    props: {
      ...props,
      resultId: 'batting-result.sacrifice-fly',
      runners: [{ base: '3', label: '三塁走者' }],
    },
  })
  await flushPromises()
  await explicitNull(w)
  await confirm(w)
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w.get('[data-testid="batted-runner-3-destination"]').setValue('4')
  await w.get('[data-testid="batted-runner-confirmed"]').setValue(true)
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w
    .get('[data-testid="batted-runner-3-rbi-cause"]')
    .setValue('stopped-and-restarted')
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w.get('[data-testid="batted-runner-confirmed"]').setValue(true)
  expect(w.emitted('change')?.at(-1)?.[0]).toMatchObject({
    resultId: 'batting-result.sacrifice-fly',
    runnerAdvanceOverridesByRunner: {
      kind: 'applied',
      overrides: [{ runnerBase: '3', destination: '4' }],
    },
    thirdOutObservation: { kind: 'none' },
    rbiRulingByRunner: { '3': 'stopped-and-restarted' },
  })
  await w
    .get('[data-testid="batted-runner-3-rbi-cause"]')
    .setValue('ordinary-play')
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w.setProps({ resultId: 'batting-result.batted-out', beforeOuts: '2' })
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  w.unmount()
})
it('併殺は実一塁走者IDと封殺観測を確認した時だけV7へ出す', async () => {
  const runnerId = '10000000-0000-0000-0000-000000000065'
  const w = mount(GameScreenBattedHitObservation, {
    props: {
      ...props,
      resultId: 'batting-result.double-play',
      runners: [{ base: '1', label: '一塁走者', runnerId }],
    },
  })
  await flushPromises()
  await explicitNull(w)
  await confirm(w)
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w.get('[data-testid="batted-runner-confirmed"]').setValue(true)
  expect(w.emitted('change')?.at(-1)?.[0]).toMatchObject({
    resultId: 'batting-result.double-play',
    runnerAdvanceOverridesByRunner: { kind: 'not-applied', overrides: [] },
    outRunner: { base: '1', runnerId, outKind: 'force-out' },
  })
  await w.setProps({ runners: [{ base: '1', label: '一塁走者' }] })
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  w.unmount()
})
it('犠打失策は守備側の実野手を選ぶまで数値1の公式原本を出さない', async () => {
  const w = mount(GameScreenBattedHitObservation, {
    props: {
      ...props,
      resultId: 'batting-result.sacrifice-bunt-error',
      runners: [
        { base: '1', label: '一塁走者' },
        { base: '2', label: '二塁走者' },
      ],
    },
  })
  await flushPromises()
  await explicitNull(w)
  await w.get('[data-testid="batted-runner-1-destination"]').setValue('2')
  await w.get('[data-testid="batted-runner-2-destination"]').setValue('3')
  await w.get('[data-testid="batted-runner-confirmed"]').setValue(true)
  await confirm(w)
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w
    .get('[data-testid="batted-error-fielder"]')
    .setValue(props.fielders[0]!.id)
  expect(w.emitted('change')?.at(-1)?.[0]).toMatchObject({
    resultId: 'batting-result.sacrifice-bunt-error',
    officialScoringPayload: {
      kind: 'error-recorded',
      errors: [
        {
          fielder: { kind: 'official', player_id: props.fielders[0]!.id },
          count: 1,
        },
      ],
    },
  })
  await w.setProps({ fielders: [] })
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  w.unmount()
})
it('全走者の停止確認は起点塁を各走者に明記し、部分確認では出さない', async () => {
  const w = mount(GameScreenBattedHitObservation, {
    props: {
      ...props,
      resultId: 'batting-result.batted-out',
      runners: [
        { base: '1', label: '一塁走者' },
        { base: '3', label: '三塁走者' },
      ],
    },
  })
  await flushPromises()
  await explicitNull(w)
  await confirm(w)
  await w.get('[data-testid="batted-runner-1-destination"]').setValue('hold')
  await w.get('[data-testid="batted-runner-confirmed"]').setValue(true)
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w.get('[data-testid="batted-runner-3-destination"]').setValue('hold')
  await w.get('[data-testid="batted-runner-confirmed"]').setValue(true)
  expect(w.emitted('change')?.at(-1)?.[0]).toMatchObject({
    runnerAdvanceOverridesByRunner: {
      kind: 'applied',
      overrides: [
        { runnerBase: '1', destination: '1' },
        { runnerBase: '3', destination: '3' },
      ],
    },
  })
  w.unmount()
})
it('通常失策による出塁も野手の公式観測と数値1を要求する', async () => {
  const w = mount(GameScreenBattedHitObservation, {
    props: { ...props, resultId: 'batting-result.error' },
  })
  await flushPromises()
  await explicitNull(w)
  await confirm(w)
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w
    .get('[data-testid="batted-error-fielder"]')
    .setValue(props.fielders[0]!.id)
  expect(w.emitted('change')?.at(-1)?.[0]).toMatchObject({
    resultId: 'batting-result.error',
    officialScoringPayload: {
      kind: 'error-recorded',
      errors: [
        {
          fielder: { kind: 'official', player_id: props.fielders[0]!.id },
          count: 1,
        },
      ],
    },
  })
  w.unmount()
})
it('6未観測と4裁定を一つずつ確認するまで観測を成立させず、結果/文脈変更で破棄する', async () => {
  const w = mount(GameScreenBattedHitObservation, { props })
  await flushPromises()
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await explicitNull(w)
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await confirm(w)
  expect(w.emitted('change')?.at(-1)).toEqual([
    {
      resultId: props.resultId,
      battedBall: Object.fromEntries(fields.map((k) => [k, null])),
      officialScoringPayload: {
        kind: 'no-error',
        errorCount: '0',
        fielders: [],
      },
      interferenceRuling: { kind: 'not-required' },
      runnerAdvanceOverridesByRunner: { kind: 'not-applied', overrides: [] },
      thirdOutObservation: { kind: 'none' },
      thirdOutTimingByRunner: {},
    },
  ])
  await w.setProps({ resultId: 'batting-result.double' })
  await flushPromises()
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  expect(w.get('[data-testid="batted-mode-hitX"]').element).toHaveProperty(
    'value',
    '',
  )
  await explicitNull(w)
  await confirm(w)
  await w.setProps({ contextKey: 'game:checkpoint:2' })
  await flushPromises()
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  w.unmount()
})
it('実語彙/実守備者/0..1原値を保持し、範囲外と越境候補を確認済みにしない', async () => {
  const w = mount(GameScreenBattedHitObservation, { props })
  await flushPromises()
  await explicitNull(w)
  for (const [key, value] of [
    ['typeKey', 'observed.line'],
    ['strengthKey', 'observed.line'],
    ['hitX', '0.250'],
    ['hitY', '0.75'],
    ['rawFielderPosition', '9'],
    ['resolvedFielderId', props.fielders[0]!.id],
  ]) {
    await w.get(`[data-testid="batted-mode-${key}"]`).setValue('observed')
    await w.get(`[data-testid="batted-value-${key}"]`).setValue(value)
  }
  await confirm(w)
  expect(w.emitted('change')?.at(-1)?.[0]).toEqual({
    resultId: props.resultId,
    officialScoringPayload: { kind: 'no-error', errorCount: '0', fielders: [] },
    interferenceRuling: { kind: 'not-required' },
    runnerAdvanceOverridesByRunner: { kind: 'not-applied', overrides: [] },
    thirdOutObservation: { kind: 'none' },
    thirdOutTimingByRunner: {},
    battedBall: {
      typeKey: 'observed.line',
      strengthKey: 'observed.line',
      hitX: '0.250',
      hitY: '0.75',
      rawFielderPosition: '9',
      resolvedFielderId: props.fielders[0]!.id,
    },
  })
  await w.get('[data-testid="batted-value-hitX"]').setValue('-0.0001')
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await w.setProps({ fielders: [] })
  await flushPromises()
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  w.unmount()
})
it('語彙取得失敗を自動NULLにせず、明示未観測だけを別操作で受ける', async () => {
  vi.mocked(options.readBattedBallOptions).mockRejectedValue(
    new Error('unavailable'),
  )
  const w = mount(GameScreenBattedHitObservation, { props })
  await flushPromises()
  expect(w.get('[role="alert"]').text()).toContain('未観測とは別')
  expect(w.emitted('change')?.at(-1)).toEqual([null])
  await explicitNull(w)
  await confirm(w)
  expect(w.emitted('change')?.at(-1)?.[0]).not.toBeNull()
  w.unmount()
})

it.each([false, true])(
  '別ページの打球種と強さを同時に保持し、逆pagingでも裁定だけ失効する（逆順=%s）',
  async (reverse) => {
    vi.mocked(options.readBattedBallOptions).mockImplementation(
      async (cursor) => ({
        items: [
          {
            key: cursor === 'page2' ? 'observed.hard' : 'observed.line',
            display_name: cursor === 'page2' ? '強い打球' : 'ライン打球',
          },
        ],
        next_cursor: cursor === null ? 'page2' : null,
      }),
    )
    const w = mount(GameScreenBattedHitObservation, { props })
    await flushPromises()
    await explicitNull(w)
    const button = (label: string) =>
      w.findAll('button').find((b) => b.text() === label)!
    if (reverse) {
      await button('次の打球語彙').trigger('click')
      await flushPromises()
    }
    await w.get('[data-testid="batted-mode-typeKey"]').setValue('observed')
    await w
      .get('[data-testid="batted-value-typeKey"]')
      .setValue(reverse ? 'observed.hard' : 'observed.line')
    await button(reverse ? '前の打球語彙' : '次の打球語彙').trigger('click')
    await flushPromises()
    expect(
      w.get('[data-testid="batted-value-typeKey"]').element,
    ).toHaveProperty('value', reverse ? 'observed.hard' : 'observed.line')
    await w.get('[data-testid="batted-mode-strengthKey"]').setValue('observed')
    await w
      .get('[data-testid="batted-value-strengthKey"]')
      .setValue(reverse ? 'observed.line' : 'observed.hard')
    await confirm(w)
    const expected = {
      resultId: props.resultId,
      battedBall: {
        typeKey: reverse ? 'observed.hard' : 'observed.line',
        strengthKey: reverse ? 'observed.line' : 'observed.hard',
        hitX: null,
        hitY: null,
        rawFielderPosition: null,
        resolvedFielderId: null,
      },
      officialScoringPayload: {
        kind: 'no-error',
        errorCount: '0',
        fielders: [],
      },
      interferenceRuling: { kind: 'not-required' },
      runnerAdvanceOverridesByRunner: { kind: 'not-applied', overrides: [] },
      thirdOutObservation: { kind: 'none' },
      thirdOutTimingByRunner: {},
    }
    expect(w.emitted('change')?.at(-1)).toEqual([expected])
    await button(reverse ? '次の打球語彙' : '前の打球語彙').trigger('click')
    await flushPromises()
    expect(w.emitted('change')?.at(-1)).toEqual([null])
    expect(
      w.get('[data-testid="batted-value-strengthKey"]').element,
    ).toHaveProperty('value', expected.battedBall.strengthKey)
    await confirm(w)
    expect(w.emitted('change')?.at(-1)).toEqual([expected])
    const select = w.get('[data-testid="batted-value-typeKey"]')
    const fake = document.createElement('option')
    fake.value = 'not-fetched'
    fake.textContent = '未取得'
    select.element.appendChild(fake)
    await select.setValue('not-fetched')
    await confirm(w)
    expect(w.emitted('change')?.at(-1)).toEqual([null])
    expect(options.readBattedBallOptions).toHaveBeenCalledTimes(reverse ? 4 : 3)
    await w.setProps({ contextKey: 'different-game' })
    await flushPromises()
    expect(w.get('[data-testid="batted-mode-typeKey"]').element).toHaveProperty(
      'value',
      '',
    )
    expect(w.emitted('change')?.at(-1)).toEqual([null])
    w.unmount()
  },
)
