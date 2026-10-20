import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GameScreen from './GameScreen.vue'
import GameScreenPastCorrection from './GameScreenPastCorrection.vue'
import type {
  CorrectionDraft,
  CorrectionPrerequisites,
  CorrectionPreview,
  CorrectionRequest,
  UndoOffer,
} from './GameScreenCorrectionTypes'

const request: CorrectionRequest = {
  contextKey: 'game-a',
  page: {
    label: '1ページ目',
    targets: [
      {
        id: 'play-a',
        label: '7回表のプレイ',
        detail: '打者 ' + '長'.repeat(80),
      },
      { id: 'play-b', label: '7回裏のプレイ', detail: '二塁の走者あり' },
    ],
    hasPrevious: false,
    hasNext: true,
  },
  questions: {
    modify: [
      {
        key: 'result',
        label: '記録結果',
        input: 'choice',
        options: [
          { id: 'hit', label: '安打' },
          { id: 'error', label: '失策' },
        ],
      },
      { key: 'note', label: '補足', input: 'text' },
    ],
    insert: [
      {
        key: 'position',
        label: '挿入位置',
        input: 'choice',
        options: [
          { id: 'before', label: '対象の前' },
          { id: 'after', label: '対象の後' },
        ],
      },
      { key: 'play', label: 'プレイの内容', input: 'text' },
    ],
    delete: [{ key: 'reason', label: '削除の説明', input: 'text' }],
  },
}

const ready: CorrectionPrerequisites = {
  writer: 'held',
  queue: 'empty',
  connection: 'online',
}

function mountCorrection(overrides: Record<string, unknown> = {}) {
  return mount(GameScreen, {
    props: {
      correctionRequest: request,
      correctionContextKey: 'game-a',
      correctionPrerequisites: ready,
      ...overrides,
    },
  })
}

