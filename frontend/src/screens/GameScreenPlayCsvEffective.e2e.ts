import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { isAbsolute, join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const away = process.env.PITCHLOG_E2E_AWAY_TEAM
const home = process.env.PITCHLOG_E2E_HOME_TEAM
const output = process.env.PITCHLOG_E2E_CSV_DOWNLOAD_DIR
const observer = process.env.PITCHLOG_E2E_CSV_OBSERVER_DIR
if (!baseURL || !team || !password || !away || !home || !output)
  throw new Error('所有画面試験の実環境入力が不足')
if (!isAbsolute(output) || !existsSync(output))
  throw new Error('所有画面試験の保存先が不正')
if (!observer || !isAbsolute(observer) || !existsSync(observer))
  throw new Error('所有画面試験の版観測先が不正')

const timeout = 30_000
const path = (url: string) => new URL(url).pathname

async function login(page: Page): Promise<void> {
  await page.goto(`${baseURL}/login?redirect=/games`)
  await expect(page.locator('form[aria-busy]')).toHaveAttribute(
    'aria-busy',
    'false',
  )
  await page.getByRole('textbox', { name: 'チーム名' }).fill(team!)
  await page.getByLabel('パスワード').fill(password!)
  const posted = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      path(response.url()) === '/api/auth/login',
  )
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
  expect((await posted).status()).toBe(200)
}

