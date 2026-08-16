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

  it('旧実装どおりの 3x3 グリッド座標を描画する', () => {
    const wrapper = mount(StrikeZone, {
      props: {
        plateSide: '右',
        point: null,
        viewpoint: 'catcher',
      },
    })

    const zone = wrapper.get('rect.fill-sky-50')
    expect({
      height: Number(zone.attributes('height')),
      width: Number(zone.attributes('width')),
      x: Number(zone.attributes('x')),
      y: Number(zone.attributes('y')),
    }).toEqual({ height: 112, width: 103, x: 80, y: 68 })

    const lineElements = wrapper.findAll('line')
    expect(lineElements).toHaveLength(4)
    const lines = lineElements.map((line) => ({
      x1: Number(line.attributes('x1')),
      x2: Number(line.attributes('x2')),
      y1: Number(line.attributes('y1')),
      y2: Number(line.attributes('y2')),
    }))

    expect(lines).toEqual([
      { x1: 114.33333333333334, x2: 114.33333333333334, y1: 68, y2: 180 },
      { x1: 80, x2: 183, y1: 105.33333333333334, y2: 105.33333333333334 },
      { x1: 148.66666666666669, x2: 148.66666666666669, y1: 68, y2: 180 },
      { x1: 80, x2: 183, y1: 142.66666666666669, y2: 142.66666666666669 },
    ])

    expect(lines[0].x1).toBe(lines[0].x2)
    expect(lines[2].x1).toBe(lines[2].x2)
    expect(lines[1].y1).toBe(lines[1].y2)
    expect(lines[3].y1).toBe(lines[3].y2)
  })
})
