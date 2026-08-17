export interface SpatialPoint {
  x: number
  y: number
}

interface MoveSpatialPointOptions {
  defaultPoint: SpatialPoint
  fine?: boolean
  coarseStep?: number
  fineStep?: number
}

const COORDINATE_MIN = 0.1
const COORDINATE_MAX = 262.9

const ARROW_DELTAS: Record<string, SpatialPoint> = {
  ArrowLeft: { x: -1, y: 0 },
  ArrowRight: { x: 1, y: 0 },
  ArrowUp: { x: 0, y: -1 },
  ArrowDown: { x: 0, y: 1 },
}

const clampCoordinate = (value: number) =>
  Math.max(COORDINATE_MIN, Math.min(COORDINATE_MAX, value))

/**
 * SVG上の連続座標を矢印キーで移動する。
 * 未入力時は各図が指定する基準点から開始し、Shift併用時は微調整する。
 */
export function moveSpatialPoint(
  point: SpatialPoint | null,
  key: string,
  options: MoveSpatialPointOptions,
): SpatialPoint | null {
  const delta = ARROW_DELTAS[key]
  if (!delta) return null

  const origin = point ?? options.defaultPoint
  const step = options.fine
    ? (options.fineStep ?? 1)
    : (options.coarseStep ?? 8)
  return {
    x: clampCoordinate(origin.x + delta.x * step),
    y: clampCoordinate(origin.y + delta.y * step),
  }
}
