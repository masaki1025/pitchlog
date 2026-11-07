import { expect, it } from 'vitest'
import mapped from '../../../backend/tests/fixtures/runner_nonpitch_public_rows_v1.json'
import recorded from './fixtures/lineupPrefixGame.recorded.v3.json'
import { isLineupPrefixGame } from './lineupPrefixGame'
import {
  isLineupNonPitchPlayRow,
  isLineupRunnerNonPitchPlayRow,
  isRecordedPrefixPlayRow,
} from './startedGame'

function pageWith(row: Record<string, unknown>) {
  const game = structuredClone(recorded.value)
  // 表示殻の試合IDだけを既fixtureへ合わせ、mapper行の他34公開値を保持する。
  Object.assign(game.page.items[0]!.play_row, row, { game_id: game.id })
  return game
}

it.each(mapped.rows)(
  '実mapperの有限$event行だけをv3 pageに採る',
  ({ play_row }) => {
    expect(Object.keys(play_row)).toHaveLength(35)
    expect(isRecordedPrefixPlayRow(play_row)).toBe(false)
    expect(isLineupNonPitchPlayRow(play_row)).toBe(false)
    expect(isLineupRunnerNonPitchPlayRow(play_row)).toBe(true)
    expect(isLineupPrefixGame(pageWith(play_row))).toBe(true)
  },
)

it.each([
  ['batting_result_key', 'batting-result.ball'],
  ['course', { unit: '1/263', x: '1', y: '1' }],
  ['pitch_type_key', 'pitch-type.straight'],
  ['pitch_speed', 0],
  ['batted_ball_type', 'batted-ball.ground'],
  ['secondary_batting_result_key', 'secondary-result.unknown'],
  ['pickoff_type', 'unknown'],
  ['pickoff_detail', 'unknown'],
  ['unknown', true],
  ['version', true],
] as const)('Runner NPの%s差替えは閉拒否', (field, value) => {
  const row: Record<string, unknown> = structuredClone(mapped.rows[0]!.play_row)
  row[field] = value
  expect(isLineupRunnerNonPitchPlayRow(row)).toBe(false)
  expect(isLineupPrefixGame(pageWith(row))).toBe(false)
})

it.each([
  { pickoff_type: 'pitcher' },
  { pickoff_detail: 'first' },
  {
    pickoff_type: 'pitcher',
    secondary_batting_result_key: 'secondary-result.balk',
  },
  {
    pickoff_detail: 'first',
    secondary_batting_result_key: 'secondary-result.balk',
  },
])('片側牽制/ボーク混合を受けない', (changes) => {
  const row: Record<string, unknown> = structuredClone(mapped.rows[0]!.play_row)
  Object.assign(row, changes)
  expect(isLineupRunnerNonPitchPlayRow(row)).toBe(false)
  expect(isLineupPrefixGame(pageWith(row))).toBe(false)
})

it('通常投球の主結果必須と申告敬遠の別閉型を維持する', () => {
  const pitch: Record<string, unknown> = structuredClone(
    recorded.value.page.items[0]!.play_row,
  )
  pitch.batting_result_key = null
  expect(isRecordedPrefixPlayRow(pitch)).toBe(false)
  expect(isLineupPrefixGame(pageWith(pitch))).toBe(false)

  const walk: Record<string, unknown> = structuredClone(
    recorded.value.page.items[0]!.play_row,
  )
  Object.assign(walk, {
    event_kind: 'non_pitch',
    batting_result_key: 'batting-result.intentional-walk',
    course: null,
    pitch_type_key: null,
  })
  expect(isLineupNonPitchPlayRow(walk)).toBe(true)
  expect(isLineupRunnerNonPitchPlayRow(walk)).toBe(false)
  expect(isLineupPrefixGame(pageWith(walk))).toBe(true)
})