async function createStartedGame(page: Page): Promise<string> {
  await page.getByRole('button', { name: '新しい試合', exact: true }).click()
  const form = page.getByRole('region', {
    name: '試合の新規作成',
    exact: true,
  })
  await expect(form.getByLabel('日時（日本時間）')).toBeEnabled()
  await form.getByLabel('日時（日本時間）').fill('2026-11-07T10:00')
  await form.getByTestId('game-type').selectOption('game_other')
  await form.getByTestId('away').selectOption(away!)
  await form.getByTestId('home').selectOption(home!)
  await form.getByTestId('tournament-kind').selectOption('new')
  await form.getByLabel('新しい大会名', { exact: true }).fill('有効版CSV大会')
  const created = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      path(response.url()) === '/api/games',
  )
  await form
    .getByRole('button', { name: '準備中の試合を作成', exact: true })
    .click()
  const response = await created
  expect(response.status()).toBe(201)
  const saved = (await response.json()) as {
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
  for (const side of ['away', 'home'] as const) {
    for (let index = 0; index < (saved.applied_rules.dh ? 10 : 9); index++) {
      await page
        .locator(`#start-${side}-${index}-player`)
        .selectOption({ index: index + 1 })
      const position =
        index === 9
          ? '1'
          : saved.applied_rules.dh
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
      path(res.url()) === `/api/games/${saved.id}/start`,
  )
  await page.getByRole('button', { name: '試合を開始', exact: true }).click()
  expect((await started).status()).toBe(200)
  await page.waitForURL(
    `${baseURL}/games/${saved.id}/record?recording=play-prefix-v3`,
  )
  // 開始直後は準備中入口の再取得が進行中。記録済み入口を実GETで開き直す。
  await page.reload()
  await expect(page.getByTestId('undo-product-panel')).toBeVisible()
  // 初球前は取消対象CPが無くundo-prefix-v1が409となる。保存球後に読取る。
  return saved.id
}

async function recordBall(page: Page, game: string): Promise<void> {
  await expect(page.getByTestId('ordinary-state-source')).toHaveText(
    'サーバー確認済み',
  )
  for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${name}`).check()
  const pitch = page.getByTestId('first-ball-pitch-type')
  await expect(pitch.locator('option')).not.toHaveCount(1)
  await pitch.selectOption({ index: 1 })
  await page
    .getByTestId('ordinary-pitch-result')
    .selectOption('batting-result.ball')
  await page.getByTestId('first-ball-course').locator('svg').click()
  const posted = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      path(res.url()) === `/api/games/${game}/sync/events`,
  )
  await page.getByTestId('first-ball-save').click()
  const response = await posted
  expect(response.status()).toBe(200)
  const body = (await response.json()) as {
    eventResults?: Array<{ a5Result: string }>
  }
  expect(body.eventResults?.[0]?.a5Result).toBe('受理')
  console.log(
    'PITCHLOG_EFFECTIVE_POST_VIEW=' +
      JSON.stringify({
        panel: await page.getByTestId('undo-product-panel').count(),
        depth: await page.getByTestId('undo-product-depth').count(),
        undoStatus: await page
          .getByTestId('undo-product-status')
          .allTextContents(),
        ordinary: await page.getByTestId('ordinary-state-source').count(),
        route: new URL(page.url()).pathname,
      }),
  )
}

async function undo(page: Page, game: string, depth: string): Promise<void> {
  const panel = page.getByTestId('undo-product-panel')
  if ((await panel.count()) === 0) {
    // POST応答後の表示切替とは独立に、記録済み入口の実GETを開き直す。
    console.log('PITCHLOG_EFFECTIVE_UNDO_PANEL_RELOAD=required')
    await page.goto(`${baseURL}/games/${game}/record?recording=play-prefix-v3`)
  }
  if ((await panel.getByTestId('undo-product-depth').count()) === 0) {
    // 初球前の409を新規操作へ置換せず、保存後の明示再取得で閉原本を確認する。
    const read = page.waitForResponse(
      (res) =>
        res.request().method() === 'GET' &&
        path(res.url()) === `/api/games/${game}/started` &&
        new URL(res.url()).searchParams.get('projection') === 'undo-prefix-v1',
    )
    await panel.getByTestId('undo-product-reload').click()
    expect((await read).status()).toBe(200)
  }
  await expect(panel.getByTestId('undo-product-depth')).toHaveText(depth)
  for (const box of await panel.locator('input[type=checkbox]').all())
    await box.check()
  const posted = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      path(res.url()) === `/api/games/${game}/sync/events`,
  )
  await panel.getByTestId('undo-product-apply').click()
  const response = await posted
  expect(response.status()).toBe(200)
  const body = (await response.json()) as {
    eventResults?: Array<{ a5Result: string }>
  }
  expect(body.eventResults?.[0]?.a5Result).toBe('受理')
  await expect(panel.getByTestId('undo-product-depth')).toHaveText(
    String(Number(depth) - 1),
  )
}

async function downloadCsv(page: Page, game: string, label: string) {
  await page.getByRole('link', { name: '毎球CSVへ' }).click()
  await expect(page).toHaveURL(`${baseURL}/games/${game}/export`)
  const received = page.waitForResponse(
    (res) =>
      res.request().method() === 'GET' &&
      path(res.url()) === `/api/games/${game}/exports/plays.zip`,
    { timeout },
  )
  const downloaded = page.waitForEvent('download', { timeout })
  await page.getByRole('button', { name: '毎球CSVをダウンロード' }).click()
  const [response, download] = await Promise.all([received, downloaded])
  expect(response.status()).toBe(200)
  const filename = join(output!, `${label}.zip`)
  await download.saveAs(filename)
  const data = readFileSync(filename)
  expect(data.length).toBe(Number(response.headers()['content-length']))
  expect(createHash('sha256').update(data).digest('hex')).toBe(
    response.headers()['x-pitchlog-archive-sha256'],
  )
  await expect(page.getByText('毎球CSVを保存しました')).toBeVisible()
  // 画面操作を進める前に同じ保存版のDB pointerを別接続で観測する。
  writeFileSync(join(observer!, `${label}.ready`), game, { flag: 'wx' })
  await expect
    .poll(() => existsSync(join(observer!, `${label}.observed`)), {
      timeout: 30_000,
    })
    .toBe(true)
  await page.goto(`${baseURL}/games/${game}/record?recording=play-prefix-v3`)
  return { label, filename, bytes: data.length }
}

test('実取消で一球残存と全取消をCSVへ反映し、再入力とreload後も旧原本を保持する', async ({
  page,
}) => {
  page.setDefaultTimeout(timeout)
  page.on('response', (response) => {
    const url = new URL(response.url())
    if (
      response.request().method() === 'GET' &&
      url.pathname.endsWith('/started') &&
      url.searchParams.get('projection') === 'undo-prefix-v1'
    )
      console.log(`PITCHLOG_EFFECTIVE_UNDO_GET=${response.status()}`)
  })
  await page.addInitScript(() => {
    const native = window.fetch.bind(window)
    let original: { url: string; init: RequestInit } | undefined
    window.fetch = async (input, init) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url
      if (
        init?.method === 'POST' &&
        typeof init.body === 'string' &&
        init.body.includes('"event_kind":"undo"')
      )
        original = {
          url,
          init: {
            ...init,
            headers: new Headers(init.headers),
            body: init.body,
          },
        }
      return native(input, init)
    }
    Object.defineProperty(window, '__replayEffectiveUndo', {
      value: async () => {
        if (!original) throw new Error('取消の原要求がない')
        const response = await native(original.url, original.init)
        return {
          status: response.status,
          body: (await response.json()) as {
            eventResults: Array<{ a5Result: string }>
          },
        }
      },
    })
  })
  await login(page)
  const game = await createStartedGame(page)
  await recordBall(page, game)
  await recordBall(page, game)
  await undo(page, game, '2')
  const replay = await page.evaluate(() =>
    (
      window as unknown as {
        __replayEffectiveUndo: () => Promise<{
          status: number
          body: { eventResults: Array<{ a5Result: string }> }
        }>
      }
    ).__replayEffectiveUndo(),
  )
  expect(replay.status).toBe(200)
  expect(replay.body.eventResults[0]?.a5Result).toBe('重複')
  const one = await downloadCsv(page, game, 'one-current')
  await undo(page, game, '1')
  const zero = await downloadCsv(page, game, 'all-undone')
  const panel = page.getByTestId('undo-product-panel')
  await expect(panel.getByTestId('undo-product-depth')).toHaveText('0')
  for (const box of await panel.locator('input[type=checkbox]').all())
    await box.check()
  const pitch = panel.getByTestId('undo-product-pitch-type')
  await expect(pitch.locator('option')).not.toHaveCount(1)
  await pitch.selectOption({ index: 1 })
  await panel.getByTestId('undo-product-course').locator('svg').click()
  const reentryStarted = Date.now()
  const reentryPosted = page
    .waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        path(res.url()) === `/api/games/${game}/sync/events`,
      { timeout: 60_000 },
    )
    .catch(() => null)
  await panel.getByTestId('undo-product-ball').click()
  const reentryResponse = await reentryPosted
  console.log(
    'PITCHLOG_EFFECTIVE_REENTRY=' +
      JSON.stringify({
        http: reentryResponse?.status() ?? null,
        elapsedMs: Date.now() - reentryStarted,
        status: await panel.getByTestId('undo-product-status').textContent(),
        depth: await panel.getByTestId('undo-product-depth').textContent(),
        locks: await page.evaluate(async () => {
          const state = await navigator.locks.query()
          return {
            held: state.held?.length ?? 0,
            pending: state.pending?.length ?? 0,
          }
        }),
      }),
  )
  expect(reentryResponse?.status()).toBe(200)
  await expect(panel.getByTestId('undo-product-depth')).toHaveText('1')
  const reentered = await downloadCsv(page, game, 'reentered')
  await page.reload()
  await expect(page.getByTestId('undo-product-depth')).toHaveText('1')
  const reloaded = await downloadCsv(page, game, 'reloaded')
  console.log(
    'PITCHLOG_EFFECTIVE_CSV_RESULT=' +
      JSON.stringify({ game, files: [one, zero, reentered, reloaded] }),
  )
})
