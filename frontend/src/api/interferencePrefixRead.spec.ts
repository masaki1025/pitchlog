import { expect, it } from 'vitest'
import recordedFixture from './fixtures/lineupPrefixGame.recorded.v3.json'
import { isLineupPrefixGame } from './lineupPrefixGame'
import {
  isLineupInterferencePlayRow,
  isRecordedPrefixPlayRow,
} from './startedGame'

const nullFields = [
  'strategy_key',
  'strategy_detail_key',
  'strategy_result_key',
  'batter_status',
  'raw_fielder_position',
  'resolved_fielder_id',
  'batted_ball_type',
  'batted_ball_strength',
  'hit_x',
  'hit_y',
  'pickoff_type',
  'pickoff_detail',
  'error_type',
  'raw_error_position',
  'resolved_error_player_id',
  'press',
  'fake_run',
  'comment',
] as const
const keys = [
  'secondary-result.batting-interference',
  'secondary-result.obstruction',
  'secondary-result.offensive-interference',
] as const

function interferenceRow(key: (typeof keys)[number]): Record<string, unknown> {
  const row: Record<string, unknown> = structuredClone(
    recordedFixture.value.page.items[0]!.play_row,
  )
  row.batting_result_key = null
  row.secondary_batting_result_key = key
  for (const field of nullFields) row[field] = null
  return row
}

it.each(keys)('v3だけ副結果 %s の実投球を閉受理する', (key) => {
  const row = interferenceRow(key)
  expect(isLineupInterferencePlayRow(row)).toBe(true)
  expect(isRecordedPrefixPlayRow(row)).toBe(false)
  const head = structuredClone(recordedFixture.value) as Record<string, unknown>
  const page = head.page as { items: { play_row: unknown }[] }
  page.items[0]!.play_row = row
  expect(isLineupPrefixGame(head)).toBe(true)
})

it.each([
  ['batting_result_key', 'batting-result.ball'],
  ['secondary_batting_result_key', 'secondary-result.unknown'],
  ['course', null],
  ['pitch_type_key', null],
  ['batted_ball_type', 'line'],
  ['event_kind', 'non_pitch'],
] as const)('%s差替えを旧投球・非投球へ読み替えない', (field, value) => {
  const row = interferenceRow(keys[0])
  row[field] = value
  expect(isLineupInterferencePlayRow(row)).toBe(false)
  const head = structuredClone(recordedFixture.value) as Record<string, unknown>
  const page = head.page as { items: { play_row: unknown }[] }
  page.items[0]!.play_row = row
  expect(isLineupPrefixGame(head)).toBe(false)
})

it('旧ordinaryと打球の主結果行を変えない', () => {
  expect(
    isRecordedPrefixPlayRow(recordedFixture.value.page.items[0]!.play_row),
  ).toBe(true)
  expect(isLineupPrefixGame(recordedFixture.value)).toBe(true)
})

it('実プレイ採用は閉じた打球主結果と打撃妨害副結果だけ', () => {
  const row: Record<string, unknown> = structuredClone(
    recordedFixture.value.page.items[0]!.play_row,
  )
  row.batting_result_key = 'batting-result.single'
  row.secondary_batting_result_key = 'secondary-result.batting-interference'
  expect(isRecordedPrefixPlayRow(row)).toBe(true)
  row.batting_result_key = 'batting-result.ball'
  expect(isRecordedPrefixPlayRow(row)).toBe(false)
  row.batting_result_key = 'batting-result.single'
  row.secondary_batting_result_key = 'secondary-result.obstruction'
  expect(isRecordedPrefixPlayRow(row)).toBe(false)
})
