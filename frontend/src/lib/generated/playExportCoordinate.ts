/** 自動生成。B-7の正準座標から画面整数への一方向写像。 */
export const SOURCE_MODEL_HASH =
  'sha256:6be2f315e519fa8054ae6980ce8b5e161dbf197793d1400bbbe1e56ac15d7e14'
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

const FIELDING_POSITION_LABELS: Readonly<Record<string, string>> = {
  '1': 'P',
  '2': 'C',
  '3': '1B',
  '4': '2B',
  '5': '3B',
  '6': 'SS',
  '7': 'LF',
  '8': 'CF',
  '9': 'RF',
}
const DH_LABEL = 'DH'

/** 保存された有限守備roleを旧表示欄へ写す。 */
export function fieldingPositionLabel(role: Record<string, unknown>): string {
  if (role === null || typeof role !== 'object' || Array.isArray(role))
    throw new Error('守備位置roleが不正です')
  if (Object.keys(role).length === 1 && role.kind === 'designated-hitter')
    return DH_LABEL
  if (
    Object.keys(role).length !== 2 ||
    role.kind !== 'fielding' ||
    typeof role.position !== 'string' ||
    !Object.prototype.hasOwnProperty.call(
      FIELDING_POSITION_LABELS,
      role.position,
    )
  )
    throw new Error('守備位置roleが不正です')
  return FIELDING_POSITION_LABELS[role.position]!
}

const PLATE_RESULT_ALIASES: Readonly<Record<string, string>> = {
  ファールフライ: '邪飛',
  三振ゲッツー: '三振併',
  振り逃げ: '振逃',
  空振り三振: '空三振',
  見逃し三振: '見三振',
}

/** 確定打席結果だけを旧有限表示へ写す。 */
export function plateResultDisplay(
  label: string | null,
  paEnded: boolean,
  fielder: string | null,
  ballType: string | null,
): string | null {
  if (
    typeof paEnded !== 'boolean' ||
    (label !== null && typeof label !== 'string')
  )
    throw new Error('打席結果原本が不正です')
  if (!paEnded) return null
  if (!label) throw new Error('完了打席の結果が欠測です')
  if (Object.prototype.hasOwnProperty.call(PLATE_RESULT_ALIASES, label))
    return PLATE_RESULT_ALIASES[label]!
  if (['併殺打', 'ライナー併殺', '凡打死', '凡打出塁'].includes(label)) {
    if (typeof fielder !== 'string' || !/^[1-9]$/.test(fielder))
      throw new Error('捕球選手が欠測です')
    if (label === 'ライナー併殺') return `${fielder}ライナー併`
    if (typeof ballType !== 'string' || !ballType)
      throw new Error('打球種類が欠測です')
    return `${fielder}${ballType}${label === '併殺打' ? '併' : ''}`
  }
  return label
}
