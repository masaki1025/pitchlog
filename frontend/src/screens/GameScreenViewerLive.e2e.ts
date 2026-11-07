import { expect, test, type Page } from '@playwright/test'
import {
  createAndStartRealGame,
  recordRealPitch,
} from './RealGameRecording.e2e-support'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const away = process.env.PITCHLOG_E2E_AWAY_TEAM
const home = process.env.PITCHLOG_E2E_HOME_TEAM
if (!baseURL || !team || !password || !away || !home)
  throw new Error('E2Eの実app資格がenvにない')

function apiPath(url: string): string {
  return new URL(url).pathname
}
async function login(page: Page): Promise<string> {
  await page.goto(`${baseURL}/login?redirect=/games`)
  await expect(page.locator('form[aria-busy]')).toHaveAttribute(
    'aria-busy',
    'false',
  )
  await page.getByRole('textbox', { name: 'チーム名' }).fill(team!)
  await page.getByLabel('パスワード').fill(password!)
  const posted = page
    .waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === '/api/auth/login',
    )
    .catch(() => null)
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
  const response = await posted
  if (!response || response.status() !== 200)
    throw new Error('実login POSTが成功しない')
  const body = (await response.json()) as { tenant_id?: string }
  if (typeof body.tenant_id !== 'string')
    throw new Error('login応答のtenantがない')
  await expect(page).toHaveURL(`${baseURL}/games`)
  await expect(
    page.getByRole('button', { name: '新規作成', exact: true }),
  ).toBeVisible()
  return body.tenant_id
}

