import { createHash } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'
import { join } from 'node:path'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const away = process.env.PITCHLOG_E2E_AWAY_TEAM
const home = process.env.PITCHLOG_E2E_HOME_TEAM
if (!baseURL || !team || !password || !away || !home)
  throw new Error('E2Eの実app資格がenvにない')

function path(url: string): string {
  return new URL(url).pathname
}

async function confirmSafety(page: Page) {
  // 復元後に別Sheetが開いていても、安全確認の可視導線へ戻る。
  await page.keyboard.press('Escape').catch(() => undefined)
  const safety = page.getByRole('button', { name: /記録端末の安全確認/ })
  if (!(await safety.isVisible().catch(() => false))) return
  await safety.click()
  for (const label of [
    'ほかの記録タブと同じブラウザプロファイルを使います',
    '通常・プライベートなどの閲覧モードを統一します',
    '同じサイトの保存領域を使うタブだけで記録します',
    'この端末でLockdownモードを適用していません',
  ])
    await page.getByRole('checkbox', { name: label }).last().check()
  await page
    .getByRole('button', { name: '確認して記録へ戻る', exact: true })
    .click()
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
    (response) =>
      response.request().method() === 'POST' &&
      path(response.url()) === '/api/auth/login',
  )
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
  expect((await posted).status()).toBe(200)
}

