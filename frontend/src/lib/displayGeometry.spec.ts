import { describe, expect, it } from 'vitest'
import {
  COURSE_STRIKE_ZONE,
  DISPLAY_COORDINATE_SYSTEM,
  DISPLAY_COORD_SIZE,
} from './displayGeometry'

describe('displayGeometry', () => {
  // 契約ファイルの差し替えによる座標定義の不一致を検出する。
  it('座標定義の契約を固定する', () => {
    expect(DISPLAY_COORDINATE_SYSTEM).toBe('display_263_top_left_v1')
    expect(DISPLAY_COORD_SIZE).toBe(263)
    expect(COURSE_STRIKE_ZONE).toEqual({
      left: 80,
      right: 183,
      top: 68,
      bottom: 180,
    })
  })
})
