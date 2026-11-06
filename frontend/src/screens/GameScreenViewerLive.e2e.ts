import { expect, test, type Page } from '@playwright/test'

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
  await login(page)
  await page.getByRole('button', { name: '新規作成', exact: true }).click()
  const form = page.getByRole('region', {
    name: '試合の新規作成',
    exact: true,
  })
  await expect(form.getByLabel('日時（日本時間）')).toBeEnabled()
  await form.getByLabel('日時（日本時間）').fill('2026-10-31T10:00')
  await form.getByTestId('game-type').selectOption('game_other')
  await form.getByTestId('away').selectOption(away!)
  await form.getByTestId('home').selectOption(home!)
  await form.getByTestId('tournament-kind').selectOption('new')
  await form.getByLabel('新しい大会名', { exact: true }).fill('画面作成大会')
  const created = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' && apiPath(res.url()) === '/api/games',
  )
  await form
    .getByRole('button', { name: '準備中の試合を作成', exact: true })
    .click()
  const createdResponse = await created
  expect(createdResponse.status()).toBe(201)
  const saved = (await createdResponse.json()) as {
    id: string
    status: string
    applied_rules: { dh: boolean }
  }
  expect(saved.status).toBe('preparing')
  // 作成した試合の保存値を確認すると記録画面へ遷移する。
  await form
    .getByRole('button', {
      name: '作成した試合IDの保存値を確認',
      exact: true,
    })
    .click()
  await expect(page).toHaveURL(`${baseURL}/games/${saved.id}/record`)
  await expect(
    page.getByRole('heading', { name: 'スタメンと試合開始' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'この端末を登録' }).click()
  await expect(page.getByText('開始入力を確認できます')).toBeVisible()
  const dh = saved.applied_rules.dh === true
  for (const side of ['away', 'home'] as const) {
    const rows = dh ? 10 : 9
    for (let index = 0; index < rows; index += 1) {
      await page
        .locator(`#start-${side}-${index}-player`)
        .selectOption({ index: index + 1 })
      const position =
        index === 9
          ? '1'
          : dh
            ? index === 8
              ? 'DH'
              : String(index + 2)
            : String(index + 1)
      await page
        .locator(`#start-${side}-${index}-position`)
        .selectOption(position)
    }
  }
  const started = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${saved.id}/start`,
  )
  await page.getByRole('button', { name: '試合を開始', exact: true }).click()
  const startedResponse = await started
  expect(startedResponse.status()).toBe(200)
  async function selectAndSave(result: string) {
    // 履歴表示と入力context再束縛は別の更新。実server由来の入力へ戻ってから操作する。
    await expect(page.getByTestId('ordinary-state-source')).toHaveText(
      'サーバー確認済みの状態',
    )
    await expect(page.getByTestId('ordinary-pitch-result')).toBeVisible()
    for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
      await page.getByTestId(`first-ball-env-${name}`).check()
    const pitch = page.getByTestId('first-ball-pitch-type')
    await expect(pitch).toBeEnabled()
    await expect(pitch.locator('option')).not.toHaveCount(1)
    await pitch.selectOption({ index: 1 })
    await page.getByTestId('ordinary-pitch-result').selectOption(result)
    await page.getByTestId('first-ball-course').locator('svg').click()
    const posted = page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
    )
    await expect(page.getByTestId('first-ball-save')).toBeEnabled()
    await page.getByTestId('first-ball-save').click()
    const response = await posted
    expect(response.status()).toBe(200)
    const ack = (await response.json()) as {
      eventResults?: readonly { a5Result?: string }[]
    }
    expect(ack.eventResults?.[0]?.a5Result).toBe('受理')
  }

  const viewerContext = await browser.newContext({ ignoreHTTPSErrors: true })
  const viewer = await viewerContext.newPage()
  viewer.setDefaultTimeout(30_000)
  try {
    await login(viewer)
    console.log('PITCHLOG_VIEWER_STAGE=second-login')
    const observed: string[] = []
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
    await expect(score).toContainText('先攻 0 – 後攻 0')
    await expect(score).toContainText('1回表')
    await expect(score).toContainText('0アウト')
    await expect(score).toContainText('走者: なし')
    await expect(
      viewer.getByRole('region', { name: '出場選手' }),
    ).toContainText('投手')
    await expect(
      viewer.getByText('まだ確定済みの投球はありません。'),
    ).toBeVisible()
    // 新規開始の受理後は現入口が自動的にv3記録へ接ぐ。
    await expect(page.getByTestId('ordinary-state-source')).toHaveText(
      'サーバー確認済みの状態',
    )
    await selectAndSave('batting-result.called-pitch')
    const savedAt = Date.now()
    await expect(viewer.getByText(/第1球:/)).toBeVisible({ timeout: 10_000 })
    const visibleAt = Date.now()
    if (visibleAt - savedAt > 10_000)
      throw new Error(`10秒更新未達: ${visibleAt - savedAt}ms`)
    console.log(`PITCHLOG_VIEWER_GAME_ID=${saved.id}`)
    console.log(`PITCHLOG_VIEWER_VISIBLE_MS=${visibleAt - savedAt}`)
    await viewer.reload()
    await expect(viewer.getByText(/第1球:/)).toBeVisible()
    await viewerContext.setOffline(true)
    await expect(viewer.getByTestId('viewer-status')).toHaveText('未更新', {
      timeout: 13_000,
    })
    await expect(viewer.getByRole('region', { name: 'スコア' })).toHaveCount(0)
  } finally {
    await viewerContext.close().catch(() => undefined)
  }
})
