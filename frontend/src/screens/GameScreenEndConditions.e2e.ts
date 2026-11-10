/** 9回コールド・延長・タイブレーク検知を実画面の保存列で確認する。 */
import { expect, test, type Page } from '@playwright/test'
import type { LineupPrefixGame } from '../api/lineupPrefixGame'
import {
  apiPath,
  createAndStartRealGame,
  recordRealPitch,
} from './RealGameRecording.e2e-support'

async function acceptEnd(page: Page, gameId: string) {
  const lifecycle = page.getByTestId('lifecycle-product')
  await lifecycle.getByTestId('lifecycle-refresh').click()
  for (const box of await lifecycle.locator('input[type=checkbox]').all())
    await box.check()
  await expect(lifecycle.getByTestId('lifecycle-confirmed-status')).toHaveText(
    '進行中',
  )
  const ended = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${gameId}/sync/events`,
  )
  await lifecycle.getByTestId('lifecycle-end').click()
  const response = await ended
  expect(response.status()).toBe(200)
  const ack = await response.json()
  expect(ack.eventResults?.[0]?.a5Result).toBe('受理')
  await expect(lifecycle.getByTestId('lifecycle-confirmed-status')).toHaveText(
    '終了',
  )
  await expect(lifecycle.getByTestId('lifecycle-last-version')).toHaveText('v1')
}

async function recordOuts(
  page: Page,
  head: LineupPrefixGame,
  count: number,
  outs: number,
) {
  let current = head
  let nextCount = count
  for (let out = 0; out < outs; out += 1) {
    const result = await recordRealPitch(
      page,
      current,
      'batting-result.batted-out',
      nextCount,
    )
    current = result.head
    nextCount += 1
  }
  return { head: current, count: nextCount }
}

async function scorelessInning(
  page: Page,
  head: LineupPrefixGame,
  count: number,
) {
  const top = await recordOuts(page, head, count, 3)
  const bottom = await recordOuts(page, top.head, top.count, 3)
  return { head: bottom.head, count: bottom.count }
}

test('9回・終盤7点差コールドを実画面から検知して終了する', async ({ page }) => {
  page.setDefaultTimeout(30_000)
  const { game, head: initial } = await createAndStartRealGame(
    page,
    '九回コールド画面試験',
    9,
    'game_semi_official',
  )
  let head = initial
  let count = 1
  for (let inning = 1; inning <= 7; inning += 1) {
    const opening = await recordRealPitch(
      page,
      head,
      'batting-result.home-run',
      count,
    )
    head = opening.head
    count += 1
    const top = await recordOuts(page, head, count, 3)
    const bottom = await recordOuts(page, top.head, top.count, 3)
    head = bottom.head
    count = bottom.count
  }
  expect(head.after.stateFields['state.score']).toEqual({
    away: '7',
    home: '0',
  })
  expect(head.after.stateFields['state.inning']).toBe('8')
  expect(head.t2?.decision.outcome).toBe('cold-end')
  await expect(page.getByTestId('ordinary-pitch-locked')).toContainText(
    '終了条件',
  )
  await expect(page.getByTestId('ordinary-pitch-result')).toHaveCount(0)
  await acceptEnd(page, game.id)
  console.log(
    'PITCHLOG_END_CONDITION_FINAL=' +
      JSON.stringify({
        scenario: 'cold-end',
        gameId: game.id,
        plays: count - 1,
        regulationInnings: 9,
        coldPointDifference: 7,
        coldStartInning: 7,
      }),
  )
})

test('9回同点は延長上限で引き分け終了する', async ({ page }) => {
  page.setDefaultTimeout(30_000)
  const { game, head: initial } = await createAndStartRealGame(
    page,
    '引き分け画面試験',
    9,
    'game_other',
  )
  let head = initial
  let count = 1
  for (let inning = 1; inning <= 9; inning += 1) {
    const result = await scorelessInning(page, head, count)
    head = result.head
    count = result.count
  }
  expect(head.after.stateFields['state.score']).toEqual({
    away: '0',
    home: '0',
  })
  expect(head.after.stateFields['state.inning']).toBe('10')
  expect(head.t2?.decision.outcome).toBe('limit-draw')
  await expect(page.getByTestId('ordinary-pitch-locked')).toContainText(
    '終了条件',
  )
  await expect(page.getByTestId('ordinary-pitch-result')).toHaveCount(0)
  await acceptEnd(page, game.id)
  console.log(
    'PITCHLOG_END_CONDITION_FINAL=' +
      JSON.stringify({
        scenario: 'limit-draw',
        gameId: game.id,
        plays: count - 1,
        regulationInnings: 9,
        extensionLimit: 9,
      }),
  )
})

test('タイブレーク発動回は開始操作まで通常球を閉じる', async ({ page }) => {
  page.setDefaultTimeout(30_000)
  const { game, head: initial } = await createAndStartRealGame(
    page,
    'タイブレーク境界画面試験',
    9,
    'game_official',
  )
  let head = initial
  let count = 1
  for (let inning = 1; inning <= 9; inning += 1) {
    const result = await scorelessInning(page, head, count)
    head = result.head
    count = result.count
  }
  expect(head.after.stateFields['state.inning']).toBe('10')
  expect(head.after.stateFields['state.half']).toBe('top')
  expect(head.after.stateFields['state.tiebreakActive']).toBe(false)
  expect(head.t2?.tiebreakStartRequired).toBe(true)
  await expect(page.getByTestId('ordinary-pitch-locked')).toContainText(
    'タイブレーク開始',
  )
  await expect(page.getByTestId('ordinary-pitch-result')).toHaveCount(0)
  console.log(
    'PITCHLOG_END_CONDITION_FINAL=' +
      JSON.stringify({
        scenario: 'tiebreak-required',
        gameId: game.id,
        plays: count - 1,
        regulationInnings: 9,
        tiebreakStartInning: 10,
      }),
  )
})
