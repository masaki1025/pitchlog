import { mount } from '@vue/test-utils'
import { h, nextTick, type VNode } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Sheet from './Sheet.vue'

const panelBase = 'absolute flex flex-col bg-white shadow-2xl dark:bg-slate-900'
const rightBase = 'inset-y-0 right-0 w-full'
const bottomClass = 'inset-x-0 bottom-0 max-h-[85dvh] rounded-t-2xl'
const headerClass =
  'flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-700'
const closeClass =
  'grid min-h-11 min-w-11 place-items-center rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800'

const mounted = new Set<{ unmount(): void }>()

function mountSheet(
  props: {
    open: boolean
    title: string
    side?: 'right' | 'bottom'
    wide?: boolean
  },
  slot?: () => VNode,
) {
  const wrapper = mount(Sheet, {
    props,
    ...(slot ? { slots: { default: slot } } : {}),
  })
  mounted.add(wrapper)
  return wrapper
}

function appRoot(): HTMLElement {
  const app = document.getElementById('app')
  if (!app) throw new Error('テスト用 #app がありません')
  return app
}

function layer(): HTMLElement {
  const element = document.querySelector<HTMLElement>('[data-sheet-layer]')
  if (!element) throw new Error('Sheet の外枠がありません')
  return element
}

function panel(): HTMLElement {
  const element = document.querySelector<HTMLElement>('[role="dialog"]')
  if (!element) throw new Error('Sheet のパネルがありません')
  return element
}

function closeButton(): HTMLButtonElement {
  const button = panel().querySelector<HTMLButtonElement>(
    'button[aria-label="閉じる"]',
  )
  if (!button) throw new Error('閉じるボタンがありません')
  return button
}

function focusOrigin(): HTMLButtonElement {
  const origin = document.createElement('button')
  appRoot().appendChild(origin)
  origin.focus()
  return origin
}

function pressKey(key: string, shiftKey = false): KeyboardEvent {
  const event = new KeyboardEvent('keydown', {
    key,
    shiftKey,
    bubbles: true,
    cancelable: true,
  })
  window.dispatchEvent(event)
  return event
}

