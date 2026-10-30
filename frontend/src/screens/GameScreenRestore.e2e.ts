import { expect, test, type Page } from '@playwright/test'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const game = process.env.PITCHLOG_E2E_GAME_ID
if (!baseURL || !team || !password || !game)
  throw new Error('E2Eの実app資格がenvにない')

function apiPath(url: string): string {
  return new URL(url).pathname
}

async function loginFromRedirect(page: Page): Promise<void> {
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
}

test('記録済み1球を再読込でサーバーから復元し、取得失敗で旧値を残さない', async ({
  page,
}) => {
  const bad: string[] = []
  page.on('response', (response) => {
    if (response.url().includes('/api/') && response.status() >= 400)
      bad.push(`${response.status()} ${apiPath(response.url())}`)
  })
  try {
    await page.goto(`${baseURL}/games/${game}/record`)
    await loginFromRedirect(page)
    await expect(page.getByText('サーバーから復元した状態')).toBeVisible()
    // 端末が開始した記録がないため自動復元しない。明示操作で実サーバーから取得する。
    const started = page.waitForResponse(
      (res) =>
        res.request().method() === 'GET' &&
        apiPath(res.url()) === `/api/games/${game}/started`,
    )
    await page.getByRole('button', { name: 'サーバーから復元' }).click()
    const view = (await (await started).json()) as {
      read_kind: string
      after: { stateFields: Record<string, string> }
      state: { stateFields: Record<string, string> }
      history: unknown[]
      play_rows: unknown[]
    }
    expect(view.read_kind).toBe('recorded')
    expect(view.after.stateFields['state.count.balls']).toBe('1')
    // 現在状態はafter（1ボール）、開始前のbeforeは0のまま。
    await expect(page.getByTestId('restore-balls')).toHaveText('1')
    await expect(page.getByTestId('restore-strikes')).toHaveText('0')
    await expect(page.getByTestId('restore-outs')).toHaveText('0')
    await expect(page.getByTestId('restore-runners')).toHaveText('empty')
    await expect(page.getByTestId('restore-before-balls')).toHaveText('0')
    await expect(page.getByTestId('restore-history')).toHaveText('1件')
    await expect(page.getByTestId('restore-plays')).toHaveText('1件')
    await expect(page.getByText('記録済み（保存初球1件）')).toBeVisible()
    // 明示再取得でも同じサーバー値を得る。
    const again = page.waitForResponse(
      (res) =>
        res.request().method() === 'GET' &&
        apiPath(res.url()) === `/api/games/${game}/started`,
    )
    await page.getByRole('button', { name: 'サーバーから再取得' }).click()
    expect((await again).status()).toBe(200)
  } catch (error) {
    const text = await page
      .locator('body')
      .innerText()
      .catch(() => '(本文なし)')
    throw new Error(
      `ORIG=${String(error)} URL=${page.url()} BAD=${bad.join(',')} TEXT=${text.slice(0, 600)}`,
    )
  }
})
