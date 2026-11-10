/** 実画面の守備変更を、先発外の控え選手で保存し現在配置へ反映する。 */
import { expect, test, type Page } from '@playwright/test'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const away = process.env.PITCHLOG_E2E_AWAY_TEAM
const home = process.env.PITCHLOG_E2E_HOME_TEAM
const defender = '00000000-0000-0000-0000-0000000000d5'
if (!baseURL || !team || !password || !away || !home)
  throw new Error('守備変更E2Eの実app資格がenvにない')

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
  const posted = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === '/api/auth/login',
  )
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
  const response = await posted
  expect(response.status()).toBe(200)
  const body = (await response.json()) as { tenant_id?: string }
  if (typeof body.tenant_id !== 'string')
    throw new Error('login応答のtenantがない')
  return body.tenant_id
}

async function createAndStart(page: Page) {
  await page.getByRole('button', { name: '新規作成', exact: true }).click()
  const form = page.getByRole('region', { name: '試合の新規作成', exact: true })
  await form.getByLabel('日時（日本時間）').fill('2026-11-11T11:00')
  await form.getByTestId('game-type').selectOption('game_other')
  await form.getByTestId('away').selectOption(away!)
  await form.getByTestId('home').selectOption(home!)
  await form.getByTestId('tournament-kind').selectOption('new')
  await form
    .getByLabel('新しい大会名', { exact: true })
    .fill('守備変更画面試験大会')
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
    applied_rules: { dh: boolean }
  }
  await form
    .getByRole('button', {
      name: '作成した試合IDの保存値を確認',
      exact: true,
    })
    .click()
  await expect(page).toHaveURL(`${baseURL}/games/${saved.id}/record`)
  await page.getByRole('button', { name: 'この端末を登録' }).click()
  await expect(page.getByText('開始入力を確認できます')).toBeVisible()
  const dh = saved.applied_rules.dh === true
  for (const side of ['away', 'home'] as const) {
    const rows = dh ? 10 : 9
    const first = page.locator(`#start-${side}-0-player`)
    const values = await first
      .locator('option')
      .evaluateAll((options) =>
        options
          .map((option) => (option as HTMLOptionElement).value)
          .filter((value) => value.length > 0),
      )
    const pool =
      side === 'home' ? values.filter((value) => value !== defender) : values
    expect(pool.length).toBeGreaterThanOrEqual(rows)
    for (let index = 0; index < rows; index += 1) {
      const player = page.locator(`#start-${side}-${index}-player`)
      await player.selectOption(pool[index]!)
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
  await expect(page).toHaveURL(/\/record\?recording=play-prefix-v3/)
  await expect(page.getByTestId('ordinary-state-source')).toHaveText(
    'サーバー確認済みの状態',
  )
  return saved.id
}

async function recordBall(page: Page, gameId: string) {
  for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${name}`).check()
  await page
    .getByTestId('ordinary-pitch-result')
    .selectOption('batting-result.ball')
  const pitch = page.getByTestId('first-ball-pitch-type')
  await expect(pitch.locator('option')).not.toHaveCount(1)
  await pitch.selectOption({ index: 1 })
  await page.getByTestId('first-ball-course').locator('svg').click()
  const posted = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${gameId}/sync/events`,
  )
  await page.getByTestId('first-ball-save').click()
  const response = await posted
  expect(response.status()).toBe(200)
  expect((await response.json()).eventResults?.[0]?.a5Result).toBe('受理')
  await expect(page.getByTestId('restore-history')).toHaveText('1件')
}

type CurrentRead = {
  roster: {
    teams: Array<{
      side: 'away' | 'home'
      participants: Array<{
        player: { player_id: string }
        roles: Array<{ kind: string; position: string }>
      }>
    }>
  }
  checkpoint?: {
    content?: {
      restored?: {
        substitutionState?: {
          home: { fielding: Record<string, string | null> }
        }
      }
    }
  }
}

async function currentRead(page: Page, gameId: string, tenant: string) {
  const read = await page.evaluate(
    async ({ id, tenantId, challenge }) => {
      const response = await fetch(
        `/api/games/${id}/started?projection=play-prefix-v3&limit=1`,
        {
          credentials: 'same-origin',
          headers: {
            'X-Pitchlog-Expected-Tenant': tenantId,
            'X-Pitchlog-Tenant-Challenge': challenge,
          },
        },
      )
      return { status: response.status, body: await response.json() }
    },
    { id: gameId, tenantId: tenant, challenge: crypto.randomUUID() },
  )
  expect(read.status).toBe(200)
  return read.body as CurrentRead
}

test('実画面で守備変更を保存し現在配置へ反映する', async ({ page }) => {
  page.setDefaultTimeout(30_000)
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('実HTTPSが必要です')
  const tenant = await login(page)
  const gameId = await createAndStart(page)
  await recordBall(page, gameId)

  const before = await currentRead(page, gameId, tenant)
  const shortstop = before.roster.teams
    .find((item) => item.side === 'home')
    ?.participants.find((player) =>
      player.roles.some(
        (role) => role.kind === 'fielding' && role.position === '6',
      ),
    )
  if (!shortstop) throw new Error('守備側の遊撃手がいない')

  const panel = page.getByTestId('substitution-product-panel')
  await panel.getByRole('button', { name: '現在の交代原本を再取得' }).click()
  for (const checkbox of await panel.locator('input[type=checkbox]').all())
    await checkbox.check()
  await expect(panel.getByTestId('substitution-product-status')).toHaveText(
    '交代を選んでください',
  )
  await panel.getByTestId('substitution-kind').selectOption('defense')
  await panel
    .getByTestId('substitution-outgoing')
    .selectOption(shortstop.player.player_id)
  await panel.getByTestId('substitution-incoming-mode').selectOption('existing')
  await panel.getByTestId('substitution-incoming').selectOption(defender)
  await panel.locator('[data-normal-question="side"]').selectOption('home')
  await panel.locator('[data-normal-question="position"]').selectOption('6')
  await expect(panel.getByTestId('substitution-apply')).toBeEnabled()
  const posted = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${gameId}/sync/events`,
  )
  await panel.getByTestId('substitution-apply').click()
  const response = await posted
  expect(response.status()).toBe(200)
  const ack = await response.json()
  expect(ack.eventResults?.[0]?.a5Result).toBe('受理')
  await expect(panel.getByTestId('substitution-product-status')).toHaveText(
    '交代を保存し、現在状態を再取得しました',
  )
  const after = await currentRead(page, gameId, tenant)
  expect(
    after.checkpoint?.content?.restored?.substitutionState?.home.fielding['6'],
  ).toBe(defender)
  console.log(
    'PITCHLOG_DEFENSE_FINAL=' +
      JSON.stringify({
        gameId,
        outgoing: shortstop.player.player_id,
        incoming: defender,
        accepted: 2,
      }),
  )
})
