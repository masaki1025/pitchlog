import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import GameScreen from './GameScreen.vue'
import GameScreenPlayObservation from './GameScreenPlayObservation.vue'
import type {
  PlayObservationQuestion,
  PlayObservationRequest,
} from './GameScreenPlayObservationTypes'

const choice = (
  key: string,
  label: string,
  ids: readonly string[],
  multiple = false,
): PlayObservationQuestion => ({
  key,
  label,
  required: true,
  multiple,
  options: ids.map((id) => ({ id, label: id })),
})

const pitchRequest: PlayObservationRequest = {
  contextKey: 'game-1/play-1',
  mode: 'pitch',
  observation: {
    battedBall: {
      fielderCandidates: [
        { id: 'f1', label: '候補一' },
        { id: 'f2', label: '候補二' },
      ],
      suggestedFielderId: 'f1',
    },
    runners: [
      {
        runnerKey: '__proto__',
        displayName: '一塁走者',
        advanceResult: choice('advance', '進塁結果', ['hold', 'safe']),
        destinationBase: choice('base', '到達塁', ['second', 'home']),
        thirdOutTiming: choice('timing', '第三アウト時機', ['before', 'after']),
        rbiRuling: choice('rbi', '打点因果', ['continued', 'restarted']),
        interferenceQuestions: [
          choice('awardedBase', '審判の授与塁', ['second', 'home']),
        ],
      },
      {
        runnerKey: 'runner-2',
        displayName: '三塁走者',
        advanceResult: choice('advance', '進塁結果', ['hold', 'safe']),
        destinationBase: choice('base', '到達塁', ['second', 'home']),
        thirdOutTiming: choice('timing', '第三アウト時機', ['before', 'after']),
        rbiRuling: choice('rbi', '打点因果', ['continued', 'restarted']),
      },
    ],
    interferenceQuestions: [
      choice('adopted', '採用された裁定', ['award', 'play']),
    ],
    officialScoringQuestions: [
      choice('errorCount', '採用した失策件数', ['none', 'one', 'two']),
      choice('errors', '付随失策', ['f1', 'f2'], true),
    ],
  },
}

const nonPitchRequest: PlayObservationRequest = {
  contextKey: 'game-1/play-2',
  mode: 'non-pitch',
  actions: [
    {
      id: 'steal',
      label: '盗塁',
      observation: {
        runners: [
          {
            runnerKey: 'r1',
            displayName: '一塁走者',
            advanceResult: choice('event', '走者の結果', [
              'safe',
              'out',
              'hold',
            ]),
            attemptedBase: choice('base', '企図塁', ['second', 'third']),
          },
        ],
      },
    },
    {
      id: 'pickoff',
      label: '牽制',
      observation: {
        runners: [
          {
            runnerKey: 'r2',
            displayName: '二塁走者',
            advanceResult: choice('event', '走者の結果', ['safe', 'out']),
            attemptedBase: choice('base', '企図塁', ['second', 'third']),
          },
        ],
      },
    },
    {
      id: 'balk',
      label: 'ボーク',
      observation: {
        runners: [
          {
            runnerKey: 'r3',
            displayName: '三塁走者',
            advanceResult: choice('event', '走者の結果', ['safe', 'hold']),
            destinationBase: choice('base', '到達塁', ['home']),
          },
        ],
      },
    },
  ],
}

function raw(wrapper: ReturnType<typeof mount>) {
  return wrapper.getComponent(GameScreenPlayObservation).vm.getRawObservation()
}

