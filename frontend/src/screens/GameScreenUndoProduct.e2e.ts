import { createHash } from 'node:crypto'
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
  return body.tenant_id
}

test('実画面の新規作成→開始→2球→ACK喪失/reload/同要求再送→2取消→次球/reload', async ({
  page,
}) => {
  page.setDefaultTimeout(30_000)
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('実HTTPSが必要です')
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    let lose = false
    Object.defineProperty(window, '__loseUndoProductAckOnce', {
      value: () => {
        lose = true
      },
    })
    window.fetch = async (input, init) => {
      const response = await original(input, init)
      if (lose && init?.method === 'POST' && typeof init.body === 'string') {
        const body: unknown = JSON.parse(init.body)
        if (
          body !== null &&
          typeof body === 'object' &&
          'events' in body &&
          Array.isArray(body.events) &&
          body.events[0]?.event_kind === 'undo' &&
          response.status === 200
        ) {
          lose = false
          throw new TypeError('isolated ACK loss after real save')
        }
      }
      return response
    }
  })
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
  console.log('PITCHLOG_UNDO_ATTEMPT_GAME=' + saved.id)
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

  const requests: Array<{
    bodySha256: string
    attemptSha256: string
    kind: string
  }> = []
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      apiPath(request.url()) === `/api/games/${saved.id}/sync/events`
    ) {
      const raw = request.postData(),
        attempt = request.headers()['x-pitchlog-sync-attempt']
      if (!raw || !attempt) throw new Error('実要求識別が不足')
      const body = JSON.parse(raw)
      requests.push({
        bodySha256: createHash('sha256').update(raw).digest('hex'),
        attemptSha256: createHash('sha256').update(attempt).digest('hex'),
        kind: body.events[0]?.event_kind,
      })
    }
  })
  await page
    .getByRole('button', {
      name: '三振・攻守交代を含む投球の記録へ',
      exact: true,
    })
    .click()
  for (let n = 1; n <= 2; n++) {
    await expect(page.getByTestId('ordinary-state-source')).toHaveText(
      'サーバー確認済みの状態',
    )
    for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
      await page.getByTestId(`first-ball-env-${name}`).check()
    await page
      .getByTestId('ordinary-pitch-result')
      .selectOption('batting-result.ball')
    const pitch = page.getByTestId('first-ball-pitch-type')
    await expect(pitch.locator('option')).not.toHaveCount(1)
    await pitch.selectOption({ index: 1 })
    await page.getByTestId('first-ball-course').locator('svg').click()
    const posted = page
      .waitForResponse(
        (res) =>
          res.request().method() === 'POST' &&
          apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
        { timeout: 10_000 },
      )
      .catch(() => null)
    await page.getByTestId('first-ball-save').click()
    const response = await posted
    console.log(
      'PITCHLOG_UNDO_ORDINARY_HTTP=' +
        JSON.stringify({
          pitch: n,
          postedRequests: requests.length,
          locks: await page.evaluate(async () => {
            if (!navigator.locks) return null
            const snapshot = await navigator.locks.query()
            return {
              held: snapshot.held?.length ?? 0,
              pending: snapshot.pending?.length ?? 0,
            }
          }),
          http: response?.status() ?? null,
          status: await page.getByTestId('first-ball-status').textContent(),
        }),
    )
    if (response === null) {
      // 元の10秒条件は失敗のまま保持し、遅延応答の有無だけ追加観測する。
      const late = await page
        .waitForResponse(
          (res) =>
            res.request().method() === 'POST' &&
            apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
          { timeout: 30_000 },
        )
        .catch(() => null)
      console.log(
        'PITCHLOG_UNDO_LATE_HTTP=' +
          JSON.stringify({ pitch: n, http: late?.status() ?? null }),
      )
    }
    expect(response).not.toBeNull()
    expect(response!.status()).toBe(200)
    const ack = await response!.json()
    const a5 = ack.eventResults?.[0]?.a5Result
    console.log(
      'PITCHLOG_UNDO_ORDINARY_ACK=' +
        JSON.stringify({
          pitch: n,
          a5: ['受理', '重複', '拒否', '退避', '未処理'].includes(a5)
            ? a5
            : 'unexpected',
          d3: Number.isSafeInteger(ack.advancedD3) ? ack.advancedD3 : null,
        }),
    )
    expect(a5).toBe('受理')
    await expect(page.getByTestId('restore-history')).toHaveText(`${n}件`)
  }
  let panel = page.getByTestId('undo-product-panel')
  await panel.getByTestId('undo-product-reload').click()
  await expect(panel.getByTestId('undo-product-balls')).toHaveText('2')
  await expect(panel.getByTestId('undo-product-depth')).toHaveText('2')
  for (const box of await panel.locator('input[type=checkbox]').all())
    await box.check()
  await page.evaluate(() => {
    const descriptor = Object.getOwnPropertyDescriptor(
      window,
      '__loseUndoProductAckOnce',
    )
    if (typeof descriptor?.value !== 'function')
      throw new Error('ACK故障注入が未配置')
    descriptor.value()
  })
  await panel.getByTestId('undo-product-apply').click()
  await expect(panel.getByTestId('undo-product-status')).toContainText(
    '結果未確認',
  )
  await page.reload()
  panel = page.getByTestId('undo-product-panel')
  await expect(panel.getByTestId('undo-product-balls')).toHaveText('1')
  await expect(panel.getByTestId('undo-product-depth')).toHaveText('1')
  await expect(panel.getByTestId('undo-product-status')).toContainText(
    '結果未確認',
  )
  for (const box of await panel.locator('input[type=checkbox]').all())
    await box.check()
  await panel.getByTestId('undo-product-retry').click()
  await expect(panel.getByTestId('undo-product-status')).toContainText(
    'サーバーで確認',
  )
  const replay = requests.filter((x) => x.kind === 'undo')
  expect(replay).toHaveLength(2)
  expect(replay[1]).toEqual(replay[0])
  await panel.getByTestId('undo-product-apply').click()
  await expect(panel.getByTestId('undo-product-balls')).toHaveText('0')
  await expect(panel.getByTestId('undo-product-depth')).toHaveText('0')
  await expect(panel.getByTestId('undo-product-apply')).toBeDisabled()
  const pitch = panel.getByTestId('undo-product-pitch-type')
  await expect(pitch.locator('option')).not.toHaveCount(1)
  await pitch.selectOption({ index: 1 })
  await panel.getByTestId('undo-product-course').locator('svg').click()
  await panel.getByTestId('undo-product-ball').click()
  await expect(panel.getByTestId('undo-product-balls')).toHaveText('1')
  await expect(panel.getByTestId('undo-product-depth')).toHaveText('1')
  await page.reload()
  panel = page.getByTestId('undo-product-panel')
  await expect(panel.getByTestId('undo-product-balls')).toHaveText('1')
  await expect(panel.getByTestId('undo-product-depth')).toHaveText('1')
  console.log('PITCHLOG_UNDO_PRODUCT_GAME=' + saved.id)
})
