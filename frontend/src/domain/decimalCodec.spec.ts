import { describe, expect, it } from 'vitest'

import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'

describe('十進整数 codec', () => {
  it.each([
    '0',
    '-1',
    '2147483648',
    '9007199254740993',
    '18446744073709551621',
    '-18446744073709551621',
  ])('境界値 %s を数値型を経ずに往復する', (text) => {
    const parsed = parseDecimalInteger(text)
    expect(typeof parsed).toBe('bigint')
    expect(formatDecimalInteger(parsed as bigint)).toBe(text)
  })

  it.each([
    '-0',
    '00',
    '01',
    '-01',
    '',
    ' ',
    ' 1',
    '1 ',
    '1e3',
    '1.0',
    '+1',
    '0x10',
    1,
    null,
  ])('不正な境界値 %s を拒否する', (value) => {
    expect(parseDecimalInteger(value)).toBeNull()
  })
})
