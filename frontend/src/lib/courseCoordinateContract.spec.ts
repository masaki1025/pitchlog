import { describe, expect, it } from 'vitest'
import geometry from '@contracts/display_geometry_263_v1.json'
import { COURSE_COORDINATE_SIZE } from './courseInputView'
import { DISPLAY_COORD_SIZE } from './displayGeometry'

describe('courseCoordinateContract', () => {
  it('COURSE_COORDINATE_SIZE が契約の size と一致する', () => {
    expect(COURSE_COORDINATE_SIZE).toBe(geometry.size)
  })

  it('DISPLAY_COORD_SIZE が契約の size と一致する', () => {
    expect(DISPLAY_COORD_SIZE).toBe(geometry.size)
  })
})