describe('Sheet', () => {
  beforeEach(() => {
    document.body.replaceChildren()
    document.body.removeAttribute('style')
    const app = document.createElement('div')
    app.id = 'app'
    document.body.appendChild(app)
  })

  afterEach(() => {
    for (const wrapper of mounted) wrapper.unmount()
    mounted.clear()
    document.body.replaceChildren()
    document.body.removeAttribute('style')
    vi.restoreAllMocks()
  })

  it('閉じているときは body に何も描かない', () => {
    mountSheet({ open: false, title: '記録' })

    expect(document.querySelector('[data-sheet-layer]')).toBeNull()
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })

  it('body 直下に旧と同じ構造・属性・クラスで描く', async () => {
    mountSheet({ open: true, title: '記録' }, () => h('p', '本文'))
    await nextTick()

    const outer = layer()
    const dialog = panel()
    const background = outer.firstElementChild as HTMLElement
    const header = dialog.firstElementChild as HTMLElement
    const heading = header.querySelector('h2')
    const body = dialog.lastElementChild as HTMLElement

    expect(outer.parentElement).toBe(document.body)
    expect(outer.getAttribute('data-sheet-layer')).toBe('')
    expect(outer.className).toBe('fixed inset-0 z-50')
    expect(background.className).toBe('absolute inset-0 bg-black/40')
    expect(dialog.className).toBe(`${panelBase} ${rightBase} max-w-md`)
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(dialog.getAttribute('aria-label')).toBe('記録')
    expect(header.className).toBe(headerClass)
    expect(heading?.className).toBe('text-lg font-bold')
    expect(heading?.textContent).toBe('記録')
    expect(closeButton().className).toBe(closeClass)
    expect(closeButton().getAttribute('type')).toBe('button')
    expect(body.className).toBe('min-h-0 flex-1 overflow-y-auto p-4')
    expect(body.textContent).toBe('本文')
  })

  it.each([
    [
      { side: 'right' as const, wide: false },
      `${panelBase} ${rightBase} max-w-md`,
    ],
    [
      { side: 'right' as const, wide: true },
      `${panelBase} ${rightBase} max-w-3xl`,
    ],
    [{ side: 'bottom' as const, wide: true }, `${panelBase} ${bottomClass}`],
  ])('side と wide に応じたパネルクラスを使う', async (options, expected) => {
    mountSheet({ open: true, title: '記録', ...options })
    await nextTick()

    expect(panel().className).toBe(expected)
  })

  it('初期 open=true でもフォーカス・背景ロック・Escape・Tab が働く', async () => {
    focusOrigin()
    const wrapper = mountSheet({ open: true, title: '記録' }, () =>
      h('button', { id: 'last' }, '末尾'),
    )
    await nextTick()

    expect(document.activeElement).toBe(closeButton())
    expect(appRoot().hasAttribute('inert')).toBe(true)
    expect(appRoot().getAttribute('aria-hidden')).toBe('true')
    expect(document.body.style.getPropertyValue('overflow')).toBe('hidden')

    const tab = pressKey('Tab', true)
    expect(tab.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(document.getElementById('last'))

    pressKey('Escape')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('Tab と Shift+Tab で先頭と末尾のフォーカスを循環する', async () => {
    mountSheet({ open: true, title: '記録' }, () =>
      h('button', { id: 'last' }, '末尾'),
    )
    await nextTick()

    const first = closeButton()
    const last = document.getElementById('last') as HTMLButtonElement
    expect(document.activeElement).toBe(first)
    expect(pressKey('Tab', true).defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)

    expect(pressKey('Tab').defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)
  })

  it('開閉の変化で背景とフォーカスを元の属性・優先度へ戻す', async () => {
    const app = appRoot()
    app.setAttribute('inert', 'before')
    app.setAttribute('aria-hidden', 'false')
    document.body.style.setProperty('overflow', 'scroll', 'important')
    const origin = focusOrigin()
    const wrapper = mountSheet({ open: false, title: '記録' })

    await wrapper.setProps({ open: true })
    expect(document.activeElement).toBe(closeButton())
    expect(app.getAttribute('inert')).toBe('')
    expect(app.getAttribute('aria-hidden')).toBe('true')
    expect(document.body.style.getPropertyValue('overflow')).toBe('hidden')

    await wrapper.setProps({ open: false })
    expect(document.querySelector('[data-sheet-layer]')).toBeNull()
    expect(document.activeElement).toBe(origin)
    expect(app.getAttribute('inert')).toBe('before')
    expect(app.getAttribute('aria-hidden')).toBe('false')
    expect(document.body.style.getPropertyValue('overflow')).toBe('scroll')
    expect(document.body.style.getPropertyPriority('overflow')).toBe(
      'important',
    )
  })

  it('2 枚のうち 1 枚を閉じても背景ロックを維持する', async () => {
    const first = mountSheet({ open: true, title: '1 枚目' })
    const second = mountSheet({ open: true, title: '2 枚目' })
    await nextTick()

    await first.setProps({ open: false })
    expect(appRoot().hasAttribute('inert')).toBe(true)
    expect(appRoot().getAttribute('aria-hidden')).toBe('true')
    expect(document.body.style.getPropertyValue('overflow')).toBe('hidden')

    await second.setProps({ open: false })
    expect(appRoot().hasAttribute('inert')).toBe(false)
    expect(appRoot().hasAttribute('aria-hidden')).toBe(false)
    expect(document.body.style.getPropertyValue('overflow')).toBe('')
  })

  it('重ねた Sheet では最前面だけが Escape を処理する', async () => {
    const lower = mountSheet({ open: true, title: '下' })
    const upper = mountSheet({ open: true, title: '上' })
    await nextTick()

    pressKey('Escape')
    expect(upper.emitted('close')).toHaveLength(1)
    expect(lower.emitted('close')).toBeUndefined()

    await upper.setProps({ open: false })
    expect(appRoot().hasAttribute('inert')).toBe(true)
    expect(document.body.style.getPropertyValue('overflow')).toBe('hidden')

    pressKey('Escape')
    expect(lower.emitted('close')).toHaveLength(1)
    expect(upper.emitted('close')).toHaveLength(1)
  })

  it('重ねた Sheet の Tab は上のパネル内だけで循環する', async () => {
    mountSheet({ open: true, title: '下' }, () =>
      h('button', { id: 'lower-last' }, '下の末尾'),
    )
    mountSheet({ open: true, title: '上' }, () =>
      h('button', { id: 'upper-last' }, '上の末尾'),
    )
    await nextTick()

    const upperPanel =
      document.querySelectorAll<HTMLElement>('[role="dialog"]')[1]
    const upperFirst = upperPanel?.querySelector<HTMLButtonElement>(
      'button[aria-label="閉じる"]',
    )
    const upperLast = document.getElementById('upper-last')
    expect(document.activeElement).toBe(upperFirst)

    expect(pressKey('Tab', true).defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(upperLast)
    expect(document.activeElement).not.toBe(
      document.getElementById('lower-last'),
    )

    expect(pressKey('Tab').defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(upperFirst)
  })

  it('下のパネルにフォーカスがあっても最前面だけが Tab を処理する', async () => {
    mountSheet({ open: true, title: '下' }, () =>
      h('button', { id: 'lower-last' }, '下の末尾'),
    )
    mountSheet({ open: true, title: '上' }, () =>
      h('button', { id: 'upper-last' }, '上の末尾'),
    )
    await nextTick()

    const dialogs = document.querySelectorAll<HTMLElement>('[role="dialog"]')
    const lowerFirst = dialogs[0]?.querySelector<HTMLButtonElement>(
      'button[aria-label="閉じる"]',
    )
    const upperFirst = dialogs[1]?.querySelector<HTMLButtonElement>(
      'button[aria-label="閉じる"]',
    )
    const lowerLast = document.getElementById('lower-last') as HTMLButtonElement
    const upperLast = document.getElementById('upper-last')
    if (!lowerFirst || !upperFirst)
      throw new Error('テスト用ボタンがありません')

    lowerLast.focus()
    const lowerFirstFocus = vi.spyOn(lowerFirst, 'focus')
    expect(pressKey('Tab').defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(upperFirst)
    expect(lowerFirstFocus).not.toHaveBeenCalled()

    lowerFirstFocus.mockRestore()
    lowerFirst.focus()
    const lowerLastFocus = vi.spyOn(lowerLast, 'focus')
    expect(pressKey('Tab', true).defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(upperLast)
    expect(lowerLastFocus).not.toHaveBeenCalled()
  })

  it('3 枚の真ん中を閉じても最前面に残り、戻り先を引き継ぐ', async () => {
    mountSheet({ open: true, title: 'A' }, () =>
      h('button', { id: 'a-origin' }, 'A 内の戻り先'),
    )
    await nextTick()
    const aOrigin = document.getElementById('a-origin') as HTMLButtonElement
    aOrigin.focus()

    const middle = mountSheet({ open: true, title: 'B' })
    const upper = mountSheet({ open: true, title: 'C' })
    await nextTick()
    const upperPanel =
      document.querySelectorAll<HTMLElement>('[role="dialog"]')[2]
    const upperClose = upperPanel?.querySelector<HTMLButtonElement>(
      'button[aria-label="閉じる"]',
    )
    expect(document.activeElement).toBe(upperClose)

    await middle.setProps({ open: false })
    expect(document.activeElement).toBe(upperClose)
    expect(document.activeElement).not.toBe(aOrigin)
    expect(appRoot().hasAttribute('inert')).toBe(true)

    await upper.setProps({ open: false })
    expect(document.activeElement).toBe(aOrigin)
  })

  it('下の Sheet を先に閉じても上の Escape が効く', async () => {
    const lower = mountSheet({ open: true, title: '下' })
    const upper = mountSheet({ open: true, title: '上' })
    await nextTick()

    await lower.setProps({ open: false })
    expect(appRoot().hasAttribute('inert')).toBe(true)
    pressKey('Escape')
    expect(upper.emitted('close')).toHaveLength(1)
    expect(lower.emitted('close')).toBeUndefined()
  })

  it('背景と閉じるボタンのクリックで close を通知する', async () => {
    const wrapper = mountSheet({ open: true, title: '記録' })
    await nextTick()

    ;(layer().firstElementChild as HTMLElement).click()
    closeButton().click()
    expect(wrapper.emitted('close')).toHaveLength(2)
  })

  it('開いたままアンマウントすると背景とリスナーを戻す', async () => {
    const origin = focusOrigin()
    const wrapper = mountSheet({ open: true, title: '記録' })
    await nextTick()
    const removeListener = vi.spyOn(window, 'removeEventListener')

    wrapper.unmount()
    mounted.delete(wrapper)
    expect(removeListener).toHaveBeenCalledWith(
      'keydown',
      expect.any(Function),
      true,
    )
    expect(document.activeElement).toBe(origin)
    expect(appRoot().hasAttribute('inert')).toBe(false)
    expect(document.body.style.getPropertyValue('overflow')).toBe('')

    pressKey('Escape')
    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('#app がないときは Sheet 以外の body 直下要素をロックする', async () => {
    appRoot().remove()
    const first = document.createElement('div')
    const second = document.createElement('div')
    second.setAttribute('aria-hidden', 'false')
    document.body.append(first, second)
    const wrapper = mountSheet({ open: true, title: '記録' })
    await nextTick()

    expect(first.hasAttribute('inert')).toBe(true)
    expect(second.hasAttribute('inert')).toBe(true)
    expect(first.getAttribute('aria-hidden')).toBe('true')
    expect(layer().hasAttribute('inert')).toBe(false)

    await wrapper.setProps({ open: false })
    expect(first.hasAttribute('inert')).toBe(false)
    expect(second.hasAttribute('inert')).toBe(false)
    expect(second.getAttribute('aria-hidden')).toBe('false')
  })

  it('閉じるアイコンの SVG 属性と 2 本のパスが決定 D と一致する', async () => {
    mountSheet({ open: true, title: '記録' })
    await nextTick()
    const svg = closeButton().querySelector('svg')

    expect(svg?.getAttribute('class')).toBe('lucide lucide-x-icon lucide-x')
    expect(svg?.getAttribute('width')).toBe('22')
    expect(svg?.getAttribute('height')).toBe('22')
    expect(svg?.getAttribute('stroke-width')).toBe('2')
    expect(svg?.getAttribute('viewBox')).toBe('0 0 24 24')
    expect(svg?.getAttribute('aria-hidden')).toBe('true')
    expect(svg?.getAttribute('xmlns')).toBe('http://www.w3.org/2000/svg')
    expect(svg?.getAttribute('fill')).toBe('none')
    expect(svg?.getAttribute('stroke')).toBe('currentColor')
    expect(svg?.getAttribute('stroke-linecap')).toBe('round')
    expect(svg?.getAttribute('stroke-linejoin')).toBe('round')
    expect(
      Array.from(svg?.querySelectorAll('path') ?? []).map((path) =>
        path.getAttribute('d'),
      ),
    ).toStrictEqual(['M18 6 6 18', 'm6 6 12 12'])
  })

  it('HTML を含む title をテキストとして表示する', async () => {
    const title = '<img src=x onerror=alert(1)>'
    mountSheet({ open: true, title })
    await nextTick()

    expect(panel().getAttribute('aria-label')).toBe(title)
    expect(panel().querySelector('h2')?.textContent).toBe(title)
    expect(document.querySelectorAll('img')).toHaveLength(0)
  })
})
