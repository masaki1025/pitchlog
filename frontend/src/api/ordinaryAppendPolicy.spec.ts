import { expect, it } from 'vitest'
import {
  ORDINARY_APPEND_POLICY,
  isOrdinaryAppendPolicy,
  nextOrdinaryD2,
} from './ordinaryAppendPolicy'
it('初期1/普通末尾gap1000を別軸で採番し、過去ラベルは変更しない', () => {
  expect(nextOrdinaryD2(null, ORDINARY_APPEND_POLICY)).toBe('1')
  expect(nextOrdinaryD2('1', ORDINARY_APPEND_POLICY)).toBe('1001')
  expect(nextOrdinaryD2('21', ORDINARY_APPEND_POLICY)).toBe('1021')
  expect(nextOrdinaryD2('9007199254740991', ORDINARY_APPEND_POLICY)).toBeNull()
})
it('版/値/余剰と非正準/overflowを補修せず閉じる', () => {
  for (const bad of [
    { ...ORDINARY_APPEND_POLICY, version: 'other' },
    { ...ORDINARY_APPEND_POLICY, d2_gap: '1' },
    { ...ORDINARY_APPEND_POLICY, extra: true },
  ])
    expect(isOrdinaryAppendPolicy(bad)).toBe(false)
  for (const last of ['01', '1\n', '-1', '1.5'])
    expect(nextOrdinaryD2(last, ORDINARY_APPEND_POLICY)).toBeNull()
})
