/** 公式成績27項目と成績CSVを実画面から確認する。 */
import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import {
  apiPath,
  baseURL,
  createAndStartRealGame,
  recordRealPitch,
} from './RealGameRecording.e2e-support'

async function endGame(page: Page, gameId: string) {
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
}

test('実画面で公式成績27項目と成績CSVを確認する', async ({ page }) => {
  page.setDefaultTimeout(30_000)
  const { game, head: initial } = await createAndStartRealGame(
    page,
    '成績27項目画面試験',
  )
  let head = initial
  let count = 1
  head = (await recordRealPitch(page, head, 'batting-result.home-run', count))
    .head
  count += 1
  for (let out = 0; out < 3; out += 1) {
    head = (
      await recordRealPitch(page, head, 'batting-result.batted-out', count)
    ).head
    count += 1
  }
  for (let out = 0; out < 3; out += 1) {
    head = (
      await recordRealPitch(page, head, 'batting-result.batted-out', count)
    ).head
    count += 1
  }
  expect(head.after.stateFields['state.score']).toEqual({
    away: '1',
    home: '0',
  })
  await endGame(page, game.id)

  await page.goto(`${baseURL}/games/${game.id}/stats`)
  await expect(
    page.getByRole('heading', { name: '試合別基本成績' }),
  ).toBeVisible()
  await page.locator('select').selectOption('official')
  await expect(page.getByRole('heading', { name: '公式 打撃' })).toBeVisible()
  const battingHeaders = await page
    .locator('table')
    .nth(0)
    .locator('thead th')
    .count()
  const pitchingHeaders = await page
    .locator('table')
    .nth(1)
    .locator('thead th')
    .count()
  expect(battingHeaders + pitchingHeaders - 4).toBe(27)
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'CSVダウンロード' }).click()
  const download = await downloaded
  const path = await download.path()
  if (!path) throw new Error('成績CSVの保存先がない')
  const csv = readFileSync(path, 'utf8')
  expect(csv.length).toBeGreaterThan(0)
  expect(
    csv.split(/\r?\n/).filter((line) => line.length > 0).length,
  ).toBeGreaterThan(0)
  console.log(
    'PITCHLOG_STATS_SCREEN_FINAL=' +
      JSON.stringify({
        gameId: game.id,
        plays: count - 1,
        battingHeaders,
        pitchingHeaders,
        metrics: battingHeaders + pitchingHeaders - 4,
        csvBytes: csv.length,
      }),
  )
})
