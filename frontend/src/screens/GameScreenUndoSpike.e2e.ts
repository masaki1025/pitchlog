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

test('実HTTPS画面で通常1球を保存し、取消・再取得・reloadで復元する', async ({
  page,
}) => {
  page.setDefaultTimeout(30_000)
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('取消spike縦断には実HTTPS originが必要です')
  try {
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
    await form.getByLabel('新しい大会名', { exact: true }).fill('取消spike大会')
    const created = page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === '/api/games',
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
    expect((await started).status()).toBe(200)

    const initialRead = page.waitForResponse(
      (res) =>
        res.request().method() === 'GET' &&
        apiPath(res.url()) === `/api/games/${saved.id}/started` &&
        res.url().includes('projection=ordinary-prefix-v1') &&
        res.status() === 200,
    )
    await expect(page.getByTestId('spike-load-ordinary')).toBeVisible()
    await page.getByTestId('spike-load-ordinary').click()
    const zero = await (await initialRead).json()
    expect(zero.prefix_ref.length).toBe('0')
    await expect(page.getByTestId('ordinary-state-source')).toHaveText(
      'サーバー確認済みの状態',
    )

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
    await page
      .getByTestId('ordinary-pitch-result')
      .selectOption('batting-result.ball')
    await page.getByTestId('first-ball-course').locator('svg').click()
    const posted = page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
    )
    const savedRead = page.waitForResponse(
      (res) =>
        res.request().method() === 'GET' &&
        apiPath(res.url()) === `/api/games/${saved.id}/started` &&
        res.url().includes('projection=ordinary-prefix-v1') &&
        res.status() === 200,
    )
    await expect(page.getByTestId('first-ball-save')).toBeEnabled()
    await page.getByTestId('first-ball-save').click()
    expect((await posted).status()).toBe(200)
    const first = (await (await savedRead).json()) as {
      prefix_ref: { length: string }
      after: { stateFields: Record<string, unknown> }
    }
    expect(first.prefix_ref.length).toBe('1')
    expect(first.after.stateFields['state.count.balls']).toBe('1')
    await expect(page.getByTestId('restore-history')).toHaveText('1件')

    // 同じ実画面に埋め込んだ取消spike panelで、サーバー由来の対象を確認する。
    const initial = page.waitForResponse(
      (res) =>
        res.request().method() === 'GET' &&
        apiPath(res.url()) === `/api/spike/games/${saved.id}/state` &&
        res.status() === 200,
    )
    await expect(page.getByTestId('undo-spike-reload')).toBeVisible()
    await page.getByTestId('undo-spike-reload').click()
    await expect(page.getByTestId('undo-spike-balls')).toHaveText('1')
    const spikeInitial = await (await initial).json()
    expect(spikeInitial.state.stateFields['state.count.balls']).toBe('1')
    expect(spikeInitial.history).toHaveLength(1)
    expect(spikeInitial.undoTarget.d1).toBe(1)
    await expect(page.getByTestId('undo-spike-target')).toContainText('D1 1')

    const undone = page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === `/api/spike/games/${saved.id}/undo` &&
        res.status() === 200,
    )
    const restored = page.waitForResponse(
      (res) =>
        res.request().method() === 'GET' &&
        apiPath(res.url()) === `/api/spike/games/${saved.id}/state` &&
        res.status() === 200,
    )
    await page.getByTestId('undo-spike-undo').click()
    const ack = (await (await undone).json()) as {
      eventResults: { a5Result: string }[]
    }
    expect(ack.eventResults[0]?.a5Result).toBe('受理')
    const after = await (await restored).json()
    expect(after.state.stateFields['state.count.balls']).toBe('0')
    expect(after.state.stateFields['state.count.strikes']).toBe('0')
    expect(after.history).toHaveLength(0)
    expect(
      after.events.map((item: { eventKind: string }) => item.eventKind),
    ).toEqual(['play_input', 'undo'])
    await expect(page.getByTestId('undo-spike-balls')).toHaveText('0')
    await expect(page.getByTestId('undo-spike-history')).toHaveText('0件')
    await expect(page.getByTestId('undo-spike-events')).toHaveText('2件')

    const reloaded = page.waitForResponse(
      (res) =>
        res.request().method() === 'GET' &&
        apiPath(res.url()) === `/api/spike/games/${saved.id}/state` &&
        res.status() === 200,
    )
    await page.reload()
    const reloadView = await (await reloaded).json()
    expect(reloadView.state).toEqual(after.state)
    expect(reloadView.history).toEqual([])
    await expect(page.getByTestId('undo-spike-balls')).toHaveText('0')
    await expect(page.getByTestId('undo-spike-history')).toHaveText('0件')
    console.log('PITCHLOG_UNDO_SPIKE_GAME_ID=' + saved.id)
  } catch (error) {
    const text = await page
      .locator('body')
      .innerText()
      .catch(() => '(本文なし)')
    throw new Error(
      `ORIG=${String(error)} URL=${page.url()} TEXT=${text.slice(0, 900)}`,
    )
  }
})
