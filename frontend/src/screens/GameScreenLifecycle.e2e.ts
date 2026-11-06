// 終了→追記再開→2球追記→再終了→再読込の実画面E2E。
//
// このfileは実認可・実PG・実画面が揃うまで成功しない。環境変数が無い場合や
// root接合（router mount・既通常/NP入力driver・backend 0043/ACL）が未提供の
// 場合は、黙ってskipせず不足を列挙して失敗する。固定応答で成功を作らない。
//
// 実行条件（rootが隔離PG・専用tenantで用意する。値はrepoへ保存しない）:
//   PITCHLOG_LIFECYCLE_E2E_BASE_URL  実HTTPSのVite/アプリURL
//   PITCHLOG_LIFECYCLE_E2E_GAME_ID   実作成・開始済みの試合ID（未終了）
import { expect, test } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

const MISSING = [
  'PITCHLOG_LIFECYCLE_E2E_BASE_URL',
  'PITCHLOG_LIFECYCLE_E2E_GAME_ID',
] as const

function requiredEnvironment(): { baseUrl: string; gameId: string } {
  const missing = MISSING.filter((key) => !process.env[key])
  if (missing.length > 0)
    throw new Error(
      `lifecycle実画面E2E未成立: 実server/実PG/root接合が未提供です（${missing.join(', ')}）。` +
        '必要: 正式game_reopen/参加区分/C12、packet 2f464208 のbackend受理、' +
        'GameScreenLifecyclePanelのrouter mount、既通常/NP入力driverの接続。',
    )
  return {
    baseUrl: process.env.PITCHLOG_LIFECYCLE_E2E_BASE_URL!,
    gameId: process.env.PITCHLOG_LIFECYCLE_E2E_GAME_ID!,
  }
}

async function openLifecycleGame(page: import('@playwright/test').Page) {
  const { baseUrl, gameId } = requiredEnvironment()
  await page.goto(`${baseUrl}/games/${gameId}`, {
    waitUntil: 'domcontentloaded',
  })
  const panel = page.getByTestId('lifecycle-panel')
  await expect(panel).toBeVisible({ timeout: 20_000 })
  return panel
}

test('終了v1→再開→2球→再終了v2→reloadを実server/実PGで通す', async ({
  page,
}) => {
  const panel = await openLifecycleGame(page)

  await test.step('実GETで進行中・確定版v0を表示する', async () => {
    await expect(panel.getByTestId('lifecycle-status')).toHaveText('進行中')
    await expect(panel.getByTestId('lifecycle-refresh-state')).toContainText(
      '取得済み',
    )
    await expect(panel.getByTestId('lifecycle-unknown-count')).toHaveText('0件')
  })

  await test.step('終了v1を宣言し、実GET再取得で終了とv1を確認する', async () => {
    await panel.getByTestId('lifecycle-end').click()
    await expect(panel.getByTestId('lifecycle-status')).toHaveText('終了', {
      timeout: 20_000,
    })
    await expect(panel.getByTestId('lifecycle-last-version')).toHaveText('v1')
    await expect(panel.getByTestId('lifecycle-active')).toHaveText('v1')
    await expect(panel.getByTestId('lifecycle-save-ack')).toContainText('受理')
  })

  await test.step('reloadしても実GETから終了v1を復元する', async () => {
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('lifecycle-panel')).toBeVisible({
      timeout: 20_000,
    })
    const reloaded = page.getByTestId('lifecycle-panel')
    await expect(reloaded.getByTestId('lifecycle-status')).toHaveText('終了')
    await expect(reloaded.getByTestId('lifecycle-last-version')).toHaveText(
      'v1',
    )
  })

  await test.step('追記のために再開し、実GETで進行中へ戻る', async () => {
    await panel.getByTestId('lifecycle-reopen').click()
    await expect(panel.getByTestId('lifecycle-status')).toHaveText('進行中', {
      timeout: 20_000,
    })
    await expect(panel.getByTestId('lifecycle-active')).toHaveText(
      'なし（進行中）',
    )
    await expect(panel.getByTestId('lifecycle-resume')).toBeVisible()
  })

  await test.step('既通常/NP入力driverで2球を追記する（計算は再実装しない）', async () => {
    // root の mount patch が既通常/NP入力controllerへ接続するまで、このステップは
    // 実driverを持たない。ここを成功stubで埋めない。
    throw new Error(
      '2球追記driverが未接続です。rootのmount patchで既通常/NP入力controllerへ接続し、' +
        'このステップを実driverの呼出（同一pageで2球を確定し、実GETのnext_positionが進むことの確認）へ置換してください。' +
        'lifecycle E2Eはこの欠落を成功にしません。',
    )
  })

  await test.step('再終了v2を宣言し、v2を実GETで確認する', async () => {
    await panel.getByTestId('lifecycle-end').click()
    await expect(panel.getByTestId('lifecycle-status')).toHaveText('終了', {
      timeout: 20_000,
    })
    await expect(panel.getByTestId('lifecycle-last-version')).toHaveText('v2')
    await expect(panel.getByTestId('lifecycle-active')).toHaveText('v2')
  })

  await test.step('再読込後も終了v2を実GETから復元する', async () => {
    await page.reload({ waitUntil: 'domcontentloaded' })
    const reloaded = page.getByTestId('lifecycle-panel')
    await expect(reloaded).toBeVisible({ timeout: 20_000 })
    await expect(reloaded.getByTestId('lifecycle-status')).toHaveText('終了')
    await expect(reloaded.getByTestId('lifecycle-last-version')).toHaveText(
      'v2',
    )
    await expect(reloaded.getByTestId('lifecycle-unknown-count')).toHaveText(
      '0件',
    )
  })
})