async function createAndStart(
  page: Page,
  gameDate: string,
): Promise<Readonly<{ gameId: string; pitchKey: string }>> {
  await login(page)
  await page.getByRole('button', { name: '新しい試合', exact: true }).click()
  const form = page.getByRole('region', { name: '試合の新規作成', exact: true })
  await expect(form.getByLabel('日時（日本時間）')).toBeEnabled()
  await form.getByLabel('日時（日本時間）').fill(gameDate)
  await form.getByTestId('game-type').selectOption('game_other')
  await form.getByTestId('away').selectOption(away!)
  await form.getByTestId('home').selectOption(home!)
  await form.getByTestId('tournament-kind').selectOption('new')
  await form
    .getByLabel('新しい大会名', { exact: true })
    .fill(`結果不明復旧 ${gameDate}`)
  const created = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      path(response.url()) === '/api/games',
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
  await page.getByRole('button', { name: 'この端末を登録' }).click()
  await expect(page.getByText('開始入力を確認できます')).toBeVisible()
  for (const side of ['away', 'home'] as const) {
    const count = saved.applied_rules.dh ? 10 : 9
    for (let index = 0; index < count; index += 1) {
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
    (response) =>
      response.request().method() === 'POST' &&
      path(response.url()) === `/api/games/${saved.id}/start`,
  )
  await page.getByRole('button', { name: '試合を開始', exact: true }).click()
  expect((await started).status()).toBe(200)
  await expect(page).toHaveURL(/record\?recording=play-prefix-v3/)
  await expect(page.getByTestId('ordinary-pitch-result')).toBeVisible()
  await expect(
    page.getByTestId('first-ball-pitch-type').locator('option'),
  ).not.toHaveCount(1)
  const pitchKey = await page
    .getByTestId('first-ball-pitch-type')
    .locator('option')
    .nth(1)
    .getAttribute('value')
  if (!pitchKey) throw new Error('実語彙の球種keyがありません')
  return { gameId: saved.id, pitchKey }
}

// 実HTTP応答の喪失/送信前の断だけを注入する。成功応答やPortは置換しない。
test('実browserを閉じて同profileを再起動し、元要求を復旧して1回だけ保存する', async ({
  playwright,
}, info) => {
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('実HTTPSが必要です')
  const completed: {
    gameId: string
    mode: string
    originalBodySha: string
    originalAttemptSha: string
  }[] = []
  for (const mode of ['ack-lost', 'before-http'] as const) {
    const profile = join(info.outputDir, `browser-profile-${mode}`)
    const options = {
      headless: true,
      ignoreHTTPSErrors: true,
      args: ['--ignore-certificate-errors'],
      viewport: { width: 1280, height: 900 },
    }
    let context = await playwright.chromium.launchPersistentContext(
      profile,
      options,
    )
    const protocol = {
      resent: 0,
      recoveries: 0,
      acknowledgements: [] as string[],
      resolutions: [] as string[],
    }
    try {
      let page = context.pages()[0] ?? (await context.newPage())
      page.setDefaultTimeout(60_000)
      const { gameId, pitchKey } = await createAndStart(
        page,
        mode === 'ack-lost' ? '2026-11-07T10:00' : '2026-11-07T13:00',
      )
      const recordingUrl = page.url()
      expect(new URL(recordingUrl).searchParams.get('recording')).toBe(
        'play-prefix-v3',
      )
      const syncPath = `/api/games/${gameId}/sync/events`
      let originalBodySha = '',
        originalAttemptSha = '',
        injected = false
      await page.route(`**${syncPath}`, async (route) => {
        const request = route.request()
        if (request.method() !== 'POST' || injected) return route.continue()
        injected = true
        const body = request.postData()
        const attempt = request.headers()['x-pitchlog-sync-attempt']
        if (!body || !attempt) throw new Error('原要求の本文/試行がありません')
        originalBodySha = createHash('sha256').update(body).digest('hex')
        originalAttemptSha = createHash('sha256').update(attempt).digest('hex')
        if (mode === 'ack-lost') {
          const actual = await route.fetch({ timeout: 120_000 })
          expect(actual.status()).toBe(200)
          const ack = await actual.json()
          expect(ack.advancedD3).toBe(1)
          expect(ack.eventResults[0].a5Result).toBe('受理')
        }
        await route.abort('failed')
      })
      await confirmSafety(page)
      await page.getByTestId('first-ball-pitch-type').selectOption(pitchKey)
      await page.getByTestId('first-ball-course').locator('svg').click()
      await page.locator('[data-result-id="batting-result.ball"]').click()
      await expect
        .poll(() => originalBodySha, { timeout: 120_000 })
        .toMatch(/^[a-f0-9]{64}$/)
      await expect(page.getByTestId('first-ball-retry')).toBeVisible({
        timeout: 120_000,
      })
      const browser = context.browser()
      await context.close()
      expect(browser?.isConnected()).toBe(false)
      context = await playwright.chromium.launchPersistentContext(
        profile,
        options,
      )
      page = context.pages()[0] ?? (await context.newPage())
      page.setDefaultTimeout(60_000)
      const resent: { body: string; attempt: string }[] = []
      const recoveries: { body: string; attempt: string }[] = []
      const acknowledgements = protocol.acknowledgements
      const resolutions = protocol.resolutions
      page.on('request', (request) => {
        if (request.method() !== 'POST') return
        const url = path(request.url())
        if (
          url !== syncPath &&
          url !== `/api/games/${gameId}/sync/attempts/recover`
        )
          return
        const body = request.postData(),
          attempt = request.headers()['x-pitchlog-sync-attempt']
        if (!body || !attempt) throw new Error('復元した原要求がありません')
        const value = {
          body: createHash('sha256').update(body).digest('hex'),
          attempt: createHash('sha256').update(attempt).digest('hex'),
        }
        if (url === syncPath) {
          resent.push(value)
          protocol.resent++
        } else {
          recoveries.push(value)
          protocol.recoveries++
        }
      })
      page.on('response', async (response) => {
        if (response.request().method() !== 'POST' || response.status() !== 200)
          return
        const url = path(response.url())
        if (url === syncPath)
          acknowledgements.push(
            (await response.json()).eventResults[0].a5Result,
          )
        if (url === `/api/games/${gameId}/sync/attempts/recover`)
          resolutions.push((await response.json()).resolution)
      })
      await page.goto(recordingUrl)
      // session cookieの寿命を延ばさず、再起動でloginが必要なら実画面を通す。
      if (new URL(page.url()).pathname === '/login') {
        await login(page)
        await page.goto(recordingUrl)
      }
      // 再起動後は復元入口を実画面で開き、記録画面へ戻ってから確認する。
      const restore = page.getByRole('button', { name: 'サーバーから復元' })
      if (await restore.isVisible().catch(() => false)) await restore.click()
      await expect(page.getByTestId('ordinary-pitch-result')).toBeVisible({
        timeout: 60_000,
      })
      await confirmSafety(page)
      // 未確認要求は自動送信しない。可視の照会導線からだけ終結を確認する。
      const inspect = page.getByTestId('first-ball-inspect')
      await expect(inspect).toBeVisible({ timeout: 60_000 })
      await expect(inspect).toBeEnabled({ timeout: 60_000 })
      let recoverAttempts = 0
      const recoverPath = `/api/games/${gameId}/sync/attempts/recover`
      await page.route(`**${recoverPath}`, async (route) => {
        recoverAttempts += 1
        // 1回目は照会中の切断。保存要求へ進まず、再照会できることを確認する。
        if (recoverAttempts === 1) return route.abort('failed')
        return route.continue()
      })
      await inspect.click()
      await expect.poll(() => recoverAttempts, { timeout: 30_000 }).toBe(1)
      await expect(inspect).toBeEnabled({ timeout: 60_000 })
      expect(resent).toHaveLength(0)
      await inspect.click()
      await expect.poll(() => resolutions.length, { timeout: 120_000 }).toBe(1)
      await page.unroute(`**${recoverPath}`)
      const retry = page.getByTestId('first-ball-retry')
      await expect(retry).toBeEnabled({ timeout: 60_000 })
      await retry.click()
      await expect
        .poll(() => acknowledgements.length, { timeout: 180_000 })
        .toBe(1)
      expect(resolutions).toEqual(['retry_allowed'])
      // 切断された照会も成功した照会も、元本文/元attemptのまま。
      expect(recoveries).toEqual([
        { body: originalBodySha, attempt: originalAttemptSha },
        { body: originalBodySha, attempt: originalAttemptSha },
      ])
      expect(resent).toHaveLength(1)
      expect(resent[0]!.body).toBe(originalBodySha)
      expect(resent[0]!.attempt).not.toBe(originalAttemptSha)
      expect(acknowledgements).toEqual([mode === 'ack-lost' ? '重複' : '受理'])
      const read = page.waitForResponse(
        async (response) =>
          response.request().method() === 'GET' &&
          path(response.url()) === `/api/games/${gameId}/started` &&
          response.status() === 200 &&
          (await response.json()).prefix_ref?.length === '1',
      )
      await page.reload()
      const restored = await (await read).json()
      expect(restored.after.stateFields['state.count.balls']).toBe('1')
      expect(restored.after.stateFields['state.count.strikes']).toBe('0')
      expect(restored.page.items).toHaveLength(1)
      completed.push({ gameId, mode, originalBodySha, originalAttemptSha })
    } catch (error) {
      const current = context.pages()[0]
      const diagnostic =
        current && !current.isClosed()
          ? await current
              .evaluate(() => {
                let authPhase: string | null = null
                try {
                  authPhase =
                    JSON.parse(localStorage.getItem('bb.auth.intent') ?? 'null')
                      ?.phase ?? null
                } catch {
                  /* 原文は出さない。 */
                }
                return {
                  path: location.pathname,
                  online: navigator.onLine,
                  secure: isSecureContext,
                  authPhase,
                  headings: [...document.querySelectorAll('h1,h2')].map(
                    (node) => node.textContent?.slice(0, 100),
                  ),
                  notices: [
                    ...document.querySelectorAll(
                      '[role="status"],[role="alert"]',
                    ),
                  ].map((node) => node.textContent?.slice(0, 250)),
                }
              })
              .catch(() => ({ unavailable: true }))
          : { unavailable: true }
      console.log(
        'PITCHLOG_ATTEMPT_RECOVERY_UI_DIAGNOSTIC=' +
          JSON.stringify({ mode, ...protocol, ...diagnostic }),
      )
      throw error
    } finally {
      await context.close()
    }
  }
  console.log(
    'PITCHLOG_ATTEMPT_RECOVERY_BROWSER_GAMES=' + JSON.stringify(completed),
  )
})