describe('打球・走者観測の表示契約', () => {
  it('投球の複数走者をキー別に保持し、時機・打点・裁定に既定値を置かない', async () => {
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: pitchRequest,
        observationContextKey: 'game-1/play-1',
      },
    })
    expect(wrapper.get('[data-testid="observation-mode"]').text()).toBe(
      '投球時の観測',
    )
    expect(
      wrapper.get<HTMLSelectElement>('[data-testid="fielder"]').element.value,
    ).toBe('')
    expect(wrapper.get('[data-testid="suggested-fielder"]').text()).toContain(
      '候補一',
    )
    expect(raw(wrapper)?.thirdOutTimingByRunner['__proto__']).toBeNull()
    expect(raw(wrapper)?.thirdOutTimingByRunner['runner-2']).toBeNull()
    expect(raw(wrapper)?.rbiRuling.byRunner['runner-2']).toBeNull()
    expect(raw(wrapper)?.interferenceRuling.play.adopted).toBeNull()
    expect(
      raw(wrapper)?.interferenceRuling.byRunner['__proto__']?.awardedBase,
    ).toBeNull()
    expect(raw(wrapper)?.officialScoringPayload.play.errorCount).toBeNull()
    expect(raw(wrapper)?.officialScoringPayload.play.errors).toBeNull()

    await wrapper.get('[data-testid="ball-x"]').setValue('0.25')
    await wrapper.get('[data-testid="ball-y"]').setValue('0.75')
    await wrapper.get('[data-testid="fielder"]').setValue('f2')
    const first = wrapper.get('[data-runner-key="__proto__"]')
    const second = wrapper.get('[data-runner-key="runner-2"]')
    await first.get('[data-question-key="advance"] select').setValue('safe')
    await first.get('[data-question-key="base"] select').setValue('second')
    await first.get('[data-question-key="timing"] select').setValue('before')
    await first.get('[data-question-key="rbi"] select').setValue('continued')
    await second.get('[data-question-key="advance"] select').setValue('hold')
    await second.get('[data-question-key="timing"] select').setValue('after')
    await second.get('[data-question-key="rbi"] select').setValue('restarted')
    await wrapper.get('[data-question-key="adopted"] select').setValue('play')
    await first.get('[data-question-key="awardedBase"] select').setValue('home')
    await wrapper.get('[data-question-key="errorCount"] select').setValue('one')
    await wrapper
      .get('[data-question-key="errors"] input[value="f2"]')
      .setValue(true)

    const observation = raw(wrapper)
    expect(observation?.battedBall).toEqual({
      x: '0.25',
      y: '0.75',
      fielderId: 'f2',
    })
    expect(observation?.runnerAdvanceOverridesByRunner['__proto__']).toEqual({
      resultId: 'safe',
      destinationBaseId: 'second',
    })
    expect(observation?.runnerAdvanceOverridesByRunner['runner-2']).toEqual({
      resultId: 'hold',
      destinationBaseId: null,
    })
    expect(observation?.thirdOutTimingByRunner['__proto__']).toBe('before')
    expect(observation?.thirdOutTimingByRunner['runner-2']).toBe('after')
    expect(observation?.rbiRuling.byRunner['__proto__']).toBe('continued')
    expect(observation?.rbiRuling.byRunner['runner-2']).toBe('restarted')
    expect(observation?.interferenceRuling.play.adopted).toBe('play')
    expect(
      observation?.interferenceRuling.byRunner['__proto__']?.awardedBase,
    ).toBe('home')
    expect(observation?.officialScoringPayload.play.errorCount).toBe('one')
    expect(observation?.officialScoringPayload.play.errors).toEqual(['f2'])
    expect(
      Object.getPrototypeOf(observation?.runnerAdvanceOverridesByRunner),
    ).toBeNull()
  })

  it.each(['steal', 'pickoff', 'balk'])(
    '非投球 %s は供給された走者・結果・塁だけを要求する',
    async (actionId) => {
      const wrapper = mount(GameScreen, {
        props: {
          observationRequest: nonPitchRequest,
          observationContextKey: 'game-1/play-2',
        },
      })
      expect(wrapper.find('[data-testid="pitch-type"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="pitch-result"]').exists()).toBe(false)
      expect(wrapper.find('svg').exists()).toBe(false)
      await wrapper.get('[data-testid="non-pitch-action"]').setValue(actionId)
      const action = nonPitchRequest.actions.find(
        (item) => item.id === actionId,
      )!
      expect(
        wrapper.findAll('[data-testid="runner-observation"]'),
      ).toHaveLength(1)
      expect(
        wrapper
          .get('[data-testid="runner-observation"]')
          .attributes('data-runner-key'),
      ).toBe(action.observation.runners[0]?.runnerKey)
      expect(
        wrapper.get<HTMLSelectElement>('[data-question-key="event"] select')
          .element.value,
      ).toBe('')
      expect(
        wrapper.get<HTMLSelectElement>('[data-question-key="base"] select')
          .element.value,
      ).toBe('')
      await wrapper.get('[data-question-key="event"] select').setValue('safe')
      await wrapper
        .get('[data-question-key="base"] select')
        .setValue(actionId === 'balk' ? 'home' : 'second')
      expect(raw(wrapper)?.mode).toBe('non-pitch')
      expect(raw(wrapper)?.actionId).toBe(actionId)
      expect(raw(wrapper)?.playResultId).toBeNull()
      expect(raw(wrapper)?.battedBall).toBeNull()
      expect(
        raw(wrapper)?.runnerEventsByRunner[
          action.observation.runners[0]!.runnerKey
        ]?.resultId,
      ).toBe('safe')
    },
  )

  it('種別・候補・試合文脈の切替で古い値を新しい走者へ移さない', async () => {
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: nonPitchRequest,
        observationContextKey: 'game-1/play-2',
      },
    })
    await wrapper.get('[data-testid="non-pitch-action"]').setValue('steal')
    await wrapper.get('[data-question-key="event"] select').setValue('out')
    await wrapper.get('[data-testid="non-pitch-action"]').setValue('pickoff')
    expect(raw(wrapper)?.runnerEventsByRunner.r1).toBeUndefined()
    expect(raw(wrapper)?.runnerEventsByRunner.r2?.resultId).toBeNull()
    await wrapper.setProps({ observationContextKey: 'game-2/play-1' })
    expect(wrapper.find('[data-testid="non-pitch-action"]').exists()).toBe(
      false,
    )
    expect(raw(wrapper)).toBeNull()
    await wrapper.setProps({
      observationRequest: { ...nonPitchRequest, contextKey: 'game-2/play-1' },
    })
    expect(
      wrapper.get<HTMLSelectElement>('[data-testid="non-pitch-action"]').element
        .value,
    ).toBe('')
    await wrapper.get('[data-testid="non-pitch-action"]').setValue('steal')
    expect(raw(wrapper)?.runnerEventsByRunner.r1?.resultId).toBeNull()
    await wrapper.setProps({
      observationRequest: {
        ...nonPitchRequest,
        contextKey: 'game-2/play-1',
        actions: nonPitchRequest.actions.slice(1),
      },
    })
    expect(
      wrapper.get<HTMLSelectElement>('[data-testid="non-pitch-action"]').element
        .value,
    ).toBe('')
    expect(raw(wrapper)).toBeNull()
  })

  it('投球から非投球へ切り替えると旧投球下書きも再表示しない', async () => {
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: pitchRequest,
        observationContextKey: 'game-1/play-1',
        pitchTypes: [{ id: 'fast', displayName: '直球', enabled: true }],
        results: [{ id: 'hit', displayName: '安打', enabled: true }],
      },
    })
    await wrapper.get('[data-testid="pitch-type"]').setValue('fast')
    await wrapper.get('[data-testid="pitch-result"]').setValue('hit')
    await wrapper.setProps({
      observationRequest: nonPitchRequest,
      observationContextKey: 'game-1/play-2',
    })
    expect(wrapper.find('[data-testid="pitch-type"]').exists()).toBe(false)
    await wrapper.setProps({
      observationRequest: pitchRequest,
      observationContextKey: 'game-1/play-1',
    })
    expect(
      wrapper.get<HTMLSelectElement>('[data-testid="pitch-type"]').element
        .value,
    ).toBe('')
    expect(
      wrapper.get<HTMLSelectElement>('[data-testid="pitch-result"]').element
        .value,
    ).toBe('')
  })

  it('結果名から付随失策・妨害を推定せず、提供された質問だけを描画する', () => {
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: pitchRequest,
        observationContextKey: 'game-1/play-1',
        results: [{ id: 'error', displayName: '失策', enabled: true }],
      },
    })
    expect(wrapper.findAll('[data-question-key="errors"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-question-key="adopted"]')).toHaveLength(1)
    const noQuestions: PlayObservationRequest = {
      contextKey: 'game-1/play-1',
      mode: 'pitch',
      observation: { runners: [] },
    }
    return wrapper.setProps({ observationRequest: noQuestions }).then(() => {
      expect(wrapper.find('[data-question-key="errors"]').exists()).toBe(false)
      expect(wrapper.find('[data-question-key="adopted"]').exists()).toBe(false)
    })
  })

  it('重複走者キーは封鎖し、文字列をHTMLに変換せず、直接dispatchでも送信しない', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response())
    const malicious = '<img src=x onerror=alert(1)>'
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: {
          contextKey: 'game-1/play-1',
          mode: 'pitch',
          observation: {
            runners: [{ runnerKey: 'r1', displayName: malicious }],
          },
        },
        observationContextKey: 'game-1/play-1',
      },
    })
    expect(wrapper.get('[data-testid="runner-observation"]').text()).toBe(
      malicious,
    )
    expect(wrapper.find('img').exists()).toBe(false)
    expect(
      wrapper.get('[data-testid="commit-observation"]').attributes('disabled'),
    ).toBeDefined()
    wrapper
      .get('[data-testid="commit-observation"]')
      .element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    wrapper
      .get('[data-testid="commit-pitch"]')
      .element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.emitted('save')).toBeUndefined()
    expect(wrapper.emitted('send')).toBeUndefined()
    expect(wrapper.text()).not.toContain('保存しました')
    await wrapper.setProps({
      observationRequest: {
        contextKey: 'game-1/play-1',
        mode: 'pitch',
        observation: {
          runners: [
            { runnerKey: 'r1', displayName: '一塁' },
            { runnerKey: 'r1', displayName: '二塁' },
          ],
        },
      },
    })
    expect(
      wrapper.find('[data-testid="observation-unavailable"]').exists(),
    ).toBe(true)
    expect(raw(wrapper)).toBeNull()
    fetchSpy.mockRestore()
  })

  it.each([375, 320])('%dpx 用に縦積みし、長い候補名を折り返す', (width) => {
    window.innerWidth = width
    const longName = 'W'.repeat(120)
    const wrapper = mount(GameScreen, {
      props: {
        observationContextKey: 'game-1/play-1',
        observationRequest: {
          contextKey: 'game-1/play-1',
          mode: 'pitch',
          observation: {
            battedBall: { fielderCandidates: [{ id: 'f1', label: longName }] },
            runners: [{ runnerKey: 'r1', displayName: longName }],
            officialScoringQuestions: [choice('error', longName, ['f1'], true)],
          },
        },
      },
    })
    const section = wrapper.get('section[aria-label="打球・走者観測の下書き"]')
    expect(section.classes()).toContain('min-w-0')
    expect(section.find('div.grid').classes()).toContain('grid-cols-1')
    expect(section.html()).not.toMatch(
      /\b(?:whitespace-nowrap|truncate|min-w-\[\d+px\])\b/,
    )
    expect(section.get('label span').classes()).toContain('wrap-anywhere')
    expect(section.text()).toContain(longName)
  })
})
