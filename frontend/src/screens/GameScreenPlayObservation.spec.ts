import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GameScreen from './GameScreen.vue'
import GameScreenPlayObservation from './GameScreenPlayObservation.vue'
import type {
  MultipleObservationQuestion,
  PlayObservationRequest,
  SingleObservationQuestion,
} from './GameScreenPlayObservationTypes'

const choice = (
  key: string,
  label: string,
  ids: readonly string[],
): SingleObservationQuestion => ({
  key,
  label,
  required: true,
  options: ids.map((id) => ({ id, label: id })),
})

const multipleChoice = (
  key: string,
  label: string,
  ids: readonly string[],
): MultipleObservationQuestion => ({
  key,
  label,
  required: true,
  multiple: true,
  options: ids.map((id) => ({ id, label: id })),
})

const pitchRequest = {
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
        attemptedBase: choice('attempt', '企図塁', ['second', 'third']),
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
      multipleChoice('errors', '付随失策', ['f1', 'f2']),
    ],
  },
} satisfies PlayObservationRequest

const nonPitchRequest = {
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
} satisfies PlayObservationRequest

function raw(wrapper: ReturnType<typeof mount>) {
  return wrapper.getComponent(GameScreenPlayObservation).vm.getRawObservation()
}

function sparseArray<T>(sample: T, extraKey: boolean): T[] {
  const values = new Array<T>(1)
  if (extraKey) {
    Object.defineProperty(values, 'extra', { value: sample, enumerable: true })
  }
  expect(Object.prototype.hasOwnProperty.call(values, 0)).toBe(false)
  expect(Object.keys(values)).toHaveLength(extraKey ? 1 : 0)
  return values
}

const originalWidth = window.innerWidth
afterEach(() => {
  window.innerWidth = originalWidth
  vi.restoreAllMocks()
})

