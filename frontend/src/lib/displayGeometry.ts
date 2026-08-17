import geometry from '@contracts/display_geometry_263_v1.json'

export type DisplayPoint = { x: number; y: number }

export const DISPLAY_COORDINATE_SYSTEM = geometry.version
export const DISPLAY_COORD_SIZE = geometry.size

export const COURSE_STRIKE_ZONE = geometry.course.strike_zone
export const COURSE_HOME_PLATE_POINTS = geometry.course.home_plate.map(([x, y]) => ({ x, y }))

export const FIELD_HOME = { x: geometry.field.home[0], y: geometry.field.home[1] }
export const FIELD_FIRST = { x: geometry.field.first[0], y: geometry.field.first[1] }
export const FIELD_SECOND = { x: geometry.field.second[0], y: geometry.field.second[1] }
export const FIELD_THIRD = { x: geometry.field.third[0], y: geometry.field.third[1] }
export const FIELD_HOME_PLATE_POINTS = geometry.field.home_plate.map(([x, y]) => ({ x, y }))
export const FIELD_FENCE_RADIUS = geometry.field.fence_radius

export function foulLinePoint(corner: DisplayPoint, radius = FIELD_FENCE_RADIUS): DisplayPoint {
  const dx = corner.x - FIELD_HOME.x
  const dy = corner.y - FIELD_HOME.y
  const length = Math.hypot(dx, dy)
  return {
    x: FIELD_HOME.x + (dx / length) * radius,
    y: FIELD_HOME.y + (dy / length) * radius,
  }
}

export const FIELD_FENCE_RIGHT = foulLinePoint(FIELD_FIRST)
export const FIELD_FENCE_LEFT = foulLinePoint(FIELD_THIRD)

export function svgPoints(points: DisplayPoint[]) {
  return points.map((point) => `${point.x},${point.y}`).join(' ')
}
