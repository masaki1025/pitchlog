import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GameScreen from './GameScreen.vue'
import type {
  PastSubstitutionPreview,
  PastSubstitutionRequest,
  SubstitutionKind,
  SubstitutionDraftsSnapshot,
  SubstitutionLockState,
  SubstitutionOperationSupply,
  SubstitutionRequest,
  SubstitutionValidation,
  TiebreakRequest,
} from './GameScreenSubstitutionTypes'

const kinds: readonly SubstitutionKind[] = [
  'pitcher',
  'pinch-hitter',
  'pinch-runner',
  'defense',
]
function operation(kind: SubstitutionKind): SubstitutionOperationSupply {
  return {
    kind,
    outgoing: [{ id: `${kind}-out`, label: '交代前の選手' }],
    incoming: [{ id: `${kind}-in`, label: '交代後の選手' }],
    registrationQuestions: [
      {
        key: 'new-name',
        label: '新しい選手の氏名',
        input: 'text',
        required: true,
      },
    ],
    placementQuestions: [
      {
        key: 'place',
        label: '守備位置または指名打者',
        input: 'choice',
        required: true,
        options: [
          { id: 'provided-dh', label: '指名打者' },
          { id: 'provided-p', label: '投手' },
        ],
      },
    ],
    questions: [
      {
        key: 'order',
        label: '提供された打順候補',
        input: 'choice',
        required: true,
        options: [{ id: 'provided-order', label: '提供された候補' }],
      },
    ],
  }
}
const request: SubstitutionRequest = {
  contextKey: 'game-a',
  operations: kinds.map(operation),
}
const tiebreakRequest: TiebreakRequest = {
  contextKey: 'game-a',
  placementQuestions: [
    {
      key: 'runner',
      label: 'タイブレーク走者の配置',
      input: 'choice',
      required: true,
      options: [{ id: 'runner-a', label: '二塁の選手' }],
    },
  ],
  leadBatterQuestions: [
    {
      key: 'lead',
      label: '先頭打者',
      input: 'choice',
      required: true,
      options: [{ id: 'batter-a', label: '次の打者' }],
    },
  ],
  inningQuestions: [
    {
      key: 'inning',
      label: '回の指定',
      input: 'choice',
      required: true,
      options: [{ id: 'inning-a', label: '延長の回' }],
    },
  ],
}
const pastRequest: PastSubstitutionRequest = {
  contextKey: 'game-a',
  page: {
    label: '1ページ目',
    hasPrevious: false,
    hasNext: true,
    targets: [
      {
        id: 'history-a',
        label: '7回表の投手交代',
        detail: '交代前 ' + '長い選手名'.repeat(25),
      },
    ],
  },
  personQuestions: [
    {
      key: 'person',
      label: '選手の訂正',
      input: 'choice',
      required: true,
      options: [{ id: 'person-a', label: '訂正後の選手' }],
    },
  ],
  inningQuestions: [
    {
      key: 'past-inning',
      label: '回の訂正',
      input: 'choice',
      required: true,
      options: [{ id: 'past-inning-a', label: '7回表' }],
    },
  ],
  timingQuestions: [
    { key: 'timing', label: '交代時点の訂正', input: 'text', required: true },
  ],
}

function mountScreen(overrides: Record<string, unknown> = {}) {
  return mount(GameScreen, {
    props: {
      substitutionRequest: request,
      tiebreakRequest,
      pastSubstitutionRequest: pastRequest,
      substitutionContextKey: 'game-a',
      ...overrides,
    },
  })
}
function raw(wrapper: ReturnType<typeof mountScreen>) {
  const events = wrapper.emitted('substitution-draft-change')
  expect(events?.length).toBeGreaterThan(0)
  return events!.at(-1)![0] as SubstitutionDraftsSnapshot
}