function draft(
  wrapper: ReturnType<typeof mountCorrection>,
): CorrectionDraft | null {
  return wrapper.findComponent(GameScreenPastCorrection).vm.getDraft()
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('直前の取消', () => {
  it('対象未取得・対象なしを区別し、取消入口を常に封鎖する', async () => {
    const wrapper = mount(GameScreen)
    expect(wrapper.get('[data-testid="undo-target-status"]').text()).toContain(
      '未取得',
    )
    expect(
      wrapper.get<HTMLButtonElement>('[data-testid="undo-action"]').element
        .disabled,
    ).toBe(true)
    await wrapper.setProps({ undoOffer: { kind: 'none' } })
    expect(wrapper.get('[data-testid="undo-target-status"]').text()).toContain(
      'ありません',
    )
    expect(
      wrapper.get<HTMLButtonElement>('[data-testid="undo-action"]').element
        .disabled,
    ).toBe(true)
  })

  it.each([
    { unsentCount: 1, syncedCount: 0 },
    { unsentCount: 0, syncedCount: 1 },
  ])('未送信/同期済みの件数で取消表示を分岐しない', (queue) => {
    const offer: UndoOffer = {
      kind: 'available',
      operationLabel: '直前のプレイ',
      targetLabel: '7回表の記録',
    }
    const wrapper = mount(GameScreen, { props: { undoOffer: offer, ...queue } })
    expect(wrapper.get('[data-testid="undo-target-status"]').text()).toContain(
      '7回表の記録',
    )
    expect(
      wrapper.get<HTMLButtonElement>('[data-testid="undo-action"]').element
        .disabled,
    ).toBe(true)
    expect(
      wrapper.get('[aria-label="直前の操作を取り消す"]').text(),
    ).not.toMatch(/未送信|同期済み/)
  })

  it('利用者には画面でできることを示し、実装用語を出さない', () => {
    const wrapper = mount(GameScreen, {
      props: {
        undoOffer: {
          kind: 'available',
          operationLabel: '直前のプレイ',
          targetLabel: '7回表の記録',
        },
      },
    })
    const text = wrapper.get('[aria-label="直前の操作を取り消す"]').text()
    expect(text).toContain('まだ取消できません')
    expect(text).not.toMatch(/正式|未提供|未接続|wire|DTO|API/)
  })
})

describe('過去プレイ修正の表示専用受取口', () => {
  it('利用者に状態と保存されないことを示し、実装用語を出さない', async () => {
    const wrapper = mountCorrection()
    await wrapper.get('[data-testid="correction-target"]').setValue('play-a')
    await wrapper.get('[data-testid="correction-operation"]').setValue('delete')
    await wrapper.get('[data-testid="correction-review"]').trigger('click')
    const text = wrapper.get('[aria-label="オンラインの過去プレイ修正"]').text()
    expect(text).toContain('履歴に残ります')
    expect(text).toContain('保存されません')
    expect(text).not.toMatch(/正式|未提供|未接続|wire|DTO|API|サーバー|キュー/)
  })
  it.each([
    [
      { writer: 'unknown', queue: 'unknown', connection: 'unknown' },
      ['未取得', '未取得', '未取得'],
    ],
    [
      { writer: 'not-held', queue: 'empty', connection: 'online' },
      ['保持していません', '記録はありません', 'オンライン'],
    ],
    [
      { writer: 'held', queue: 'not-empty', connection: 'online' },
      ['保持を確認済み', '記録があります', 'オンライン'],
    ],
    [
      { writer: 'held', queue: 'empty', connection: 'offline' },
      ['保持を確認済み', '記録はありません', '切れています'],
    ],
    [ready, ['保持を確認済み', '記録はありません', 'オンライン']],
  ] as const)(
    '提供された前提 %j を表示し、実確定は封鎖する',
    async (prerequisites, expected) => {
      const wrapper = mountCorrection({
        correctionPrerequisites: prerequisites,
      })
      expect(wrapper.get('[data-testid="correction-writer"]').text()).toContain(
        expected[0],
      )
      expect(wrapper.get('[data-testid="correction-queue"]').text()).toContain(
        expected[1],
      )
      expect(
        wrapper.get('[data-testid="correction-connection"]').text(),
      ).toContain(expected[2])
      await wrapper.get('[data-testid="correction-target"]').setValue('play-a')
      await wrapper
        .get('[data-testid="correction-operation"]')
        .setValue('modify')
      await wrapper.get('[data-testid="correction-review"]').trigger('click')
      expect(
        wrapper.get<HTMLButtonElement>('[data-testid="correction-apply"]')
          .element.disabled,
      ).toBe(true)
    },
  )

  it('要求未取得・旧文脈では入力を出さない', async () => {
    const wrapper = mountCorrection({ correctionRequest: null })
    expect(
      wrapper.get('[data-testid="correction-request-unavailable"]').text(),
    ).toContain('未取得')
    expect(wrapper.find('[data-testid="correction-target"]').exists()).toBe(
      false,
    )
    await wrapper.setProps({
      correctionRequest: request,
      correctionContextKey: 'game-b',
    })
    expect(wrapper.find('[data-testid="correction-target"]').exists()).toBe(
      false,
    )
  })

  it.each([
    ['modify', 'result', 'hit', '安打'],
    ['insert', 'position', 'after', '対象の後'],
    ['delete', 'reason', '説明の下書き', '説明の下書き'],
  ] as const)(
    '%s の質問を入力し確認画面に保持する',
    async (operation, key, value, label) => {
      const wrapper = mountCorrection()
      await wrapper.get('[data-testid="correction-target"]').setValue('play-a')
      await wrapper
        .get('[data-testid="correction-operation"]')
        .setValue(operation)
      await wrapper.get(`[data-question-key="${key}"]`).setValue(value)
      expect(draft(wrapper)?.answers[key]).toBe(value)
      await wrapper.get('[data-testid="correction-review"]').trigger('click')
      const confirmation = wrapper.get(
        '[data-testid="correction-confirmation"]',
      )
      expect(confirmation.text()).toContain(label)
      expect(confirmation.text()).toContain('7回表のプレイ')
      expect(confirmation.text()).toContain('終了後の追記再開も行いません')
      expect(
        confirmation.get<HTMLButtonElement>('[data-testid="correction-apply"]')
          .element.disabled,
      ).toBe(true)
      await confirmation.get('[data-testid="correction-back"]').trigger('click')
      expect(
        wrapper.get(`[data-question-key="${key}"]`).element,
      ).toHaveProperty('value', value)
    },
  )

  it('供給済みの一ページだけを表示し、ページ取得や全件集計をしない', () => {
    const wrapper = mountCorrection()
    expect(
      wrapper.get('[data-testid="correction-target"]').findAll('option'),
    ).toHaveLength(3)
    expect(
      wrapper
        .get('[data-testid="correction-previous-page"]')
        .attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper
        .get('[data-testid="correction-next-page"]')
        .attributes('disabled'),
    ).toBeDefined()
    expect(wrapper.text()).toContain('1ページ目')
  })

  it.each([375, 320])(
    '%dpx 向けの縦積みと長い名前の折返しを保つ',
    async (width) => {
      window.innerWidth = width
      window.dispatchEvent(new Event('resize'))
      const wrapper = mountCorrection()
      const section = wrapper.get('[aria-label="オンラインの過去プレイ修正"]')
      expect(section.classes()).toContain('min-w-0')
      expect(section.get('dl').classes()).toContain('grid-cols-1')
      expect(
        section.get('[data-testid="correction-previous-page"]').classes(),
      ).toContain('min-w-0')
      await section.get('[data-testid="correction-target"]').setValue('play-a')
      expect(
        section.get('[data-testid="correction-target-detail"]').text(),
      ).toContain('長'.repeat(80))
      expect(
        section.get('[data-testid="correction-target-detail"]').classes(),
      ).toContain('wrap-anywhere')
      expect(section.html()).not.toMatch(
        /\b(?:whitespace-nowrap|truncate|min-w-\[\d+px\])\b/,
      )
    },
  )

  it('準備中・失敗・競合・サーバー差分を表示し、内部原因やHTMLを出さない', async () => {
    const wrapper = mountCorrection()
    await wrapper.get('[data-testid="correction-target"]').setValue('play-a')
    await wrapper.get('[data-testid="correction-operation"]').setValue('modify')
    const identity = draft(wrapper)!.identity
    expect(
      wrapper.get('[data-testid="correction-preview-status"]').text(),
    ).toContain('準備中')
    for (const kind of ['pending', 'failed', 'conflict'] as const) {
      const preview: CorrectionPreview = {
        identity,
        kind,
        // 実行時に余分な内部原因が届いても利用者へ渡さない。
        internalCause: 'other-tenant-record-id',
      } as CorrectionPreview
      await wrapper.setProps({ correctionPreview: preview })
      expect(
        wrapper.get('[data-testid="correction-preview-status"]').text(),
      ).toContain(
        kind === 'pending'
          ? '準備中'
          : kind === 'failed'
            ? '取得できません'
            : '競合',
      )
      expect(wrapper.text()).not.toContain('other-tenant-record-id')
    }
    await wrapper.setProps({
      correctionPreview: {
        identity,
        kind: 'ready',
        rows: [
          {
            label: '下流の得点',
            before: '0',
            after: '<img src=x onerror=alert(1)>',
          },
        ],
      },
    })
    expect(
      wrapper.get('[data-testid="correction-diff-rows"]').text(),
    ).toContain('下流の得点')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(
      wrapper.get('[data-testid="correction-diff-rows"]').html(),
    ).toContain('&lt;img')
  })

  it('対象・操作・下書き・文脈の変更で前のプレビューを遮断する', async () => {
    const wrapper = mountCorrection()
    await wrapper.get('[data-testid="correction-target"]').setValue('play-a')
    await wrapper.get('[data-testid="correction-operation"]').setValue('modify')
    const oldIdentity = draft(wrapper)!.identity
    const oldPreview: CorrectionPreview = {
      identity: oldIdentity,
      kind: 'ready',
      rows: [{ label: '旧応答', before: '旧', after: '表示禁止' }],
    }
    await wrapper.setProps({ correctionPreview: oldPreview })
    expect(wrapper.text()).toContain('旧応答')
    await wrapper.get('[data-question-key="note"]').setValue('変更')
    expect(
      wrapper.get('[data-testid="correction-preview-status"]').text(),
    ).toContain('準備中')
    expect(wrapper.text()).not.toContain('旧応答')
    await wrapper.get('[data-testid="correction-operation"]').setValue('insert')
    expect(wrapper.text()).not.toContain('旧応答')
    await wrapper.get('[data-testid="correction-target"]').setValue('play-b')
    expect(wrapper.text()).not.toContain('旧応答')
    await wrapper.setProps({ correctionContextKey: 'game-b' })
    expect(draft(wrapper)).toBeNull()
    expect(wrapper.find('[data-testid="correction-preview"]').exists()).toBe(
      false,
    )
    expect(
      wrapper.get('[data-testid="correction-draft-cleared"]').text(),
    ).toContain('消去しました')
  })

  it('同内容の新参照では下書き・確認画面・対応プレビューを保持する', async () => {
    const wrapper = mountCorrection()
    await wrapper.get('[data-testid="correction-target"]').setValue('play-a')
    await wrapper.get('[data-testid="correction-operation"]').setValue('modify')
    await wrapper.get('[data-question-key="note"]').setValue('手入力の説明')
    const original = draft(wrapper)!
    await wrapper.setProps({
      correctionPreview: {
        identity: original.identity,
        kind: 'ready',
        rows: [{ label: '確認する差分', before: '前', after: '後' }],
      },
    })
    await wrapper.get('[data-testid="correction-review"]').trigger('click')
    await wrapper.setProps({ correctionRequest: structuredClone(request) })
    expect(draft(wrapper)).toEqual(original)
    expect(
      wrapper.get('[data-testid="correction-confirmation"]').text(),
    ).toContain('手入力の説明')
    expect(wrapper.text()).toContain('確認する差分')
    expect(
      wrapper.find('[data-testid="correction-draft-cleared"]').exists(),
    ).toBe(false)
  })

  it('要求内容の実変更では下書きを消し、理由を表示して旧プレビューを遮断する', async () => {
    const wrapper = mountCorrection()
    await wrapper.get('[data-testid="correction-target"]').setValue('play-a')
    await wrapper.get('[data-testid="correction-operation"]').setValue('modify')
    await wrapper.get('[data-question-key="note"]').setValue('旧下書き')
    const previous = draft(wrapper)!
    await wrapper.setProps({
      correctionPreview: {
        identity: previous.identity,
        kind: 'ready',
        rows: [{ label: '旧差分', before: '前', after: '後' }],
      },
      correctionRequest: {
        ...structuredClone(request),
        questions: {
          ...structuredClone(request.questions),
          modify: [
            { ...request.questions.modify[0]!, label: '更新された記録結果' },
            ...request.questions.modify.slice(1),
          ],
        },
      },
    })
    expect(draft(wrapper)).toBeNull()
    expect(
      wrapper.get('[data-testid="correction-draft-cleared"]').text(),
    ).toContain('前の下書きを消去')
    expect(wrapper.text()).not.toContain('旧差分')
    expect(
      wrapper.get<HTMLSelectElement>('[data-testid="correction-target"]')
        .element.value,
    ).toBe('')
  })

  it('再mount後に同じ入力手順でも旧インスタンスのプレビューを再掲しない', async () => {
    const randomUUID = vi
      .fn()
      .mockReturnValueOnce('ui-first')
      .mockReturnValueOnce('ui-second')
    vi.stubGlobal('crypto', { randomUUID })
    const first = mountCorrection()
    await first.get('[data-testid="correction-target"]').setValue('play-a')
    await first.get('[data-testid="correction-operation"]').setValue('modify')
    await first.get('[data-question-key="note"]').setValue('同じ入力')
    const previous = draft(first)!
    const preview: CorrectionPreview = {
      identity: previous.identity,
      kind: 'ready',
      rows: [{ label: '前画面の差分', before: '前', after: '後' }],
    }
    first.unmount()

    const second = mountCorrection({ correctionPreview: preview })
    await second.get('[data-testid="correction-target"]').setValue('play-a')
    await second.get('[data-testid="correction-operation"]').setValue('modify')
    await second.get('[data-question-key="note"]').setValue('同じ入力')
    const current = draft(second)!
    expect(current.identity.draftId).toBe(previous.identity.draftId)
    expect(current.identity.uiInstanceId).not.toBe(
      previous.identity.uiInstanceId,
    )
    expect(
      second.get('[data-testid="correction-preview-status"]').text(),
    ).toContain('準備中')
    expect(second.text()).not.toContain('前画面の差分')
    expect(randomUUID).toHaveBeenCalledTimes(2)
  })

  it('画面識別子を生成できなくても入力と確認を保ち、プレビューを閉じる', async () => {
    vi.stubGlobal('crypto', undefined)
    const wrapper = mountCorrection({
      correctionPreview: {
        identity: {
          contextKey: 'game-a',
          uiInstanceId: 'old',
          draftId: 3,
          targetId: 'play-a',
          operation: 'modify',
        },
        kind: 'ready',
        rows: [{ label: '表示してはいけない差分', before: '前', after: '後' }],
      },
    })
    await wrapper.get('[data-testid="correction-target"]').setValue('play-a')
    await wrapper.get('[data-testid="correction-operation"]').setValue('modify')
    expect(draft(wrapper)).toBeNull()
    expect(
      wrapper.get('[data-testid="correction-preview-unavailable"]').text(),
    ).toContain('確認できません')
    expect(wrapper.text()).not.toContain('表示してはいけない差分')
    await wrapper.get('[data-testid="correction-review"]').trigger('click')
    expect(
      wrapper.find('[data-testid="correction-confirmation"]').exists(),
    ).toBe(true)
    expect(
      wrapper.get<HTMLButtonElement>('[data-testid="correction-apply"]').element
        .disabled,
    ).toBe(true)
  })

  it.each([
    { contextKey: 'game-b' },
    { uiInstanceId: 'previous-ui' },
    { draftId: -1 },
    { targetId: 'play-b' },
    { operation: 'delete' as const },
  ])('プレビュー識別子の不一致 %j を表示しない', async (mismatch) => {
    const wrapper = mountCorrection()
    await wrapper.get('[data-testid="correction-target"]').setValue('play-a')
    await wrapper.get('[data-testid="correction-operation"]').setValue('modify')
    const identity = draft(wrapper)!.identity
    await wrapper.setProps({
      correctionPreview: {
        identity: { ...identity, ...mismatch },
        kind: 'ready',
        rows: [{ label: '別要求の差分', before: '前', after: '後' }],
      },
    })
    expect(
      wrapper.get('[data-testid="correction-preview-status"]').text(),
    ).toContain('準備中')
    expect(wrapper.text()).not.toContain('別要求の差分')
  })

  it('直接dispatchでも取消・修正・削除・ページ送りの通信、保存、イベント発行が0', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    const save = vi.spyOn(Storage.prototype, 'setItem')
    const wrapper = mountCorrection({
      undoOffer: {
        kind: 'available',
        operationLabel: '直前',
        targetLabel: 'プレイ',
      },
    })
    await wrapper.get('[data-testid="correction-target"]').setValue('play-a')
    await wrapper.get('[data-testid="correction-operation"]').setValue('delete')
    for (const selector of [
      'correction-previous-page',
      'correction-next-page',
    ]) {
      wrapper
        .get(`[data-testid="${selector}"]`)
        .element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    }
    await wrapper.get('[data-testid="correction-review"]').trigger('click')
    for (const selector of [
      'undo-action',
      'correction-apply',
      'commit-pitch',
    ]) {
      wrapper
        .get(`[data-testid="${selector}"]`)
        .element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    }
    expect(fetch).not.toHaveBeenCalled()
    expect(save).not.toHaveBeenCalled()
    for (const event of [
      'undo',
      'correct',
      'insert',
      'delete',
      'save',
      'send',
    ]) {
      expect(wrapper.emitted(event)).toBeUndefined()
    }
    expect(wrapper.text()).not.toMatch(/保存しました|修正しました|削除しました/)
  })
})