test('同一D5/同本文の再送は確定版を増やさない（ACK喪失）', async ({ page }) => {
  await openLifecycleGame(page)
  const panel = page.getByTestId('lifecycle-panel')

  // 最初の同期POSTだけを落とす。server側の受理/拒否は実DBで決まる。
  let dropped = false
  await page.route('**/api/games/*/sync/events', async (route) => {
    if (!dropped) {
      dropped = true
      await route.abort('connectionreset')
      return
    }
    await route.continue()
  })

  await panel.getByTestId('lifecycle-end').click()
  await expect(panel.getByTestId('lifecycle-unknown-count')).toHaveText('1件', {
    timeout: 20_000,
  })
  await expect(panel.getByTestId('lifecycle-save-ack')).toHaveText('未確認')

  await panel.getByTestId('lifecycle-retry').click()
  await expect(panel.getByTestId('lifecycle-status')).toHaveText('終了', {
    timeout: 20_000,
  })
  // 再送は同D5/同本文だけなので v2 へ増えない。
  await expect(panel.getByTestId('lifecycle-last-version')).toHaveText('v1')
})

test('二重タブでは非所有タブが追記しない', async ({ browser }) => {
  const context = await browser.newContext({ ignoreHTTPSErrors: true })
  const holder = await context.newPage()
  await openLifecycleGame(holder)
  const second = await context.newPage()
  await openLifecycleGame(second)

  // 先のタブが同期POST中（排他保持中）に、後のタブが終了を押す。
  await holder.route('**/api/games/*/sync/events', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 3_000))
    await route.continue()
  })
  const inFlight = holder
    .getByTestId('lifecycle-panel')
    .getByTestId('lifecycle-end')
    .click()
  const nonOwner = second.getByTestId('lifecycle-panel')
  await nonOwner.getByTestId('lifecycle-end').click()
  await expect(nonOwner.getByTestId('lifecycle-failure')).toContainText(
    '別のタブ',
    { timeout: 20_000 },
  )
  await inFlight
  await context.close()
})

test('不可視試合/取得失敗は状態を表示しない', async ({ page }) => {
  const { baseUrl, gameId } = requiredEnvironment()
  await page.goto(`${baseUrl}/games/${gameId}`, {
    waitUntil: 'domcontentloaded',
  })
  const panel = page.getByTestId('lifecycle-panel')
  await expect(panel.getByTestId('lifecycle-status')).toHaveText('未取得', {
    timeout: 20_000,
  })
  await expect(panel.getByTestId('lifecycle-failure')).toContainText(
    '取得できません',
  )
})
