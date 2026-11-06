import { describe, expect, it } from 'vitest'
import { courseScreen } from './playExportCoordinate'

describe('B-7 毎球CSV表示座標', () => {
  it.each([
    [['0', '0', '1/263'], ['0', '263']],
    [['132', '66', '1/263'], ['132', '197']],
    [['263', '263', '1/263'], ['263', '0']],
    [[null, null, null], [null, null]],
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
