/** 現行v3実画面からCSV ZIPを保存し、実HTTPと完成bytesを突合する。 */
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { basename, dirname, isAbsolute } from 'node:path'
import { expect, test } from '@playwright/test'
import {
  apiPath,
  baseURL,
  createAndStartRealGame,
  recordRealPitch,
} from './RealGameRecording.e2e-support'

const savedPath = process.env.PITCHLOG_E2E_CSV_DOWNLOAD_PATH
if (
  !savedPath ||
  !isAbsolute(savedPath) ||
  basename(savedPath) !== 'play-csv-screen.zip' ||
  !existsSync(dirname(savedPath))
)
  throw new Error('所有画面試験のZIP保存先が不正')

test('実画面の新規作成・2球から完成CSV ZIPを保存する', async ({ page }) => {
  page.setDefaultTimeout(30_000)
  const { game, head: initial } = await createAndStartRealGame(
    page,
    '毎球CSV画面受入',
  )
  const first = await recordRealPitch(
    page,
    initial,
    'batting-result.called-pitch',
    1,
  )
  const second = await recordRealPitch(
    page,
    first.head,
    'batting-result.called-pitch',
    2,
  )
  expect(second.head.prefix_ref.length).toBe('2')
  await page.getByRole('link', { name: '毎球CSVへ' }).click()
  await expect(page).toHaveURL(`${baseURL}/games/${game.id}/export`)

  const received = page.waitForResponse(
    (response) =>
      response.request().method() === 'GET' &&
      apiPath(response.url()) === `/api/games/${game.id}/exports/plays.zip`,
  )
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: '毎球CSVをダウンロード' }).click()
  const [response, download] = await Promise.all([received, downloaded])
  expect(response.status()).toBe(200)
  const contentLength = Number(response.headers()['content-length'])
  const headerSha256 = response.headers()['x-pitchlog-archive-sha256']
  expect(Number.isSafeInteger(contentLength) && contentLength > 0).toBe(true)
  expect(headerSha256).toMatch(/^[a-f0-9]{64}$/)
  expect(download.suggestedFilename()).toBe(`pitchlog-plays-${game.id}.zip`)
  await download.saveAs(savedPath)
  const bytes = readFileSync(savedPath)
  const downloadSha256 = createHash('sha256').update(bytes).digest('hex')
  expect(bytes.length).toBe(contentLength)
  expect(downloadSha256).toBe(headerSha256)
  await expect(page.getByText('毎球CSVを保存しました')).toBeVisible()
  console.log(
    'PITCHLOG_CSV_SCREEN_FINAL=' +
      JSON.stringify({
        gameId: game.id,
        plays: 2,
        downloadBytes: bytes.length,
        downloadSha256,
        contentLength,
        headerSha256,
        downloadFilename: download.suggestedFilename(),
      }),
  )
})
