import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import StrikeZone from './StrikeZone.vue'

// jsdom はレイアウトを計算しないため、座標変換の基準を left=10, top=20, width=263, height=263 に固定する。
const fixedBoundingClientRect = {
  bottom: 283,
  height: 263,
  left: 10,
  right: 273,
  toJSON: () => ({}),
  top: 20,
  width: 263,
  x: 10,
  y: 20,
} as DOMRect

beforeEach(() => {
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(
    fixedBoundingClientRect,
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

function dispatchPointerDown(svg: Element): void {
  svg.dispatchEvent(
    new MouseEvent('pointerdown', {
      bubbles: true,
      clientX: 90,
      clientY: 88,
    }),
  )
}

describe('StrikeZone', () => {
  it.each([
    ['右打者・捕手側', '右', 'catcher', 80],
    ['左打者・捕手側', '左', 'catcher', 80],
    ['右打者・投手後方', '右', 'pitcher', 183],
    ['左打者・投手後方', '左', 'pitcher', 183],
  ] as const)(
    '%s はタップ座標を捕手側保存座標へ変換する',
    (_label, plateSide, viewpoint, expectedStoredX) => {
      const wrapper = mount(StrikeZone, {
        props: {
          plateSide,
          point: null,
          viewpoint,
        },
      })

      dispatchPointerDown(wrapper.get('svg').element)

      expect(wrapper.emitted('tap')).toEqual([[expectedStoredX, 68]])
    },
  )

  it('disabled のときはタップを emit しない', () => {
    const wrapper = mount(StrikeZone, {
      props: {
        disabled: true,
        plateSide: '右',
        point: null,
        viewpoint: 'catcher',
      },
    })

    dispatchPointerDown(wrapper.get('svg').element)

    expect(wrapper.emitted('tap')).toBeUndefined()
  })

  it('class attrs を SVG root へ fallthrough する', () => {
    const wrapper = mount(StrikeZone, {
      attrs: {
        class: 'comparison-class',
      },
      props: {
        plateSide: '右',
        point: null,
        viewpoint: 'catcher',
      },
    })

    expect(wrapper.get('svg').classes()).toContain('comparison-class')
  })
})
