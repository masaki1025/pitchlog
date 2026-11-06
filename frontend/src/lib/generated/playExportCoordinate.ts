/** 自動生成。B-7の正準座標から画面整数への一方向写像。 */
export const SOURCE_MODEL_HASH =
  'sha256:0054a1bc629d86a638363589d1166acdbc78d6300411a097883ed5c80e50fc8c'
const SIZE = 263
const UNIT = '1/263'
const PATTERN = /^(?:0|[1-9][0-9]{0,3})$/

function number(value: string): number {
  if (typeof value !== 'string' || !PATTERN.test(value))
    throw new Error('正準整数座標が必要です')
  const parsed = Number(value)
  if (!Number.isSafeInteger(parsed) || parsed > SIZE)
    throw new Error('画面座標の範囲外です')
  return parsed
}

/** 保存k/263を画面整数へ写し、欠測は両軸同時だけ保持する。 */
export function courseScreen(
  x: string | null,
  y: string | null,
  unit: string | null,
): readonly [string | null, string | null] {
  if (x === null && y === null && unit === null) return [null, null]
  if (unit !== UNIT || x === null || y === null)
    throw new Error('正準座標単位が不一致です')
  const xValue = number(x)
  const yValue = number(y)
  return [String(xValue), String(SIZE - yValue)]
}
