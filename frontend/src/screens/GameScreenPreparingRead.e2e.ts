import { expect, test, type Page, type Response } from '@playwright/test'
import { readGameScreenE2eRuntime } from './GameScreenE2eSupport'

function matches(res: Response, method: string, path: string): boolean {
  return (
    res.request().method() === method && new URL(res.url()).pathname === path
  )
}

function read(page: Page, path: string): Promise<Response | null> {
  return page
    .waitForResponse((res) => matches(res, 'GET', path))
    .catch(() => null)
}

async function success(res: Response | null): Promise<Response> {
  if (!res || res.status() !== 200) throw new Error('実readのHTTP成功がない')
  const sent = res.request().headers()
  if (
    res.headers()['x-pitchlog-tenant-match'] !== '1' ||
    res.headers()['x-pitchlog-tenant-challenge'] !==
      sent['x-pitchlog-tenant-challenge'] ||
    res.headers()['cache-control'] !== 'no-store'
  )
    throw new Error('実readのC2またはno-storeが成立しない')
  return res
}

async function displayedRulesMatch(page: Page, game: unknown): Promise<void> {
  if (typeof game !== 'object' || game === null || !('applied_rules' in game))
    throw new Error('実readに保存規則がない')
  const shown = page.locator('pre')
  await expect(shown).toBeVisible()
  expect(JSON.parse((await shown.textContent()) ?? 'null')).toEqual(
    game.applied_rules,
  )
}

async function login(page: Page): Promise<void> {
  const runtime = readGameScreenE2eRuntime()
  const identity = runtime.identities[0]
  if (!identity) throw new Error('専用認証fixtureがない')
  await page.goto(`${runtime.baseURL}/login?redirect=/games`)
  await expect(page.locator('form[aria-busy]')).toHaveAttribute(
    'aria-busy',
    'false',
  )
  const name = page.getByRole('textbox', { name: 'チーム名' })
  await expect(name).toBeEnabled()
  await name.fill(identity.name)
  await page.getByLabel('パスワード').fill(identity.password)
  const posted = page
    .waitForResponse((res) => matches(res, 'POST', '/api/auth/login'))
    .catch(() => null)
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
  const response = await posted
  if (!response || response.status() !== 200)
    throw new Error('実login POSTが成功しない')
  const body: unknown = await response.json()
  if (
    typeof body !== 'object' ||
    body === null ||
    !('tenant_id' in body) ||
    body.tenant_id !== identity.tenantId
  )
    throw new Error('実loginのtenantが一致しない')
  const reverify = page.getByRole('button', {
    name: '状態を再確認',
    exact: true,
  })
  await expect(
    page.getByRole('heading', { name: '準備中の試合' }).or(reverify),
  ).toBeVisible()
  if (await reverify.isVisible()) await reverify.click()
  await expect(page).toHaveURL(`${runtime.baseURL}/games`)
  // PlaywrightのHTTP URLフィルタはloopbackでもSecure Cookieを除外する。
  // 全cookieからdomain/path/属性を照合し、値は出力しない。
  const cookies = await page.context().cookies()
  if (
    !cookies.some(
      (cookie) =>
        cookie.name === '__Host-pitchlog_token' &&
        cookie.domain === '127.0.0.1' &&
        cookie.path === '/' &&
        cookie.secure &&
        cookie.httpOnly,
    )
  )
    throw new Error('実loginのSecure/HttpOnly Cookieがない')
  if (!(await page.evaluate(() => window.isSecureContext)))
    throw new Error('loopbackのsecure contextが成立しない')
}