describe('打球・走者観測の表示契約', () => {
  const sparseRequests: readonly [
    string,
    (extraKey: boolean) => PlayObservationRequest,
  ][] = [
    [
      '質問の選択肢',
      (extraKey) => ({
        contextKey: 'game-1/play-1',
        mode: 'pitch',
        observation: {
          runners: [],
          playResult: {
            ...choice('result', '打撃結果', ['hit']),
            options: sparseArray({ id: 'hit', label: '安打' }, extraKey),
          },
        },
      }),
    ],
    [
      'プレイ単位の質問配列',
      (extraKey) => ({
        contextKey: 'game-1/play-1',
        mode: 'pitch',
        observation: {
          runners: [],
          interferenceQuestions: sparseArray(
            choice('ruling', '裁定', ['award']),
            extraKey,
          ),
        },
      }),
    ],
    [
      '走者単位の質問配列',
      (extraKey) => ({
        contextKey: 'game-1/play-1',
        mode: 'pitch',
        observation: {
          runners: [
            {
              runnerKey: 'r1',
              displayName: '走者',
              officialScoringQuestions: sparseArray(
                choice('error', '失策', ['none']),
                extraKey,
              ),
            },
          ],
        },
      }),
    ],
    [
      '対象走者',
      (extraKey) => ({
        contextKey: 'game-1/play-1',
        mode: 'pitch',
        observation: {
          runners: sparseArray(
            { runnerKey: 'r1', displayName: '走者' },
            extraKey,
          ),
        },
      }),
    ],
    [
      '捕球選手候補',
      (extraKey) => ({
        contextKey: 'game-1/play-1',
        mode: 'pitch',
        observation: {
          runners: [],
          battedBall: {
            fielderCandidates: sparseArray(
              { id: 'f1', label: '候補一' },
              extraKey,
            ),
          },
        },
      }),
    ],
    [
      '非投球の種別',
      (extraKey) => ({
        contextKey: 'game-1/play-1',
        mode: 'non-pitch',
        actions: sparseArray(
          { id: 'steal', label: '盗塁', observation: { runners: [] } },
          extraKey,
        ),
      }),
    ],
  ]

  it.each(sparseRequests)(
    '%sの疎配列を未取得として封鎖し停止UIを維持する',
    (_name, requestFor) => {
      for (const extraKey of [false, true]) {
        const request = requestFor(extraKey)
        const wrapper = mount(GameScreen, {
          props: {
            observationRequest: request,
            observationContextKey: request.contextKey,
            stopDisplay: {
              phase: 'sending-stopped',
              deviceUnconfirmed: { kind: 'count', value: 2 },
            },
          },
        })
        expect(
          wrapper.find('[data-testid="observation-unavailable"]').exists(),
        ).toBe(true)
        expect(raw(wrapper)).toBeNull()
        expect(wrapper.find('[data-testid="non-pitch-action"]').exists()).toBe(
          false,
        )
        expect(
          wrapper.find('[data-testid="runner-observation"]').exists(),
        ).toBe(false)
        expect(wrapper.get('[data-testid="stop-status"]').text()).toBe(
          '送信停止',
        )
        expect(
          wrapper.get('[data-testid="device-unconfirmed-count"]').text(),
        ).toBe('2')
        for (const testId of [
          'resume-same-content',
          'correct-stopped-content',
        ]) {
          expect(
            wrapper.get<HTMLButtonElement>(`[data-testid="${testId}"]`).element
              .disabled,
          ).toBe(true)
        }
        if (request.mode === 'pitch') {
          expect(
            wrapper.get<HTMLButtonElement>('[data-testid="commit-pitch"]')
              .element.disabled,
          ).toBe(true)
        } else {
          expect(wrapper.find('[data-testid="commit-pitch"]').exists()).toBe(
            false,
          )
        }
        expect(
          wrapper.find('[data-testid="commit-observation"]').exists(),
        ).toBe(false)
      }
    },
  )

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
    expect(raw(wrapper)?.battedBall?.fielderId).toBeNull()
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
    expect(
      raw(wrapper)?.runnerAdvanceOverridesByRunner['__proto__'],
    ).toBeUndefined()

    await wrapper.get('[data-testid="ball-x"]').setValue('0.25')
    await wrapper.get('[data-testid="ball-y"]').setValue('0.75')
    await wrapper
      .get('[data-testid="choose-suggested-fielder"]')
      .trigger('click')
    expect(raw(wrapper)?.battedBall?.fielderId).toBe('f1')
    await wrapper.get('[data-testid="fielder"]').setValue('f2')
    const first = wrapper.get('[data-runner-key="__proto__"]')
    const second = wrapper.get('[data-runner-key="runner-2"]')
    await first.get('[data-question-key="advance"] select').setValue('safe')
    await first.get('[data-question-key="base"] select').setValue('second')
    await first.get('[data-question-key="attempt"] select').setValue('third')
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
      attemptedBaseId: 'third',
    })
    expect(observation?.runnerAdvanceOverridesByRunner['runner-2']).toEqual({
      resultId: 'hold',
      destinationBaseId: null,
      attemptedBaseId: null,
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

  it('投球で企図塁だけを観測した走者もrawの写像に保持する', async () => {
    const request: PlayObservationRequest = {
      contextKey: 'game-1/play-1',
      mode: 'pitch',
      observation: {
        runners: [
          {
            runnerKey: 'r1',
            displayName: '走者',
            attemptedBase: choice('attempt', '企図塁', ['third']),
          },
        ],
      },
    }
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: request,
        observationContextKey: request.contextKey,
      },
    })
    await wrapper.get('[data-question-key="attempt"] select').setValue('third')
    expect(raw(wrapper)?.runnerAdvanceOverridesByRunner.r1).toEqual({
      resultId: null,
      destinationBaseId: null,
      attemptedBaseId: 'third',
    })
  })

  it('複数選択の最後を外すと未選択へ戻し、明示noneだけを観測として残す', async () => {
    const request: PlayObservationRequest = {
      contextKey: 'game-1/play-1',
      mode: 'pitch',
      observation: {
        runners: [],
        officialScoringQuestions: [
          multipleChoice('errors', '採用した失策', ['f1', 'none']),
        ],
      },
    }
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: request,
        observationContextKey: request.contextKey,
      },
    })
    const fielder = wrapper.get(
      '[data-question-key="errors"] input[value="f1"]',
    )
    expect(raw(wrapper)?.officialScoringPayload.play.errors).toBeNull()
    await fielder.setValue(true)
    expect(raw(wrapper)?.officialScoringPayload.play.errors).toEqual(['f1'])
    await fielder.setValue(false)
    expect(raw(wrapper)?.officialScoringPayload.play.errors).toBeNull()
    await wrapper
      .get('[data-question-key="errors"] input[value="none"]')
      .setValue(true)
    expect(raw(wrapper)?.officialScoringPayload.play.errors).toEqual(['none'])
  })

  it.each([
    'advanceResult',
    'destinationBase',
    'attemptedBase',
    'thirdOutTiming',
    'rbiRuling',
  ] as const)('%s に複数選択を渡した要求を表示前に拒否する', (field) => {
    const invalid = {
      contextKey: 'game-1/play-1',
      mode: 'pitch',
      observation: {
        runners: [
          {
            runnerKey: 'r1',
            displayName: '走者',
            [field]: multipleChoice('invalid', '不正な複数選択', ['one']),
          },
        ],
      },
    } as unknown as PlayObservationRequest
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: invalid,
        observationContextKey: 'game-1/play-1',
      },
    })
    expect(
      wrapper.find('[data-testid="observation-unavailable"]').exists(),
    ).toBe(true)
    expect(raw(wrapper)).toBeNull()
  })

  it('単一選択はlabel、複数選択はlegendで質問名を読める', () => {
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: pitchRequest,
        observationContextKey: 'game-1/play-1',
      },
    })
    const field = wrapper.get(
      '[data-runner-key="__proto__"] [data-question-key="advance"]',
    )
    expect(field.get('label').attributes('for')).toBe(
      field.get('select').attributes('id'),
    )
    expect(field.get('label').text()).toContain('進塁結果')
    expect(
      wrapper.get('[data-question-key="errors"] fieldset legend').text(),
    ).toContain('付随失策')
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

  it.each(['playResult', 'rbiRuling'] as const)(
    'プレイ単位の%sに複数選択を渡した要求も拒否する',
    (field) => {
      const invalid = {
        contextKey: 'game-1/play-1',
        mode: 'pitch',
        observation: {
          runners: [],
          [field]: multipleChoice('invalid', '不正な複数選択', ['one']),
        },
      } as unknown as PlayObservationRequest
      const wrapper = mount(GameScreen, {
        props: {
          observationRequest: invalid,
          observationContextKey: 'game-1/play-1',
        },
      })
      expect(
        wrapper.find('[data-testid="observation-unavailable"]').exists(),
      ).toBe(true)
      expect(raw(wrapper)).toBeNull()
    },
  )

  it('非投球で同時に動く複数走者の結果・到達塁・企図塁を別々に保持する', async () => {
    const request: PlayObservationRequest = {
      contextKey: 'game-1/play-3',
      mode: 'non-pitch',
      actions: [
        {
          id: 'multi',
          label: '複数走者',
          observation: {
            runners: [
              {
                runnerKey: 'r1',
                displayName: '一塁走者',
                advanceResult: choice('result', '結果', ['safe', 'out']),
                destinationBase: choice('reached', '到達塁', [
                  'second',
                  'third',
                ]),
                attemptedBase: choice('attempted', '企図塁', [
                  'second',
                  'third',
                ]),
              },
              {
                runnerKey: 'r2',
                displayName: '二塁走者',
                advanceResult: choice('result', '結果', ['safe', 'out']),
                destinationBase: choice('reached', '到達塁', ['third', 'home']),
                attemptedBase: choice('attempted', '企図塁', ['third', 'home']),
              },
            ],
          },
        },
      ],
    }
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: request,
        observationContextKey: request.contextKey,
      },
    })
    await wrapper.get('[data-testid="non-pitch-action"]').setValue('multi')
    const first = wrapper.get('[data-runner-key="r1"]')
    const second = wrapper.get('[data-runner-key="r2"]')
    await first.get('[data-question-key="result"] select').setValue('safe')
    await first.get('[data-question-key="reached"] select').setValue('second')
    await first.get('[data-question-key="attempted"] select').setValue('third')
    await second.get('[data-question-key="result"] select').setValue('out')
    await second.get('[data-question-key="reached"] select').setValue('third')
    await second.get('[data-question-key="attempted"] select').setValue('home')
    expect(raw(wrapper)?.runnerEventsByRunner.r1).toEqual({
      resultId: 'safe',
      destinationBaseId: 'second',
      attemptedBaseId: 'third',
    })
    expect(raw(wrapper)?.runnerEventsByRunner.r2).toEqual({
      resultId: 'out',
      destinationBaseId: 'third',
      attemptedBaseId: 'home',
    })
  })

  it('未知modeと非投球への打撃結果・打球欄混入を表示前に拒否する', () => {
    const invalidRequests = [
      { contextKey: 'game-1/play-1', mode: 'unknown', actions: [] },
      {
        contextKey: 'game-1/play-1',
        mode: 'non-pitch',
        actions: [
          {
            id: 'steal',
            label: '盗塁',
            observation: {
              runners: [],
              playResult: choice('result', '打撃結果', ['hit']),
            },
          },
        ],
      },
      {
        contextKey: 'game-1/play-1',
        mode: 'non-pitch',
        actions: [
          {
            id: 'steal',
            label: '盗塁',
            observation: {
              runners: [],
              battedBall: { fielderCandidates: [] },
            },
          },
        ],
      },
    ] as unknown as PlayObservationRequest[]
    for (const request of invalidRequests) {
      const wrapper = mount(GameScreen, {
        props: {
          observationRequest: request,
          observationContextKey: 'game-1/play-1',
        },
      })
      expect(
        wrapper.find('[data-testid="observation-unavailable"]').exists(),
      ).toBe(true)
      expect(wrapper.find('[data-testid="pitch-type"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="non-pitch-action"]').exists()).toBe(
        false,
      )
      expect(raw(wrapper)).toBeNull()
    }
  })

  it('非投球の任意プロパティがundefinedだけなら入力要求を受ける', async () => {
    const request: PlayObservationRequest = {
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
                advanceResult: choice('result', '走者の結果', ['safe']),
              },
            ],
            playResult: undefined,
            battedBall: undefined,
          },
        },
      ],
    }
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: request,
        observationContextKey: request.contextKey,
      },
    })
    expect(
      wrapper.find('[data-testid="observation-unavailable"]').exists(),
    ).toBe(false)
    expect(wrapper.find('[data-testid="pitch-type"]').exists()).toBe(false)
    await wrapper.get('[data-testid="non-pitch-action"]').setValue('steal')
    await wrapper.get('[data-question-key="result"] select').setValue('safe')
    expect(raw(wrapper)?.runnerEventsByRunner.r1?.resultId).toBe('safe')
    expect(raw(wrapper)?.playResultId).toBeNull()
    expect(raw(wrapper)?.battedBall).toBeNull()
  })

  it.each([
    null,
    undefined,
    {},
    [],
    false,
    { runners: null },
    { runners: [null] },
    {
      runners: [
        {
          runnerKey: 'r1',
          displayName: '走者',
          advanceResult: {
            key: 'result',
            label: '結果',
            required: true,
            options: [null],
          },
        },
      ],
    },
  ])('非投球の不正なobservation %jを例外なく拒否する', (observation) => {
    const request = {
      contextKey: 'game-1/play-2',
      mode: 'non-pitch',
      actions: [{ id: 'steal', label: '盗塁', observation }],
    } as unknown as PlayObservationRequest
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: request,
        observationContextKey: 'game-1/play-2',
      },
    })
    expect(
      wrapper.find('[data-testid="observation-unavailable"]').exists(),
    ).toBe(true)
    expect(wrapper.find('[data-testid="non-pitch-action"]').exists()).toBe(
      false,
    )
    expect(raw(wrapper)).toBeNull()
  })

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
    expect(
      wrapper.get('[data-testid="observation-draft-cleared"]').text(),
    ).toContain('消去しました')
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

  it('同じ内容の新しいprops参照では保持し、候補の内容変更時だけ通知して破棄する', async () => {
    const identity = {
      d5: 'draft-a',
      d4: 'generation-a',
      gameId: 'game-1',
      d2: { sequence: 1 },
    }
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: pitchRequest,
        observationContextKey: 'game-1/play-1',
        eventIdentity: identity,
        pitchTypes: [{ id: 'fast', displayName: '直球', enabled: true }],
      },
    })
    await wrapper.get('[data-testid="ball-x"]').setValue('0.25')
    await wrapper.get('[data-testid="pitch-type"]').setValue('fast')
    await wrapper.setProps({
      observationRequest: structuredClone(pitchRequest),
      eventIdentity: structuredClone(identity),
    })
    expect(
      wrapper.get<HTMLInputElement>('[data-testid="ball-x"]').element.value,
    ).toBe('0.25')
    expect(
      wrapper.get<HTMLSelectElement>('[data-testid="pitch-type"]').element
        .value,
    ).toBe('fast')
    expect(
      wrapper.find('[data-testid="observation-draft-cleared"]').exists(),
    ).toBe(false)
    expect(wrapper.find('[data-testid="pitch-draft-cleared"]').exists()).toBe(
      false,
    )

    const changed = structuredClone(pitchRequest)
    changed.observation.battedBall!.fielderCandidates[0]!.label = '変更後'
    await wrapper.setProps({ observationRequest: changed })
    expect(
      wrapper.get<HTMLInputElement>('[data-testid="ball-x"]').element.value,
    ).toBe('')
    expect(
      wrapper.get<HTMLSelectElement>('[data-testid="pitch-type"]').element
        .value,
    ).toBe('')
    expect(
      wrapper.get('[data-testid="observation-draft-cleared"]').text(),
    ).toContain('消去しました')
    expect(wrapper.get('[data-testid="pitch-draft-cleared"]').text()).toContain(
      '消去しました',
    )
  })

  it('eventIdentity変更では投球と走者観測の両方を消し、同内容の再供給では保持する', async () => {
    const identity = {
      d5: 'draft-a',
      d4: 'generation-a',
      gameId: 'game-1',
      d2: { sequence: 1 },
    }
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: pitchRequest,
        observationContextKey: 'game-1/play-1',
        eventIdentity: identity,
        pitchTypes: [{ id: 'fast', displayName: '直球', enabled: true }],
      },
    })
    await wrapper.get('[data-testid="pitch-type"]').setValue('fast')
    await wrapper.get('[data-testid="ball-x"]').setValue('0.25')
    await wrapper
      .get('[data-runner-key="__proto__"] [data-question-key="timing"] select')
      .setValue('before')
    await wrapper.setProps({ eventIdentity: structuredClone(identity) })
    expect(
      wrapper.get<HTMLInputElement>('[data-testid="ball-x"]').element.value,
    ).toBe('0.25')
    expect(raw(wrapper)?.thirdOutTimingByRunner['__proto__']).toBe('before')
    await wrapper.setProps({ eventIdentity: { ...identity, d5: 'draft-b' } })
    expect(
      wrapper.get<HTMLSelectElement>('[data-testid="pitch-type"]').element
        .value,
    ).toBe('')
    expect(
      wrapper.get<HTMLInputElement>('[data-testid="ball-x"]').element.value,
    ).toBe('')
    expect(raw(wrapper)?.thirdOutTimingByRunner['__proto__']).toBeNull()
    expect(wrapper.get('[data-testid="pitch-draft-cleared"]').text()).toContain(
      '消去しました',
    )
    expect(
      wrapper.get('[data-testid="observation-draft-cleared"]').text(),
    ).toContain('消去しました')
  })

  it('観測下書きを明示消去すると非投球の種別と走者回答が残らない', async () => {
    const wrapper = mount(GameScreen, {
      props: {
        observationRequest: nonPitchRequest,
        observationContextKey: 'game-1/play-2',
      },
    })
    await wrapper.get('[data-testid="non-pitch-action"]').setValue('steal')
    await wrapper.get('[data-question-key="event"] select').setValue('out')
    await wrapper.get('[data-testid="clear-observation"]').trigger('click')
    expect(
      wrapper.get<HTMLSelectElement>('[data-testid="non-pitch-action"]').element
        .value,
    ).toBe('')
    expect(raw(wrapper)).toBeNull()
    await wrapper.get('[data-testid="non-pitch-action"]').setValue('steal')
    expect(raw(wrapper)?.runnerEventsByRunner.r1?.resultId).toBeNull()
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
    const previousWidth = window.innerWidth
    try {
      window.innerWidth = width
      const longName = 'W'.repeat(120)
      const wrapper = mount(GameScreen, {
        props: {
          observationContextKey: 'game-1/play-1',
          observationRequest: {
            contextKey: 'game-1/play-1',
            mode: 'pitch',
            observation: {
              battedBall: {
                fielderCandidates: [{ id: 'f1', label: longName }],
              },
              runners: [{ runnerKey: 'r1', displayName: longName }],
              officialScoringQuestions: [
                multipleChoice('error', longName, ['f1']),
              ],
            },
          },
        },
      })
      const section = wrapper.get(
        'section[aria-label="打球・走者観測の下書き"]',
      )
      expect(section.classes()).toContain('min-w-0')
      expect(section.find('div.grid').classes()).toContain('grid-cols-1')
      expect(section.html()).not.toMatch(
        /\b(?:whitespace-nowrap|truncate|min-w-\[\d+px\])\b/,
      )
      expect(section.get('label span').classes()).toContain('wrap-anywhere')
      expect(section.text()).toContain(longName)
    } finally {
      window.innerWidth = previousWidth
    }
    expect(window.innerWidth).toBe(previousWidth)
  })
})
