import { expect, test, type Page } from '@playwright/test'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const away = process.env.PITCHLOG_E2E_AWAY_TEAM
const home = process.env.PITCHLOG_E2E_HOME_TEAM
const incoming = '00000000-0000-0000-0000-0000000000d3'
if (!baseURL || !team || !password || !away || !home)
  throw new Error('交代E2Eの実app資格がenvにない')

function apiPath(url: string): string {
  return new URL(url).pathname
}

async function login(page: Page): Promise<void> {
  await page.goto(`${baseURL}/login?redirect=/games`)
  await expect(page.locator('form[aria-busy]')).toHaveAttribute(
    'aria-busy',
    'false',
  )
  await page.getByRole('textbox', { name: 'チーム名' }).fill(team!)
  await page.getByLabel('パスワード').fill(password!)
  const posted = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === '/api/auth/login',
  )
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
  expect((await posted).status()).toBe(200)
}

async function acceptedSync(
  page: Page,
  gameId: string,
  action: () => Promise<void>,
) {
  const posted = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${gameId}/sync/events`,
    { timeout: 45_000 },
  )
  await action()
  const response = await posted
  expect(response.status()).toBe(200)
  const ack = await response.json()
  expect(ack.eventResults?.[0]?.a5Result).toBe('受理')
  return ack
}

test('実画面の新規作成→開始→投手交代→次球→再取得', async ({ page }) => {
  page.setDefaultTimeout(30_000)
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('実HTTPSが必要です')
  await login(page)
  await page.getByRole('button', { name: '新しい試合', exact: true }).click()
  const form = page.getByRole('region', { name: '試合の新規作成', exact: true })
  await form.getByLabel('日時（日本時間）').fill('2026-11-06T10:00')
  await form.getByTestId('game-type').selectOption('game_other')
  await form.getByTestId('away').selectOption(away!)
  await form.getByTestId('home').selectOption(home!)
  await form.getByTestId('tournament-kind').selectOption('new')
  await form
    .getByLabel('新しい大会名', { exact: true })
    .fill('交代画面試験大会')
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
  await form
    .getByRole('button', { name: '作成した試合IDの保存値を確認', exact: true })
    .click()
  await expect(page).toHaveURL(`${baseURL}/games/${saved.id}/record`)
  await page.getByRole('button', { name: 'この端末を登録' }).click()
  await expect(page.getByText('開始入力を確認できます')).toBeVisible()
  const dh = saved.applied_rules.dh === true
  let outgoing = ''
  for (const side of ['away', 'home'] as const) {
    for (let index = 0; index < (dh ? 10 : 9); index++) {
      const player = page.locator(`#start-${side}-${index}-player`)
      await player.selectOption({ index: index + 1 })
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
      if (side === 'home' && (dh ? index === 9 : index === 0))
        outgoing = await player.inputValue()
    }
  }
  expect(outgoing).not.toBe('')
  const started = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${saved.id}/start`,
  )
  await page.getByRole('button', { name: '試合を開始', exact: true }).click()
  expect((await started).status()).toBe(200)
  await expect(page).toHaveURL(/\/record\?recording=play-prefix-v3/)
  await expect(page.getByTestId('ordinary-state-source')).toHaveText(
    'サーバー確認済み',
  )
  for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${name}`).check()
  await page
    .getByTestId('ordinary-pitch-result')
    .selectOption('batting-result.ball')
  const pitchType = page.getByTestId('first-ball-pitch-type')
  await expect(pitchType.locator('option')).not.toHaveCount(1)
  await pitchType.selectOption({ index: 1 })
  await page.getByTestId('first-ball-course').locator('svg').click()
  await acceptedSync(page, saved.id, () =>
    page.getByTestId('first-ball-save').click(),
  )
  await expect(page.getByTestId('restore-history')).toHaveText('1件')

  const panel = page.getByTestId('substitution-product-panel')
  await panel.getByRole('button', { name: '現在の交代原本を再取得' }).click()
  for (const checkbox of await panel.locator('input[type=checkbox]').all())
    await checkbox.check()
  await expect(panel.getByTestId('substitution-product-status')).toHaveText(
    '交代を選んでください',
  )
  await panel.getByTestId('substitution-kind').selectOption('pitcher')
  await panel.getByTestId('substitution-outgoing').selectOption(outgoing)
  await panel.getByTestId('substitution-incoming-mode').selectOption('existing')
  await panel.getByTestId('substitution-incoming').selectOption(incoming)
  for (const [key, value] of [
    ['side', 'home'],
    ['strikes', '0'],
    ['balls', '1'],
    ['dh', 'retain'],
  ] as const)
    await panel.locator(`[data-normal-question="${key}"]`).selectOption(value)
  await expect(panel.getByTestId('substitution-apply')).toBeEnabled()
  await acceptedSync(page, saved.id, () =>
    panel.getByTestId('substitution-apply').click(),
  )
  await expect(panel.getByTestId('substitution-product-status')).toHaveText(
    '交代を保存し、現在状態を再取得しました',
  )

  const input = page.getByTestId('undo-product-panel')
  await input.getByTestId('undo-product-reload').click()
  await expect(input.getByTestId('undo-product-balls')).toHaveText('1')
  for (const checkbox of await input.locator('input[type=checkbox]').all())
    await checkbox.check()
  const nextPitch = input.getByTestId('undo-product-pitch-type')
  await expect(nextPitch.locator('option')).not.toHaveCount(1)
  await nextPitch.selectOption({ index: 1 })
  await input.getByTestId('undo-product-course').locator('svg').click()
  await acceptedSync(page, saved.id, () =>
    input.getByTestId('undo-product-ball').click(),
  )
  await expect(input.getByTestId('undo-product-balls')).toHaveText('2')
  await page.reload()
  await input.getByTestId('undo-product-reload').click()
  await expect(input.getByTestId('undo-product-balls')).toHaveText('2')
  await panel.getByRole('button', { name: '現在の交代原本を再取得' }).click()
  await expect(panel.getByTestId('substitution-product-status')).toHaveText(
    '交代を選んでください',
  )
  console.log(
    'PITCHLOG_SUBSTITUTION_FINAL=' +
      JSON.stringify({
        gameId: saved.id,
        outgoing,
        incoming,
        accepted: 3,
        balls: 2,
      }),
  )
})