test('実loginから一覧・詳細・再読込を実APIと専用DBへ通す', async ({ page }) => {
  const runtime = readGameScreenE2eRuntime()
  if (!runtime.preparingGameId) throw new Error('専用read seedのIDがない')
  const mutations: string[] = []
  page.on('request', (request) => {
    if (
      new URL(request.url()).pathname.startsWith('/api/games') &&
      request.method() !== 'GET'
    )
      mutations.push(request.method())
  })
  const first = read(page, '/api/games')
  await login(page)
  await success(await first)
  const list = page.getByRole('region', { name: '試合一覧', exact: true })
  await expect(list.getByRole('link', { name: '閲覧画面へ' })).toHaveCount(20)
  await expect(list).toContainText('<b>保存ラベル</b>')
  await expect(list.locator('b')).toHaveCount(0)
  const next = read(page, '/api/games')
  await page.getByRole('button', { name: '次のページ', exact: true }).click()
  await success(await next)
  await expect(list).toContainText('2ページ目')
  const previous = read(page, '/api/games')
  await page.getByRole('button', { name: '前のページ', exact: true }).click()
  await success(await previous)
  await expect(list).toContainText('1ページ目')
  const path = `/api/games/${runtime.preparingGameId}`
  const detail = read(page, path)
  await list.getByRole('link', { name: '閲覧画面へ' }).first().click()
  const saved: unknown = await (await success(await detail)).json()
  await expect(
    page.getByRole('heading', { name: '準備中試合の保存情報' }),
  ).toBeVisible()
  await expect(page.locator('main').last()).toContainText(
    runtime.preparingGameId,
  )
  await expect(page.locator('main').last()).toContainText(
    'スタメン・記録権・下書き復元：未取得',
  )
  await expect(page.getByRole('button', { name: '1球を確定' })).toHaveCount(0)
  const reload = read(page, path)
  await page.reload()
  expect(await (await success(await reload)).json()).toEqual(saved)
  await displayedRulesMatch(page, saved)
  expect(mutations).toEqual([])
})

test('別tenantと不存在を同じ404で拒否し明示再試行でも情報を表示しない', async ({
  page,
}) => {
  const runtime = readGameScreenE2eRuntime()
  await login(page)
  await expect(
    page
      .getByRole('region', { name: '試合一覧', exact: true })
      .getByRole('link', { name: '閲覧画面へ' }),
  ).toHaveCount(20)
  for (const id of [
    '00000000-0000-0000-0000-000000000014',
    '00000000-0000-0000-0000-0000000003e7',
  ]) {
    const response = read(page, `/api/games/${id}`)
    await page.goto(`${runtime.baseURL}/games/${id}/record`)
    if ((await response)?.status() !== 404)
      throw new Error('不可視readの404が成立しない')
    await expect(page.locator('main').last()).toContainText(
      'この試合の情報を確認できません',
    )
    await expect(page.locator('pre')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '1球を確定' })).toHaveCount(0)
    const retry = read(page, `/api/games/${id}`)
    await page.getByRole('button', { name: 'この試合を再試行' }).click()
    if ((await retry)?.status() !== 404)
      throw new Error('再試行が同じ拒否を保持しない')
  }
})

test('read通信が失われたら旧保存情報を破棄し明示確認後にだけ取得する', async ({
  page,
}) => {
  const runtime = readGameScreenE2eRuntime()
  const id = runtime.preparingGameId
  if (!id) throw new Error('専用read seedのIDがない')
  await login(page)
  await expect(
    page
      .getByRole('region', { name: '試合一覧', exact: true })
      .getByRole('link', { name: '閲覧画面へ' }),
  ).toHaveCount(20)
  let attempts = 0
  const pattern = `**/api/games/${id}`
  await page.route(pattern, async (route) => {
    attempts += 1
    // 故障だけを注入し、成功応答や認証結果を作らない。
    await route.abort('failed')
  })
  await page.getByRole('link', { name: '閲覧画面へ' }).first().click()
  await expect(page).toHaveURL(/\/login\?/)
  await expect(page.locator('pre')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '1球を確定' })).toHaveCount(0)
  const reverify = page.getByRole('button', {
    name: '状態を再確認',
    exact: true,
  })
  await expect(reverify).toBeEnabled()
  expect(attempts).toBe(1)
  await page.unroute(pattern)
  const restored = read(page, `/api/games/${id}`)
  await reverify.click()
  const restoredGame: unknown = await (await success(await restored)).json()
  await displayedRulesMatch(page, restoredGame)
})
