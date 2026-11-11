/** 守備位置の表示アンカー（旧画面の配置を表示専用に固定したもの）。 */
export const FIELDER_ANCHORS: readonly [number, number, number][] = [
  [8, 116.0, 66.0],
  [7, 56.0, 101.0],
  [9, 174.0, 101.0],
  [6, 88.0, 144.0],
  [4, 152.0, 144.0],
  [5, 66.0, 174.0],
  [3, 166.0, 174.0],
  [1, 123.0, 164.0],
  [2, 123.0, 232.0],
]

export const POSITION_SHORT: Readonly<Record<number, string>> = {
  1: '投',
  2: '捕',
  3: '一',
  4: '二',
  5: '三',
  6: '遊',
  7: '左',
  8: '中',
  9: '右',
}

export const POSITION_LONG: Readonly<Record<number, string>> = {
  1: '投手',
  2: '捕手',
  3: '一塁手',
  4: '二塁手',
  5: '三塁手',
  6: '遊撃手',
  7: '左翼手',
  8: '中堅手',
  9: '右翼手',
}