test('別contextの保存済み閲覧は10秒以内に1球へ更新し、断中は未更新', async ({
  page,
  browser,
}) => {
  page.setDefaultTimeout(30_000)
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('HTTPSが必要です')
  const { game: saved, head: initial } = await createAndStartRealGame(
    page,
    '画面作成大会',
  )
  let head = initial
  // 閲覧開始時点で26球を保存し、最新25球と旧pageの境界を作る。
  for (let index = 1; index <= 26; index += 1) {
    console.log(`PITCHLOG_VIEWER_RECORDING=${index}`)
    const recorded = await recordRealPitch(
      page,
      head,
      index % 3 === 0
        ? 'batting-result.called-strikeout'
        : 'batting-result.called-pitch',
      index,
    )
    head = recorded.head
  }
  expect(head.prefix_ref.length).toBe('26')
  const viewerContext = await browser.newContext({ ignoreHTTPSErrors: true })
  const viewer = await viewerContext.newPage()
  viewer.setDefaultTimeout(30_000)
  try {
    await login(viewer)
    console.log('PITCHLOG_VIEWER_STAGE=second-login')
    const observed: string[] = []
    const viewerApiRequests: string[] = []
    viewer.on('request', (request) => {
      const path = apiPath(request.url())
      if (path.startsWith('/api/'))
        viewerApiRequests.push(`${request.method()} ${path}`)
    })
    viewer.on('response', (res) => {
      const path = apiPath(res.url())
      if (
        (path.startsWith('/api/games/') && path.includes('/viewer')) ||
        path === '/api/auth/session'
      )
        observed.push(`${path}:${res.status()}`)
    })
    const initialBody = viewer.waitForResponse(
      (res) =>
        res.request().method() === 'GET' &&
        apiPath(res.url()) === `/api/games/${saved.id}/viewer` &&
        res.status() === 200,
      { timeout: 30_000 },
    )
    await viewer.goto(`${baseURL}/games/${saved.id}/view`)
    console.log(`PITCHLOG_VIEWER_STAGE=viewer-goto:${viewer.url()}`)
    try {
      await initialBody
    } catch {
      const body = await viewer
        .locator('body')
        .innerText({ timeout: 3000 })
        .catch(() => 'unavailable')
      throw new Error(
        `初回viewer GET未確認: url=${viewer.url()} responses=${observed.join(',')} body=${body.slice(0, 400)}`,
      )
    }
    console.log('PITCHLOG_VIEWER_STAGE=initial-body')
    await expect(viewer.getByTestId('viewer-status')).toHaveText('更新済み')
    const score = viewer.getByRole('region', { name: 'スコア' })
    await expect(score).toContainText('先攻')
    await expect(score).toContainText('後攻')
    await expect(
      viewer.getByRole('region', { name: '出場選手' }),
    ).toContainText('投手')
    const historyItems = viewer.locator('[data-testid="viewer-history"] li')
    await expect(historyItems).toHaveCount(25)
    await expect(viewer.getByTestId('viewer-page-index')).toHaveText(
      '表示ページ: 1',
    )
    await viewer.getByTestId('viewer-next-page').click()
    await expect(viewer.getByTestId('viewer-page-index')).toHaveText(
      '表示ページ: 2',
    )
    await expect(historyItems).toHaveCount(1)
    await expect(viewer.getByText(/第1球:/)).toBeVisible()
    await viewer.getByTestId('viewer-previous-page').click()
    await expect(viewer.getByTestId('viewer-page-index')).toHaveText(
      '表示ページ: 1',
    )
    await expect(historyItems).toHaveCount(25)
    const savedAt = Date.now()
    const recorded = await recordRealPitch(
      page,
      head,
      'batting-result.called-pitch',
      27,
    )
    head = recorded.head
    expect(head.prefix_ref.length).toBe('27')
    await expect(viewer.getByText(/第27球:/)).toBeVisible({ timeout: 10_000 })
    const visibleAt = Date.now()
    if (visibleAt - savedAt > 10_000)
      throw new Error(`10秒更新未達: ${visibleAt - savedAt}ms`)
    console.log(`PITCHLOG_VIEWER_GAME_ID=${saved.id}`)
    console.log(`PITCHLOG_VIEWER_VISIBLE_MS=${visibleAt - savedAt}`)
    await viewer.reload()
    await expect(viewer.getByText(/第27球:/)).toBeVisible()
    await viewerContext.setOffline(true)
    const disconnectedAt = Date.now()
    await expect(viewer.getByTestId('viewer-status')).toHaveText('未更新', {
      timeout: 13_000,
    })
    await expect(viewer.getByRole('region', { name: 'スコア' })).toHaveCount(0)
    console.log(
      `PITCHLOG_VIEWER_DISCONNECTED_MS=${Date.now() - disconnectedAt}`,
    )
    await viewerContext.setOffline(false)
    const recoveredAt = Date.now()
    await expect(viewer.getByTestId('viewer-status')).toHaveText('更新済み', {
      timeout: 15_000,
    })
    await expect(viewer.getByText(/第27球:/)).toBeVisible()
    console.log(`PITCHLOG_VIEWER_RECOVERED_MS=${Date.now() - recoveredAt}`)
    // 記録権・端末登録・同期送信を閲覧contextから一度も行っていない。
    expect(
      viewerApiRequests.filter(
        (value) =>
          value.includes('/devices/enroll') ||
          value.includes('/start') ||
          value.includes('/sync/events'),
      ),
    ).toEqual([])
    console.log(
      'PITCHLOG_VIEWER_API_REQUESTS=' + JSON.stringify(viewerApiRequests),
    )
    // 不存在・越境は404の「閲覧できません」へ閉じ、旧値を残さない。
    const missing = '00000000-0000-4000-8000-000000000000'
    await viewer.goto(`${baseURL}/games/${missing}/view`)
    await expect(viewer.getByTestId('viewer-status')).toHaveText(
      '閲覧できません',
    )
    await expect(viewer.getByRole('region', { name: 'スコア' })).toHaveCount(0)
    await viewer.goto(`${baseURL}/games/${saved.id}/view`)
    await expect(viewer.getByTestId('viewer-status')).toHaveText('更新済み')
    await expect(viewer.getByText(/第27球:/)).toBeVisible()
  } finally {
    await viewerContext.close().catch(() => undefined)
  }
})
