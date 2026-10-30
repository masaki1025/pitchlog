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

test('実画面で新規作成し、その試合を開始してGET /started initialを得る', async ({
  page,
}) => {
  try {
    const tenant = await login(page)
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
    const read = await page.evaluate(
      async (value) => {
        const response = await fetch(`/api/games/${value.id}/started`, {
          headers: {
            'X-Pitchlog-Expected-Tenant': value.tenant,
            'X-Pitchlog-Tenant-Challenge': crypto.randomUUID(),
            'X-Pitchlog-Request': '1',
          },
        })
        return { status: response.status, text: await response.text() }
      },
      { id: saved.id, tenant },
    )
    expect(read.status).toBe(200)
    const view = JSON.parse(read.text) as {
      read_kind: string
      id: string
      state: { stateFields: Record<string, string> }
    }
    expect(view.read_kind).toBe('initial')
    expect(view.id).toBe(saved.id)
    expect(view.state.stateFields['state.count.balls']).toBe('0')
  } catch (error) {
    const text = await page
      .locator('body')
      .innerText()
      .catch(() => '(本文なし)')
    throw new Error(
      `ORIG=${String(error)} URL=${page.url()} TEXT=${text.slice(0, 700)}`,
    )
  }
})
