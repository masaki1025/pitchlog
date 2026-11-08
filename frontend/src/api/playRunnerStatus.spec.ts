import { describe, expect, it } from 'vitest'
import { isPlayRunnerStatus } from './playRunnerStatus'

describe('物理走者状況の公開境界', () => {
  it('起点別の進塁と手動由来を受理する', () => {
    expect(isPlayRunnerStatus(1, '三進', 'manual')).toBe(true)
    expect(isPlayRunnerStatus(1, '本進', 'manual')).toBe(true)
    expect(isPlayRunnerStatus(2, '三進', 'auto')).toBe(true)
    expect(isPlayRunnerStatus(3, '本進', 'auto')).toBe(true)
    expect(isPlayRunnerStatus(1, '継続', 'auto')).toBe(true)
  })

  it.each([1, 2, 3])('起点%sの保存済み手動妨害裁定だけを表示できる', (base) => {
    expect(isPlayRunnerStatus(base, '妨害裁定アウト', 'manual')).toBe(true)
    expect(isPlayRunnerStatus(base, '妨害裁定アウト', 'auto')).toBe(false)
    expect(isPlayRunnerStatus(base, '妨害裁定アウト', 'unknown')).toBe(false)
    expect(isPlayRunnerStatus(base, '妨害アウト', 'manual')).toBe(false)
  })

  it('逆行・未知状況・未知由来を拒否する', () => {
    expect(isPlayRunnerStatus(0, '妨害裁定アウト', 'manual')).toBe(false)
    expect(isPlayRunnerStatus(4, '妨害裁定アウト', 'manual')).toBe(false)
    expect(isPlayRunnerStatus(2, '二進', 'manual')).toBe(false)
    expect(isPlayRunnerStatus(3, '三進', 'manual')).toBe(false)
    expect(isPlayRunnerStatus(1, '四進', 'auto')).toBe(false)
    expect(isPlayRunnerStatus(1, '本進', 'unknown')).toBe(false)
    expect(isPlayRunnerStatus(4, '継続', 'auto')).toBe(false)
  })
})
