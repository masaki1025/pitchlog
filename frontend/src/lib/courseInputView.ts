export type CourseInputView = 'catcher' | 'pitcher'

export const DEFAULT_COURSE_INPUT_VIEW: CourseInputView = 'catcher'
export const COURSE_COORDINATE_SIZE = 263
const STANCE_GRID_SIZE = 5

export function sanitizeCourseInputView(value: unknown): CourseInputView {
  return value === 'pitcher' ? 'pitcher' : DEFAULT_COURSE_INPUT_VIEW
}

/**
 * 保存座標は従来どおり捕手側視点の 0〜263 を正本とする。
 * 投手後方視点は画面上のX座標だけを反転し、既存データを書き換えない。
 */
export function courseScreenXToStoredX(
  screenX: number,
  view: CourseInputView,
): number {
  return view === 'pitcher' ? COURSE_COORDINATE_SIZE - screenX : screenX
}

export function courseStoredXToScreenX(
  storedX: number,
  view: CourseInputView,
): number {
  return view === 'pitcher' ? COURSE_COORDINATE_SIZE - storedX : storedX
}

function mirrorStanceZoneWithinRow(zone: number): number {
  if (!Number.isInteger(zone) || zone < 1 || zone > STANCE_GRID_SIZE ** 2) return zone
  const zeroBased = zone - 1
  const rowStart = Math.floor(zeroBased / STANCE_GRID_SIZE) * STANCE_GRID_SIZE
  const column = zeroBased % STANCE_GRID_SIZE
  return rowStart + (STANCE_GRID_SIZE - column)
}

/**
 * 構え番号は従来の捕手側 1〜25 を正本とする。
 * 投手後方視点では同じ高さのまま左右だけ反転して保存番号へ戻す。
 */
export function stanceScreenZoneToStoredZone(
  screenZone: number,
  view: CourseInputView,
): number {
  return view === 'pitcher' ? mirrorStanceZoneWithinRow(screenZone) : screenZone
}

/** 保存済みの構え番号を現在の画面位置へ変換する。上記変換の逆（同じ写像）。 */
export function stanceStoredZoneToScreenZone(
  storedZone: number,
  view: CourseInputView,
): number {
  return view === 'pitcher' ? mirrorStanceZoneWithinRow(storedZone) : storedZone
}

export function courseInputViewLabel(view: CourseInputView): string {
  return view === 'pitcher' ? '投手後方' : '捕手側'
}
