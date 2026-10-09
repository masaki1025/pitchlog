import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import Button from './Button.vue'

const variants = [
  'primary',
  'result',
  'secondary',
  'ghost',
  'danger',
  'chip',
] as const

// 旧 Button のクラス文字列を期待値として固定する。
const expectedBase =
  'relative select-none rounded-xl font-bold transition-colors disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500'

const expectedVariants = {
  primary:
    'min-h-[60px] px-4 text-lg bg-sky-600 text-white hover:bg-sky-700 active:bg-sky-800',
  result:
    'min-h-[60px] px-3 text-xl bg-white text-slate-900 border-2 border-slate-300 hover:bg-slate-50 active:bg-slate-200 dark:bg-slate-800 dark:text-slate-100 dark:border-slate-600 dark:hover:bg-slate-700',
  secondary:
    'min-h-12 px-3 text-base bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 active:bg-slate-200 dark:bg-slate-800 dark:text-slate-100 dark:border-slate-600 dark:hover:bg-slate-700',
  ghost:
    'min-h-12 px-3 text-base text-slate-700 hover:bg-slate-200 active:bg-slate-300 dark:text-slate-200 dark:hover:bg-slate-800',
  danger:
    'min-h-12 px-3 text-base bg-red-600 text-white hover:bg-red-700 active:bg-red-800',
  chip: 'min-h-11 px-3 text-sm bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 active:bg-slate-200 dark:bg-slate-800 dark:text-slate-100 dark:border-slate-600 dark:hover:bg-slate-700',
} as const

const expectedActive =
  'bg-sky-100 border-sky-500 text-sky-900 dark:bg-sky-900/60 dark:border-sky-400 dark:text-sky-100'

const expectedKeyHint =
  'pointer-events-none absolute right-1.5 top-1 hidden rounded border border-slate-300 bg-slate-100 px-1 text-[10px] font-mono font-normal leading-4 text-slate-500 lg:inline dark:border-slate-600 dark:bg-slate-900 dark:text-slate-400'

function classSet(classes: string): Set<string> {
  return new Set(classes.split(' '))
}

describe('Button', () => {
  it.each(variants)('%s のクラスを旧 Button と一致させる', (variant) => {
    const wrapper = mount(Button, { props: { variant } })
    const expected = `${expectedBase} ${expectedVariants[variant]}`

    expect(classSet(wrapper.attributes('class') ?? '')).toStrictEqual(
      classSet(expected),
    )
    expect(wrapper.attributes('class')).toBe(expected)
  })

  it.each(variants)('%s の active クラスを切り替える', async (variant) => {
    const wrapper = mount(Button, { props: { variant, active: true } })
    const activeClasses = `${expectedBase} ${expectedVariants[variant]} ${expectedActive}`

    expect(classSet(wrapper.attributes('class') ?? '')).toStrictEqual(
      classSet(activeClasses),
    )
    expect(wrapper.attributes('class')).toBe(activeClasses)

    await wrapper.setProps({ active: false })
    expect(wrapper.attributes('class')).toBe(
      `${expectedBase} ${expectedVariants[variant]}`,
    )
  })

  it('既定では secondary・非 active・button 型になる', () => {
    const wrapper = mount(Button)

    expect(wrapper.attributes('class')).toBe(
      `${expectedBase} ${expectedVariants.secondary}`,
    )
    expect(wrapper.attributes('type')).toBe('button')
    expect(wrapper.props()).not.toHaveProperty('className')
  })

  it('keyHint があるときだけ旧と同じクラスの span を表示する', async () => {
    const wrapper = mount(Button, { slots: { default: '本文' } })
    expect(wrapper.find('span').exists()).toBe(false)

    await wrapper.setProps({ keyHint: 'A' })
    const hint = wrapper.find('span')
    expect(hint.text()).toBe('A')
    expect(hint.attributes('class')).toBe(expectedKeyHint)
    expect(wrapper.text()).toContain('本文')

    await wrapper.setProps({ keyHint: '' })
    expect(wrapper.find('span').exists()).toBe(false)
  })

  it('class と任意の属性を root へ継承する', () => {
    const wrapper = mount(Button, {
      attrs: { class: 'custom-class', 'aria-label': '保存', disabled: true },
      slots: { default: '保存' },
    })

    expect(wrapper.classes()).toContain('custom-class')
    expect(wrapper.attributes('aria-label')).toBe('保存')
    expect(wrapper.attributes()).toHaveProperty('disabled')
    expect(wrapper.text()).toBe('保存')
  })

  it('呼び出し側の type で既定値を上書きする', () => {
    const wrapper = mount(Button, { attrs: { type: 'submit' } })

    expect(wrapper.attributes('type')).toBe('submit')
  })

  it('root のクリックイベントを呼び出し側へ届ける', async () => {
    const onClick = vi.fn()
    const wrapper = mount(Button, { attrs: { onClick } })

    await wrapper.trigger('click')
    expect(onClick).toHaveBeenCalledOnce()
  })
})
