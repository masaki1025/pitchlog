/** 走者別の物理状況を既語彙seedの起点塁ごとに閉検査する。 */
export function isPlayRunnerStatus(
  base: number,
  status: unknown,
  source: unknown,
): boolean {
  const outcomes = [
    '継続',
    '封殺',
    '投手牽制死',
    '捕手牽制死',
    '盗塁死',
    '走塁死',
  ]
  const advances: Record<number, Array<string>> = {
    1: ['二進', '三進', '本進'],
    2: ['三進', '本進'],
    3: ['本進'],
  }
  return (
    Object.hasOwn(advances, base) &&
    typeof status === 'string' &&
    (outcomes.includes(status) ||
      advances[base]!.includes(status) ||
      (status === '妨害裁定アウト' && source === 'manual')) &&
    (source === 'auto' || source === 'manual')
  )
}
