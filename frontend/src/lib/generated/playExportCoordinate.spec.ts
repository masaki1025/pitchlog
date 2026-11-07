import { describe, expect, it } from 'vitest'
import {
  courseScreen,
  fieldingPositionLabel,
  plateResultDisplay,
} from './playExportCoordinate'

describe('B-7 毎球CSV表示座標', () => {
  it.each([
    [
      ['0', '0', '1/263'],
      ['0', '263'],
    ],
    [
      ['132', '66', '1/263'],
      ['132', '197'],
    ],
    [
      ['263', '263', '1/263'],
      ['263', '0'],
    ],
    [
      [null, null, null],
      [null, null],
    ],
  ] as const)('独立規範の端点・本文例を保つ', (source, expected) => {
    expect(courseScreen(source[0], source[1], source[2])).toEqual(expected)
  })

  it.each([
    ['00', '0', '1/263'],
    ['264', '0', '1/263'],
    ['0', null, '1/263'],
    ['0', '0', '1/262'],
  ] as const)('非正準値を補完しない', (x, y, unit) => {
    expect(() => courseScreen(x, y, unit)).toThrow()
  })
})

describe('旧守備位置表示の有限写像', () => {
  it('P/C/一二三遊外野とDHを表示する', () => {
    expect(
      Array.from({ length: 9 }, (_, index) =>
        fieldingPositionLabel({
          kind: 'fielding',
          position: String(index + 1),
        }),
      ),
    ).toEqual(['P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF'])
    expect(fieldingPositionLabel({ kind: 'designated-hitter' })).toBe('DH')
  })
  it('未知守備位置を拒否する', () => {
    expect(() =>
      fieldingPositionLabel({ kind: 'fielding', position: '10' }),
    ).toThrow()
  })
})

describe('確定打席結果の有限表示', () => {
  it.each([
    ['見逃し三振', null, null, '見三振'],
    ['併殺打', '6', 'G', '6G併'],
    ['ライナー併殺', '4', null, '4ライナー併'],
    ['四球', null, null, '四球'],
  ] as const)(
    '旧独立表示例を維持する',
    (label, fielder, ballType, expected) => {
      expect(plateResultDisplay(label, true, fielder, ballType)).toBe(expected)
    },
  )
  it('継続と完了欠測を区別する', () => {
    expect(plateResultDisplay(null, false, null, null)).toBeNull()
    expect(() => plateResultDisplay(null, true, null, null)).toThrow()
    expect(() => plateResultDisplay('併殺打', true, null, 'G')).toThrow()
  })
})
