import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ToastProvider, {
  useToast,
  type ToastApi,
  type ToastTone,
} from './Toast.vue'

const expectedContainer =
  'pointer-events-none fixed bottom-20 right-4 z-[60] flex w-80 flex-col gap-2'
const expectedBase = 'rounded-xl px-4 py-3 text-sm font-semibold shadow-lg'
const expectedTones: Record<ToastTone, string> = {
  info: 'bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900',
  success: 'bg-emerald-600 text-white',
  error: 'bg-red-600 text-white',
  warning: 'bg-amber-500 text-slate-900',
}

function createConsumer(onReady: (api: ToastApi) => void) {
  return defineComponent({
    setup() {
      onReady(useToast())
      return () => h('span', '子コンポーネント')
    },
  })
}

function mountWithConsumer() {
  let api: ToastApi | undefined
  const Consumer = createConsumer((value) => {
    api = value
  })
  const wrapper = mount(ToastProvider, {
    slots: { default: () => h(Consumer) },
  })

  async function show(...args: Parameters<ToastApi['push']>): Promise<void> {
    if (!api) throw new Error('テスト用コンシューマーを取得できません')
    api.push(...args)
    await nextTick()
  }

  return { wrapper, show }
}

describe('Toast', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('子から通知を追加し、slot の後ろに status として表示する', async () => {
    const { wrapper, show } = mountWithConsumer()
    await show('通知')

    const status = wrapper.find('[role="status"]')
    expect(status.text()).toBe('通知')
    expect(wrapper.html().indexOf('子コンポーネント')).toBeLessThan(
      wrapper.html().indexOf(expectedContainer),
    )
  })

  it('6 件目を追加すると最古を除いた 5 件を残す', async () => {
    const { wrapper, show } = mountWithConsumer()
    for (let id = 1; id <= 6; id += 1) {
      await show(`通知${id}`)
    }

    expect(
      wrapper.findAll('[role="status"]').map((item) => item.text()),
    ).toStrictEqual(['通知2', '通知3', '通知4', '通知5', '通知6'])
  })

  it.each([
    ['info', 4000],
    ['success', 4000],
    ['warning', 4000],
    ['error', 6000],
  ] as const)('%s は %i ms 後に消える', async (tone, duration) => {
    const { wrapper, show } = mountWithConsumer()
    await show('通知', tone)

    await vi.advanceTimersByTimeAsync(duration - 1)
    await nextTick()
    expect(wrapper.findAll('[role="status"]')).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(1)
    await nextTick()
    expect(wrapper.findAll('[role="status"]')).toHaveLength(0)
  })

  it('durationMs を指定すると tone の既定時間より優先する', async () => {
    const { wrapper, show } = mountWithConsumer()
    await show('通知', 'error', 125)

    await vi.advanceTimersByTimeAsync(124)
    await nextTick()
    expect(wrapper.findAll('[role="status"]')).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(1)
    await nextTick()
    expect(wrapper.findAll('[role="status"]')).toHaveLength(0)
  })

  it.each(['info', 'success', 'error', 'warning'] as const)(
    '%s のクラスを旧 Toast と一致させる',
    async (tone) => {
      const { wrapper, show } = mountWithConsumer()
      await show('通知', tone)

      expect(wrapper.find('div').attributes('class')).toBe(expectedContainer)
      expect(wrapper.find('[role="status"]').attributes('class')).toBe(
        `${expectedBase} ${expectedTones[tone]}`,
      )
    },
  )

  it('Provider の外で useToast を呼ぶと例外を投げる', () => {
    const Consumer = createConsumer(() => {})

    expect(() => mount(Consumer)).toThrowError(
      'ToastProvider の外では useToast() を使用できません',
    )
  })

  it('HTML を含む文言を要素に変えずテキストで表示する', async () => {
    const { wrapper, show } = mountWithConsumer()
    const message = '<img src=x onerror=alert(1)>'
    await show(message)

    expect(wrapper.find('[role="status"]').text()).toBe(message)
    expect(wrapper.findAll('img')).toHaveLength(0)
  })
})