// 穴と余分な列挙keyを同時に作り、キー数だけの検査をすり抜けないことを確かめる。
function sparseWithExtra<T>(item: T): T[] {
  const values = new Array<T>(2)
  values[1] = item
  Object.defineProperty(values, 'extra', {
    value: item,
    enumerable: true,
  })
  return values
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('交代とタイブレークの画面下書き', () => {
  it('候補・質問・交代種別・履歴の全供給配列の穴を未取得として閉じ、停止表示を保つ', () => {
    const base = operation('pitcher')
    const normal = (change: Partial<SubstitutionOperationSupply>) => ({
      ...request,
      operations: [{ ...base, ...change }],
    })
    const sparseCases: readonly {
      name: string
      props: Record<string, unknown>
      unavailable: string
    }[] = [
      {
        name: '交代種別',
        props: {
          substitutionRequest: {
            ...request,
            operations: sparseWithExtra(base),
          },
        },
        unavailable: 'substitution-unavailable',
      },
      {
        name: '交代前候補',
        props: {
          substitutionRequest: normal({
            outgoing: sparseWithExtra(base.outgoing[0]!),
          }),
        },
        unavailable: 'substitution-unavailable',
      },
      {
        name: '交代後候補',
        props: {
          substitutionRequest: normal({
            incoming: sparseWithExtra(base.incoming[0]!),
          }),
        },
        unavailable: 'substitution-unavailable',
      },
      {
        name: '登録質問',
        props: {
          substitutionRequest: normal({
            registrationQuestions: sparseWithExtra(
              base.registrationQuestions[0]!,
            ),
          }),
        },
        unavailable: 'substitution-unavailable',
      },
      {
        name: '配置質問',
        props: {
          substitutionRequest: normal({
            placementQuestions: sparseWithExtra(base.placementQuestions[0]!),
          }),
        },
        unavailable: 'substitution-unavailable',
      },
      {
        name: '交代質問',
        props: {
          substitutionRequest: normal({
            questions: sparseWithExtra(base.questions[0]!),
          }),
        },
        unavailable: 'substitution-unavailable',
      },
      {
        name: '交代選択肢',
        props: {
          substitutionRequest: normal({
            placementQuestions: [
              {
                ...base.placementQuestions[0]!,
                options: sparseWithExtra(
                  base.placementQuestions[0]!.options![0]!,
                ),
              },
            ],
          }),
        },
        unavailable: 'substitution-unavailable',
      },
      {
        name: '文字質問の余分な選択肢',
        props: {
          substitutionRequest: normal({
            registrationQuestions: [
              {
                ...base.registrationQuestions[0]!,
                options: sparseWithExtra({ id: 'x', label: '不正' }),
              },
            ],
          }),
        },
        unavailable: 'substitution-unavailable',
      },
      {
        name: '走者配置質問',
        props: {
          tiebreakRequest: {
            ...tiebreakRequest,
            placementQuestions: sparseWithExtra(
              tiebreakRequest.placementQuestions[0]!,
            ),
          },
        },
        unavailable: 'tiebreak-unavailable',
      },
      {
        name: '先頭打者質問',
        props: {
          tiebreakRequest: {
            ...tiebreakRequest,
            leadBatterQuestions: sparseWithExtra(
              tiebreakRequest.leadBatterQuestions[0]!,
            ),
          },
        },
        unavailable: 'tiebreak-unavailable',
      },
      {
        name: '回指定質問',
        props: {
          tiebreakRequest: {
            ...tiebreakRequest,
            inningQuestions: sparseWithExtra(
              tiebreakRequest.inningQuestions[0]!,
            ),
          },
        },
        unavailable: 'tiebreak-unavailable',
      },
      {
        name: '先頭打者選択肢',
        props: {
          tiebreakRequest: {
            ...tiebreakRequest,
            leadBatterQuestions: [
              {
                ...tiebreakRequest.leadBatterQuestions[0]!,
                options: sparseWithExtra(
                  tiebreakRequest.leadBatterQuestions[0]!.options![0]!,
                ),
              },
            ],
          },
        },
        unavailable: 'tiebreak-unavailable',
      },
      {
        name: '交代履歴',
        props: {
          pastSubstitutionRequest: {
            ...pastRequest,
            page: {
              ...pastRequest.page,
              targets: sparseWithExtra(pastRequest.page.targets[0]!),
            },
          },
        },
        unavailable: 'past-substitution-unavailable',
      },
      {
        name: '選手訂正質問',
        props: {
          pastSubstitutionRequest: {
            ...pastRequest,
            personQuestions: sparseWithExtra(pastRequest.personQuestions[0]!),
          },
        },
        unavailable: 'past-substitution-unavailable',
      },
      {
        name: '回訂正質問',
        props: {
          pastSubstitutionRequest: {
            ...pastRequest,
            inningQuestions: sparseWithExtra(pastRequest.inningQuestions[0]!),
          },
        },
        unavailable: 'past-substitution-unavailable',
      },
      {
        name: '時点訂正質問',
        props: {
          pastSubstitutionRequest: {
            ...pastRequest,
            timingQuestions: sparseWithExtra(pastRequest.timingQuestions[0]!),
          },
        },
        unavailable: 'past-substitution-unavailable',
      },
      {
        name: '選手訂正選択肢',
        props: {
          pastSubstitutionRequest: {
            ...pastRequest,
            personQuestions: [
              {
                ...pastRequest.personQuestions[0]!,
                options: sparseWithExtra(
                  pastRequest.personQuestions[0]!.options![0]!,
                ),
              },
            ],
          },
        },
        unavailable: 'past-substitution-unavailable',
      },
    ]
    for (const item of sparseCases) {
      const wrapper = mountScreen(item.props)
      expect(
        wrapper.get(`[data-testid="${item.unavailable}"]`).text(),
        item.name,
      ).toContain('未取得')
      expect(
        wrapper.get('[data-testid="stop-status"]').text(),
        item.name,
      ).toContain('未取得')
      expect(
        wrapper.get<HTMLButtonElement>('[data-testid="substitution-apply"]')
          .element.disabled,
        item.name,
      ).toBe(true)
      wrapper.unmount()
    }
    expect(Object.keys(sparseWithExtra(base))).toHaveLength(2)
  })

  it('親の公開通知で不変下書きを毎変更・消去・文脈変更ごとに渡し、実操作を発行しない', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountScreen()
    const initial = raw(wrapper)
    expect(Object.isFrozen(initial)).toBe(true)
    expect(initial.normal).toBeNull()
    const eventCount = () =>
      wrapper.emitted('substitution-draft-change')?.length ?? 0
    const firstCount = eventCount()
    await wrapper.get('[data-testid="substitution-kind"]').setValue('pitcher')
    expect(eventCount()).toBe(firstCount + 1)
    const selected = raw(wrapper)
    expect(Object.isFrozen(selected.normal)).toBe(true)
    expect(Object.isFrozen(selected.normal?.identity)).toBe(true)
    expect(Object.isFrozen(selected.normal?.answers)).toBe(true)
    await wrapper
      .get('[data-testid="substitution-outgoing"]')
      .setValue('pitcher-out')
    expect(eventCount()).toBe(firstCount + 2)
    expect(selected.normal?.outgoingId).toBeNull()
    expect(raw(wrapper).normal?.outgoingId).toBe('pitcher-out')
    await wrapper.get('[data-testid="substitution-outgoing"]').setValue('')
    expect(eventCount()).toBe(firstCount + 3)
    expect(raw(wrapper).normal?.outgoingId).toBeNull()
    await wrapper.get('[data-tiebreak-question="runner"]').setValue('runner-a')
    expect(eventCount()).toBe(firstCount + 4)
    expect(Object.isFrozen(raw(wrapper).tiebreak?.answers)).toBe(true)
    await wrapper
      .get('[data-testid="past-substitution-target"]')
      .setValue('history-a')
    expect(eventCount()).toBe(firstCount + 5)
    expect(Object.isFrozen(raw(wrapper).past?.identity)).toBe(true)
    await wrapper.get('[data-testid="past-substitution-target"]').setValue('')
    expect(eventCount()).toBe(firstCount + 6)
    expect(raw(wrapper).past).toBeNull()
    await wrapper.setProps({
      substitutionValidation: {
        identity: raw(wrapper).normal!.identity,
        kind: 'pending',
      },
    })
    expect(eventCount()).toBe(firstCount + 6)
    await wrapper.setProps({ substitutionContextKey: 'game-b' })
    expect(eventCount()).toBe(firstCount + 7)
    expect(raw(wrapper).normal).toBeNull()
    expect(raw(wrapper).past).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.emitted('save')).toBeUndefined()
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.emitted('apply')).toBeUndefined()
  })

  it.each(kinds)(
    '%s の候補だけを手動選択し、未選択を null に保つ',
    async (kind) => {
      const wrapper = mountScreen()
      await wrapper.get('[data-testid="substitution-kind"]').setValue(kind)
      expect(raw(wrapper).normal?.outgoingId).toBeNull()
      expect(raw(wrapper).normal?.incomingMode).toBeNull()
      expect(raw(wrapper).normal?.incomingId).toBeNull()
      expect(raw(wrapper).normal?.answers).toEqual({ order: null, place: null })
      expect(
        wrapper.get('[data-testid="substitution-incoming-mode"]').text(),
      ).toContain('その場で選手を登録')
      await wrapper
        .get('[data-testid="substitution-outgoing"]')
        .setValue(`${kind}-out`)
      await wrapper
        .get('[data-testid="substitution-incoming-mode"]')
        .setValue('existing')
      await wrapper
        .get('[data-testid="substitution-incoming"]')
        .setValue(`${kind}-in`)
      await wrapper
        .get('[data-normal-question="place"]')
        .setValue('provided-dh')
      expect(raw(wrapper).normal).toMatchObject({
        outgoingId: `${kind}-out`,
        incomingMode: 'existing',
        incomingId: `${kind}-in`,
        answers: { order: null, place: 'provided-dh' },
      })
      expect(
        wrapper
          .findAll('[data-normal-question="place"] option')
          .map((item) => item.text()),
      ).toEqual(['未選択', '指名打者', '投手'])
      expect(
        wrapper.get('[data-testid="substitution-validation"]').text(),
      ).toContain('未取得')
    },
  )

  it('その場登録は提供された質問だけを入力し、未知の候補を採用しない', async () => {
    const wrapper = mountScreen()
    await wrapper.get('[data-testid="substitution-kind"]').setValue('defense')
    await wrapper
      .get('[data-testid="substitution-incoming-mode"]')
      .setValue('new')
    expect(raw(wrapper).normal?.incomingId).toBeNull()
    expect(raw(wrapper).normal?.answers['new-name']).toBeNull()
    await wrapper
      .get('[data-normal-question="new-name"]')
      .setValue('新しい選手')
    await wrapper.get('[data-normal-question="place"]').setValue('provided-p')
    expect(raw(wrapper).normal?.answers).toMatchObject({
      'new-name': '新しい選手',
      place: 'provided-p',
    })
    expect(
      wrapper
        .findAll('[data-normal-question="place"] option')
        .map((item) => item.attributes('value')),
    ).not.toContain('unknown')
    expect(wrapper.find('[data-testid="substitution-incoming"]').exists()).toBe(
      false,
    )
  })

  it('必須質問を通常・登録・配置・タイブレーク・過去訂正のラベルに示す', async () => {
    const wrapper = mountScreen()
    await wrapper.get('[data-testid="substitution-kind"]').setValue('defense')
    await wrapper
      .get('[data-testid="substitution-incoming-mode"]')
      .setValue('new')
    for (const selector of [
      '[data-normal-question="order"]',
      '[data-normal-question="place"]',
      '[data-normal-question="new-name"]',
      '[data-tiebreak-question="runner"]',
      '[data-tiebreak-question="lead"]',
      '[data-tiebreak-question="inning"]',
      '[data-past-question="person"]',
      '[data-past-question="past-inning"]',
      '[data-past-question="timing"]',
    ]) {
      expect(
        wrapper.get(selector).element.closest('label')?.textContent,
      ).toContain('（必須）')
    }
    expect(wrapper.findAll('fieldset legend').length).toBeGreaterThan(0)
    const optional = {
      ...structuredClone(request),
      operations: [
        {
          ...operation('pitcher'),
          questions: [
            {
              key: 'note',
              label: '任意のメモ',
              input: 'text' as const,
              required: false,
            },
          ],
        },
      ],
    }
    await wrapper.setProps({ substitutionRequest: optional })
    await wrapper.get('[data-testid="substitution-kind"]').setValue('pitcher')
    expect(
      wrapper.get('[data-normal-question="note"]').element.closest('label')
        ?.textContent,
    ).not.toContain('（必須）')
  })

  it('入る選手の指定方法を変えて回答が消えた理由を通知する', async () => {
    const wrapper = mountScreen()
    await wrapper.get('[data-testid="substitution-kind"]').setValue('pitcher')
    await wrapper
      .get('[data-testid="substitution-incoming-mode"]')
      .setValue('existing')
    await wrapper
      .get('[data-testid="substitution-incoming"]')
      .setValue('pitcher-in')
    await wrapper.get('[data-normal-question="place"]').setValue('provided-p')
    await wrapper
      .get('[data-testid="substitution-incoming-mode"]')
      .setValue('new')
    const notice = wrapper.get(
      '[data-testid="substitution-mode-draft-cleared"]',
    )
    expect(notice.attributes('role')).toBe('status')
    expect(notice.text()).toContain('消去しました')
    expect(raw(wrapper).normal?.incomingId).toBeNull()
    expect(raw(wrapper).normal?.answers.place).toBeNull()
  })

  it('タイブレーク配置・先頭打者・回の質問に表示名があり、自動選択しない', async () => {
    const wrapper = mountScreen()
    expect(raw(wrapper).tiebreak?.answers).toEqual({
      runner: null,
      lead: null,
      inning: null,
    })
    for (const name of ['走者の配置', '先頭打者', '回の指定']) {
      expect(wrapper.findAll('fieldset legend').length).toBeGreaterThan(0)
      expect(wrapper.text()).toContain(name)
    }
    expect(
      wrapper.get('[data-tiebreak-question="runner"]').element.closest('label')
        ?.textContent,
    ).toContain('タイブレーク走者の配置')
    await wrapper.get('[data-tiebreak-question="runner"]').setValue('runner-a')
    await wrapper.get('[data-tiebreak-question="lead"]').setValue('batter-a')
    await wrapper.get('[data-tiebreak-question="inning"]').setValue('inning-a')
    expect(raw(wrapper).tiebreak?.answers).toEqual({
      runner: 'runner-a',
      lead: 'batter-a',
      inning: 'inning-a',
    })
  })

  it('過去交代の一ページから対象・人・回・時点を入力し、下流プレビュー4状態だけを表示する', async () => {
    const wrapper = mountScreen()
    expect(
      wrapper.get('[data-testid="past-substitution-target"]').text(),
    ).toContain('7回表の投手交代')
    expect(
      wrapper.get('[data-testid="past-substitution-next"]').text(),
    ).toContain('準備中')
    await wrapper
      .get('[data-testid="past-substitution-target"]')
      .setValue('history-a')
    await wrapper.setProps({
      pastSubstitutionPreview: {
        identity: raw(wrapper).past!.identity,
        kind: 'ready',
        rows: [{ label: '空欄の旧結果', before: '前', after: '後' }],
      },
    })
    expect(
      wrapper.get('[data-testid="past-substitution-preview-status"]').text(),
    ).toContain('未取得')
    expect(wrapper.text()).not.toContain('空欄の旧結果')
    await wrapper.get('[data-past-question="person"]').setValue('person-a')
    await wrapper
      .get('[data-past-question="past-inning"]')
      .setValue('past-inning-a')
    await wrapper.get('[data-past-question="timing"]').setValue('交代後')
    const draft = raw(wrapper).past!
    expect(draft.answers).toEqual({
      person: 'person-a',
      'past-inning': 'past-inning-a',
      timing: '交代後',
    })
    expect(
      wrapper.get('[data-testid="past-substitution-preview-status"]').text(),
    ).toContain('未取得')
    for (const [kind, expected] of [
      ['pending', '準備中'],
      ['failed', '取得できません'],
      ['conflict', '競合'],
    ] as const) {
      const preview: PastSubstitutionPreview = {
        identity: draft.identity,
        kind,
      }
      await wrapper.setProps({ pastSubstitutionPreview: preview })
      expect(
        wrapper.get('[data-testid="past-substitution-preview-status"]').text(),
      ).toContain(expected)
      expect(
        wrapper.find('[data-testid="past-substitution-preview-rows"]').exists(),
      ).toBe(false)
    }
    await wrapper.setProps({
      pastSubstitutionPreview: {
        identity: draft.identity,
        kind: 'ready',
        rows: [
          {
            label: '投手の帰属',
            before: '変更前の選手',
            after: '<img src=x onerror=alert(1)>',
          },
        ],
      },
    })
    expect(
      wrapper.get('[data-testid="past-substitution-preview-rows"]').text(),
    ).toContain('投手の帰属')
    expect(
      wrapper.get('[data-testid="past-substitution-preview-status"]').text(),
    ).toContain('まだ行われていません')
    expect(
      wrapper
        .get('[data-testid="past-substitution-preview-rows"]')
        .find('img')
        .exists(),
    ).toBe(false)
  })

  it('対象・下書き・操作・文脈・画面インスタンスが違う古いプレビューを拒否する', async () => {
    const wrapper = mountScreen()
    await wrapper
      .get('[data-testid="past-substitution-target"]')
      .setValue('history-a')
    await wrapper.get('[data-past-question="person"]').setValue('person-a')
    await wrapper
      .get('[data-past-question="past-inning"]')
      .setValue('past-inning-a')
    await wrapper.get('[data-past-question="timing"]').setValue('交代後')
    const current = raw(wrapper).past!
    const row = { label: '秘密の旧結果', before: '前', after: '後' }
    for (const identity of [
      { ...current.identity, contextKey: 'game-b' },
      { ...current.identity, operation: 'pitcher' as const },
      { ...current.identity, targetId: 'history-b' },
      { ...current.identity, draftId: current.identity.draftId + 1 },
      { ...current.identity, uiInstanceId: 'other-instance' },
    ]) {
      await wrapper.setProps({
        pastSubstitutionPreview: { identity, kind: 'ready', rows: [row] },
      })
      expect(
        wrapper.get('[data-testid="past-substitution-preview-status"]').text(),
      ).toContain('未取得')
      expect(wrapper.text()).not.toContain('秘密の旧結果')
    }
    await wrapper.setProps({
      pastSubstitutionPreview: {
        identity: current.identity,
        kind: 'ready',
        rows: [row],
      },
    })
    expect(wrapper.text()).toContain('秘密の旧結果')
    await wrapper.get('[data-past-question="timing"]').setValue('新しい時点')
    expect(wrapper.text()).not.toContain('秘密の旧結果')
    wrapper.unmount()
    const remounted = mountScreen({
      pastSubstitutionPreview: {
        identity: current.identity,
        kind: 'ready',
        rows: [row],
      },
    })
    await remounted
      .get('[data-testid="past-substitution-target"]')
      .setValue('history-a')
    await remounted.get('[data-past-question="person"]').setValue('person-a')
    await remounted
      .get('[data-past-question="past-inning"]')
      .setValue('past-inning-a')
    await remounted.get('[data-past-question="timing"]').setValue('交代後')
    expect(remounted.text()).not.toContain('秘密の旧結果')
  })

  it('同内容の新参照は保持し、要求・文脈変更で各下書きを破棄して理由を表示する', async () => {
    const wrapper = mountScreen()
    await wrapper.get('[data-testid="substitution-kind"]').setValue('pitcher')
    await wrapper.get('[data-tiebreak-question="runner"]').setValue('runner-a')
    await wrapper
      .get('[data-testid="past-substitution-target"]')
      .setValue('history-a')
    const before = raw(wrapper)
    await wrapper.setProps({
      substitutionRequest: structuredClone(request),
      tiebreakRequest: structuredClone(tiebreakRequest),
      pastSubstitutionRequest: structuredClone(pastRequest),
    })
    expect(raw(wrapper)).toEqual(before)
    await wrapper.setProps({ substitutionContextKey: 'game-b' })
    expect(raw(wrapper).normal).toBeNull()
    expect(raw(wrapper).tiebreak).toBeNull()
    expect(raw(wrapper).past).toBeNull()
    for (const id of [
      'substitution-draft-cleared',
      'tiebreak-draft-cleared',
      'past-substitution-draft-cleared',
    ]) {
      expect(wrapper.get(`[data-testid="${id}"]`).text()).toContain(
        '消去しました',
      )
    }
  })

  it('同じ文脈でも提供候補や訂正対象の実変更だけを消去し、別フォームは保持する', async () => {
    const wrapper = mountScreen()
    await wrapper
      .get('[data-testid="substitution-kind"]')
      .setValue('pinch-runner')
    await wrapper.get('[data-tiebreak-question="lead"]').setValue('batter-a')
    await wrapper
      .get('[data-testid="past-substitution-target"]')
      .setValue('history-a')
    const tiebreakBefore = raw(wrapper).tiebreak
    await wrapper.setProps({
      substitutionRequest: {
        ...structuredClone(request),
        operations: request.operations.map((item) =>
          item.kind === 'pinch-runner'
            ? { ...item, incoming: [{ id: 'another', label: '別の候補' }] }
            : item,
        ),
      },
    })
    expect(raw(wrapper).normal).toBeNull()
    expect(raw(wrapper).tiebreak).toEqual(tiebreakBefore)
    expect(raw(wrapper).past?.identity.targetId).toBe('history-a')
    expect(
      wrapper.get('[data-testid="substitution-draft-cleared"]').text(),
    ).toContain('消去')
    await wrapper.setProps({
      pastSubstitutionRequest: {
        ...structuredClone(pastRequest),
        page: { ...pastRequest.page, targets: [] },
      },
    })
    expect(raw(wrapper).past).toBeNull()
    expect(
      wrapper.get('[data-testid="past-substitution-draft-cleared"]').text(),
    ).toContain('消去')
    expect(raw(wrapper).tiebreak).toEqual(tiebreakBefore)
  })

  it('提供検証だけを照合し、未知状態・欠落・不正要求を成功扱いしない', async () => {
    const wrapper = mountScreen()
    await wrapper.get('[data-testid="substitution-kind"]').setValue('pitcher')
    const identity = raw(wrapper).normal!.identity
    await wrapper.setProps({
      substitutionValidation: { identity, kind: 'pending' },
    })
    expect(
      wrapper.get('[data-testid="substitution-validation"]').text(),
    ).toContain('検証を待っています')
    await wrapper.setProps({ substitutionValidation: null })
    expect(
      wrapper.get('[data-testid="substitution-validation"]').text(),
    ).toContain('未取得')
    await wrapper.setProps({
      substitutionValidation: {
        identity,
        kind: 'valid',
        messages: ['提供側の確認結果'],
      },
    })
    expect(
      wrapper.get('[data-testid="substitution-validation"]').text(),
    ).toContain('検証済みとして扱えません')
    expect(wrapper.text()).not.toContain('提供側の確認結果')
    await wrapper
      .get('[data-testid="substitution-outgoing"]')
      .setValue('pitcher-out')
    await wrapper
      .get('[data-testid="substitution-incoming-mode"]')
      .setValue('existing')
    await wrapper
      .get('[data-testid="substitution-incoming"]')
      .setValue('pitcher-in')
    await wrapper.get('[data-normal-question="place"]').setValue('provided-p')
    await wrapper
      .get('[data-normal-question="order"]')
      .setValue('provided-order')
    const completeIdentity = raw(wrapper).normal!.identity
    await wrapper.setProps({
      substitutionValidation: {
        identity: completeIdentity,
        kind: 'valid',
        messages: ['提供側の確認結果'],
      },
    })
    expect(
      wrapper.get('[data-testid="substitution-validation"]').text(),
    ).toContain('提供側の確認結果')
    await wrapper.setProps({
      substitutionLockState: {
        contextKey: 'game-a',
        state: 'ending-locked-undo-unavailable',
      } satisfies SubstitutionLockState,
    })
    expect(
      wrapper.get('[data-testid="substitution-validation"]').text(),
    ).toContain('終了条件により交代できません')
    expect(
      wrapper.get('[data-testid="substitution-validation"]').text(),
    ).toContain('変更は行われていません')
    await wrapper.setProps({ substitutionLockState: null })
    expect(
      wrapper.get('[data-testid="substitution-validation"]').text(),
    ).toContain('終了条件の状態は未取得')
    expect(
      wrapper.get<HTMLButtonElement>('[data-testid="substitution-apply"]')
        .element.disabled,
    ).toBe(true)
    await wrapper.get('[data-normal-question="place"]').setValue('')
    expect(
      wrapper.get('[data-testid="substitution-validation"]').text(),
    ).toContain('未取得')
    await wrapper.setProps({
      substitutionValidation: {
        identity: completeIdentity,
        kind: 'unknown',
      } as unknown as SubstitutionValidation,
    })
    expect(
      wrapper.get('[data-testid="substitution-validation"]').text(),
    ).toContain('未取得')
    await wrapper.setProps({
      substitutionRequest: {
        ...request,
        operations: [
          { ...operation('pitcher'), kind: 'unknown' as SubstitutionKind },
        ],
      },
    })
    expect(
      wrapper.get('[data-testid="substitution-unavailable"]').text(),
    ).toContain('未取得')
    await wrapper.setProps({
      substitutionRequest: {
        ...request,
        operations: [
          {
            ...operation('pitcher'),
            questions: [{ key: 'missing', label: '必須性不明', input: 'text' }],
          },
        ],
      } as unknown as SubstitutionRequest,
    })
    expect(
      wrapper.get('[data-testid="substitution-unavailable"]').text(),
    ).toContain('未取得')
    await wrapper.setProps({
      substitutionRequest: null,
      tiebreakRequest: null,
      pastSubstitutionRequest: null,
    })
    expect(
      wrapper.get('[data-testid="tiebreak-unavailable"]').text(),
    ).toContain('未取得')
    expect(
      wrapper.get('[data-testid="past-substitution-unavailable"]').text(),
    ).toContain('未取得')
  })

  it('質問ゼロ、不正な変更行、未知の状態を取得済みの確認結果として扱わない', async () => {
    const emptyQuestions: SubstitutionRequest = {
      contextKey: 'game-a',
      operations: [
        { ...operation('pitcher'), questions: [], placementQuestions: [] },
      ],
    }
    const wrapper = mountScreen({ substitutionRequest: emptyQuestions })
    await wrapper.get('[data-testid="substitution-kind"]').setValue('pitcher')
    await wrapper
      .get('[data-testid="substitution-outgoing"]')
      .setValue('pitcher-out')
    await wrapper
      .get('[data-testid="substitution-incoming-mode"]')
      .setValue('existing')
    await wrapper
      .get('[data-testid="substitution-incoming"]')
      .setValue('pitcher-in')
    await wrapper.setProps({
      substitutionValidation: {
        identity: raw(wrapper).normal!.identity,
        kind: 'valid',
        messages: ['表示してはいけない確認結果'],
      },
    })
    expect(
      wrapper.get('[data-testid="substitution-validation"]').text(),
    ).toContain('入力項目を確認できない')
    expect(wrapper.text()).not.toContain('表示してはいけない確認結果')
    await wrapper
      .get('[data-testid="past-substitution-target"]')
      .setValue('history-a')
    await wrapper.get('[data-past-question="person"]').setValue('person-a')
    await wrapper
      .get('[data-past-question="past-inning"]')
      .setValue('past-inning-a')
    await wrapper.get('[data-past-question="timing"]').setValue('交代後')
    const pastIdentity = raw(wrapper).past!.identity
    for (const preview of [
      { identity: pastIdentity, kind: 'ready' },
      { identity: pastIdentity, kind: 'ready', rows: [] },
      {
        identity: pastIdentity,
        kind: 'ready',
        rows: [{ label: {}, before: '前', after: '後' }],
      },
      {
        identity: pastIdentity,
        kind: 'unknown',
        rows: [{ label: '不明', before: '前', after: '後' }],
      },
    ]) {
      await wrapper.setProps({
        pastSubstitutionPreview: preview as unknown as PastSubstitutionPreview,
      })
      expect(
        wrapper.get('[data-testid="past-substitution-preview-status"]').text(),
      ).toContain('未取得')
      expect(
        wrapper.find('[data-testid="past-substitution-preview-rows"]').exists(),
      ).toBe(false)
    }
    await wrapper.setProps({
      pastSubstitutionPreview: { identity: pastIdentity, kind: 'pending' },
    })
    expect(
      wrapper.get('[data-testid="past-substitution-preview-status"]').text(),
    ).toContain('準備中')
  })

  it('検証文言と変更行の疎配列は提供結果として描画しない', async () => {
    const wrapper = mountScreen()
    await wrapper.get('[data-testid="substitution-kind"]').setValue('pitcher')
    await wrapper
      .get('[data-testid="substitution-outgoing"]')
      .setValue('pitcher-out')
    await wrapper
      .get('[data-testid="substitution-incoming-mode"]')
      .setValue('existing')
    await wrapper
      .get('[data-testid="substitution-incoming"]')
      .setValue('pitcher-in')
    await wrapper.get('[data-normal-question="place"]').setValue('provided-p')
    await wrapper
      .get('[data-normal-question="order"]')
      .setValue('provided-order')
    await wrapper.setProps({
      substitutionValidation: {
        identity: raw(wrapper).normal!.identity,
        kind: 'valid',
        messages: sparseWithExtra('穴の後の検証文言'),
      },
    })
    expect(
      wrapper.get('[data-testid="substitution-validation"]').text(),
    ).toContain('未取得')
    expect(wrapper.text()).not.toContain('穴の後の検証文言')
    await wrapper
      .get('[data-testid="past-substitution-target"]')
      .setValue('history-a')
    await wrapper.get('[data-past-question="person"]').setValue('person-a')
    await wrapper
      .get('[data-past-question="past-inning"]')
      .setValue('past-inning-a')
    await wrapper.get('[data-past-question="timing"]').setValue('交代後')
    await wrapper.setProps({
      pastSubstitutionPreview: {
        identity: raw(wrapper).past!.identity,
        kind: 'ready',
        rows: sparseWithExtra({
          label: '穴の後の変更行',
          before: '前',
          after: '後',
        }),
      },
    })
    expect(
      wrapper.get('[data-testid="past-substitution-preview-status"]').text(),
    ).toContain('未取得')
    expect(wrapper.text()).not.toContain('穴の後の変更行')
    expect(wrapper.get('[data-testid="stop-status"]').text()).toContain(
      '未取得',
    )
  })

  it('終了ロックと既存undo表示を整合させ、実操作は常に封鎖する', async () => {
    const wrapper = mountScreen({
      substitutionLockState: {
        contextKey: 'game-a',
        state: 'ending-locked-undo-available',
      } satisfies SubstitutionLockState,
      undoOffer: {
        kind: 'available',
        operationLabel: '交代',
        targetLabel: '直前の操作',
      },
    })
    expect(
      wrapper.get('[data-testid="substitution-lock-status"]').text(),
    ).toContain('交代できません')
    expect(
      wrapper.get('[data-testid="substitution-lock-status"]').text(),
    ).toContain('対象は未取得')
    expect(wrapper.get('[data-testid="undo-target-status"]').text()).toContain(
      '未取得',
    )
    const staleOffer = {
      kind: 'available' as const,
      contextKey: 'game-b',
      operationLabel: '交代',
      targetLabel: '古い試合の操作',
    }
    await wrapper.setProps({ undoOffer: staleOffer, undoContextKey: 'game-a' })
    expect(
      wrapper.get('[data-testid="substitution-lock-status"]').text(),
    ).toContain('対象は未取得')
    expect(wrapper.get('[data-testid="undo-target-status"]').text()).toContain(
      '未取得',
    )
    await wrapper.setProps({ undoContextKey: 'game-b' })
    expect(
      wrapper.get('[data-testid="substitution-lock-status"]').text(),
    ).toContain('対象は未取得')
    expect(wrapper.get('[data-testid="undo-target-status"]').text()).toContain(
      '未取得',
    )
    const currentOffer = {
      ...staleOffer,
      contextKey: 'game-a',
      targetLabel: '直前の操作',
    }
    await wrapper.setProps({
      undoOffer: currentOffer,
      undoContextKey: 'game-a',
    })
    expect(
      wrapper.get('[data-testid="substitution-lock-status"]').text(),
    ).toContain('対象は上の欄にあります')
    expect(wrapper.get('[data-testid="undo-target-status"]').text()).toContain(
      '直前の操作',
    )
    await wrapper.setProps({ undoOffer: { ...currentOffer, targetLabel: '' } })
    expect(
      wrapper.get('[data-testid="substitution-lock-status"]').text(),
    ).toContain('対象は未取得')
    expect(wrapper.get('[data-testid="undo-target-status"]').text()).toContain(
      '未取得',
    )
    const noTarget = { kind: 'none' as const, contextKey: 'game-a' }
    await wrapper.setProps({
      undoOffer: noTarget,
      substitutionLockState: {
        contextKey: 'game-a',
        state: 'ending-locked-undo-unavailable',
      } satisfies SubstitutionLockState,
    })
    expect(
      wrapper.get('[data-testid="substitution-lock-status"]').text(),
    ).toContain('対象もありません')
    expect(wrapper.get('[data-testid="undo-target-status"]').text()).toContain(
      'ありません',
    )
    await wrapper.setProps({
      substitutionLockState: {
        contextKey: 'game-a',
        state: 'nonsense',
      } as unknown as SubstitutionLockState,
    })
    expect(
      wrapper.get('[data-testid="substitution-lock-status"]').text(),
    ).toContain('未取得')
  })

  it('ロックの旧文脈・欠落・空白・未知状態を未取得に閉じる', async () => {
    const wrapper = mountScreen({
      substitutionLockState: {
        contextKey: 'game-a',
        state: 'open',
      } satisfies SubstitutionLockState,
    })
    const lock = () =>
      wrapper.get('[data-testid="substitution-lock-status"]').text()
    expect(lock()).toContain('制限はありません')
    await wrapper.setProps({ substitutionContextKey: 'game-b' })
    expect(lock()).toContain('未取得')
    await wrapper.setProps({ substitutionContextKey: 'game-a' })
    expect(lock()).toContain('制限はありません')
    for (const state of [
      null,
      { contextKey: '', state: 'open' },
      { contextKey: '   ', state: 'open' },
      { state: 'open' },
      { contextKey: 'game-a' },
      { contextKey: 'game-a', state: 'unknown' },
      { contextKey: 'game-a', state: 'unexpected' },
    ]) {
      await wrapper.setProps({
        substitutionLockState: state as SubstitutionLockState | null,
      })
      expect(lock()).toContain('未取得')
      expect(lock()).not.toContain('制限はありません')
    }
    await wrapper.setProps({
      substitutionContextKey: '   ',
      substitutionLockState: { contextKey: '   ', state: 'open' },
    })
    expect(lock()).toContain('未取得')
  })

  it('取消対象と取消可否が矛盾しても両欄の対象表示を一致させる', async () => {
    const wrapper = mountScreen({
      substitutionLockState: {
        contextKey: 'game-a',
        state: 'ending-locked-undo-unavailable',
      } satisfies SubstitutionLockState,
      undoContextKey: 'game-a',
      undoOffer: {
        kind: 'available',
        contextKey: 'game-a',
        operationLabel: '投手交代',
        targetLabel: '直前の選手交代',
      },
    })
    const lock = () =>
      wrapper.get('[data-testid="substitution-lock-status"]').text()
    const target = () =>
      wrapper.get('[data-testid="undo-target-status"]').text()
    expect(target()).toContain('直前の選手交代')
    expect(lock()).toContain('対象は上の欄にあります')
    expect(lock()).toContain('取消可否は確認できません')
    expect(lock()).not.toContain('対象は未取得')
    await wrapper.setProps({
      substitutionLockState: {
        contextKey: 'game-a',
        state: 'ending-locked-undo-available',
      } satisfies SubstitutionLockState,
      undoOffer: { kind: 'none', contextKey: 'game-a' },
    })
    expect(target()).toContain('ありません')
    expect(lock()).toContain('対象はありません')
    expect(lock()).toContain('取消可否は確認できません')
    await wrapper.setProps({ undoContextKey: '   ' })
    expect(target()).toContain('未取得')
    expect(lock()).toContain('対象は未取得')
    await wrapper.setProps({
      substitutionContextKey: '   ',
      undoContextKey: '   ',
      undoOffer: { kind: 'none', contextKey: '   ' },
    })
    expect(target()).toContain('未取得')
    expect(lock()).toContain('未取得')
    expect(
      wrapper.get<HTMLButtonElement>('[data-testid="undo-action"]').element
        .disabled,
    ).toBe(true)
    expect(
      wrapper.get<HTMLButtonElement>('[data-testid="substitution-apply"]')
        .element.disabled,
    ).toBe(true)
  })

  it('全実操作の直接dispatchでも通信・操作イベントを起こさず、既存停止・観測・取消・確定を保つ', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem')
    const wrapper = mountScreen()
    const draftEventCount = wrapper.emitted('substitution-draft-change')?.length
    const ids = [
      'substitution-apply',
      'tiebreak-apply',
      'past-substitution-apply',
      'past-substitution-previous',
      'past-substitution-next',
      'undo-action',
      'resume-same-content',
      'correct-stopped-content',
      'commit-pitch',
    ]
    for (const id of ids) {
      const button = wrapper.get<HTMLButtonElement>(`[data-testid="${id}"]`)
      expect(button.element.disabled).toBe(true)
      button.element.dispatchEvent(
        new MouseEvent('click', { bubbles: true, cancelable: true }),
      )
    }
    await wrapper.vm.$nextTick()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(storageSpy).not.toHaveBeenCalled()
    expect(wrapper.emitted('substitution-draft-change')?.length).toBe(
      draftEventCount,
    )
    expect(wrapper.emitted('save')).toBeUndefined()
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.emitted('apply')).toBeUndefined()
    expect(wrapper.get('[data-testid="stop-status"]').text()).toContain(
      '未取得',
    )
    expect(
      wrapper.get('[data-testid="correction-request-unavailable"]').text(),
    ).toContain('未取得')
  })

  it('長い日本語を折り返す縦積み構造と質問のlabel/legendを備える', async () => {
    const wrapper = mountScreen()
    await wrapper.get('[data-testid="substitution-kind"]').setValue('defense')
    await wrapper
      .get('[data-testid="past-substitution-target"]')
      .setValue('history-a')
    const section = wrapper.get('[aria-label="選手交代とタイブレーク"]')
    expect(section.classes()).toContain('min-w-0')
    expect(
      section.findAll('fieldset legend').map((item) => item.text()),
    ).toEqual(
      expect.arrayContaining([
        '配置・守備位置',
        '走者の配置',
        '先頭打者',
        '回の指定',
        '選手の訂正',
        '回の訂正',
        '時点の訂正',
      ]),
    )
    expect(
      wrapper.get('[data-normal-question="place"]').element.closest('label')
        ?.textContent,
    ).toContain('守備位置または指名打者')
    expect(
      wrapper.get('[data-past-question="person"]').element.closest('label')
        ?.textContent,
    ).toContain('選手の訂正')
    expect(
      wrapper.get('[data-testid="past-substitution-detail"]').classes(),
    ).toContain('wrap-anywhere')
    expect(
      wrapper.get('[aria-label="過去の選手交代を訂正"]').classes(),
    ).toContain('min-w-0')
  })
})
