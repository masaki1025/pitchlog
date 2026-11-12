import { createHash } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'

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
): Promise<Readonly<{ gameId: string; pitchKey: string }>> {
  await login(page)
  await page.getByRole('button', { name: '新しい試合', exact: true }).click()
  const form = page.getByRole('region', { name: '試合の新規作成', exact: true })
  await expect(form.getByLabel('日時（日本時間）')).toBeEnabled()
  await form.getByLabel('日時（日本時間）').fill('2026-10-31T10:00')
  await form.getByTestId('game-type').selectOption('game_other')
  await form.getByTestId('away').selectOption(away!)
  await form.getByTestId('home').selectOption(home!)
  await form.getByTestId('tournament-kind').selectOption('new')
  await form
    .getByLabel('新しい大会名', { exact: true })
    .fill('断中再起動画面大会')
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

async function waitForPreparedScope(page: Page, gameId: string): Promise<void> {
  await page.waitForFunction(async (game) => {
    if (
      typeof indexedDB.databases !== 'function' ||
      !(await indexedDB.databases()).some(
        (database) =>
          database.name === 'pitchlog-local-recording-permission-v1',
      )
    )
      return false
    return new Promise<boolean>((resolve) => {
      const opened = indexedDB.open('pitchlog-local-recording-permission-v1')
      opened.onerror = () => resolve(false)
      opened.onsuccess = () => {
        const db = opened.result
        try {
          const tx = db.transaction('permissions', 'readonly')
          const request = tx.objectStore('permissions').getAll()
          request.onsuccess = () =>
            resolve(
              request.result.some(
                (row: {
                  gameId?: string
                  tenantId?: string
                  correlation?: {
                    intentId?: string
                    uncertaintyNotice?: string | null
                  }
                  pages?: { cursor: string | null }[]
                }) =>
                  row.gameId === game &&
                  (() => {
                    const marker = JSON.parse(
                      localStorage.getItem('bb.auth.intent') ?? 'null',
                    ) as {
                      phase?: string
                      tenantId?: string
                      intentId?: string
                    } | null
                    return (
                      marker?.phase === 'expected' &&
                      row.tenantId === marker.tenantId &&
                      row.correlation?.intentId === marker.intentId &&
                      row.correlation?.uncertaintyNotice ===
                        localStorage.getItem('bb.auth.uncertain') &&
                      localStorage.getItem('bb.auth.uncertain') ===
                        localStorage.getItem('bb.auth.uncertain.ack')
                    )
                  })() &&
                  row.pages?.some((page) => page.cursor === null),
              ),
            )
          request.onerror = () => resolve(false)
          tx.oncomplete = tx.onabort = () => db.close()
        } catch {
          db.close()
          resolve(false)
        }
      }
    })
  }, gameId)
}

async function preparedHashes(
  page: Page,
): Promise<readonly { body: string; attempt: string }[]> {
  return page.evaluate(async () => {
    const opened = indexedDB.open('pitchlog-ordinary-prepared-envelope-v1')
    const rows = await new Promise<
      {
        d1: number
        attemptId: string
        requestBody: unknown
      }[]
    >((resolve, reject) => {
      opened.onerror = () => reject(new Error('原文保存域を開けません'))
      opened.onsuccess = () => {
        const db = opened.result
        const tx = db.transaction('prepared', 'readonly')
        const request = tx.objectStore('prepared').getAll()
        request.onsuccess = () => resolve(request.result)
        request.onerror = () => reject(new Error('原文を読めません'))
        tx.oncomplete = tx.onabort = () => db.close()
      }
    })
    async function sha(value: string) {
      const bytes = await crypto.subtle.digest(
        'SHA-256',
        new TextEncoder().encode(value),
      )
      return [...new Uint8Array(bytes)]
        .map((byte) => byte.toString(16).padStart(2, '0'))
        .join('')
    }
    return Promise.all(
      rows
        .sort((a, b) => a.d1 - b.d1)
        .map(async (row) => ({
          body: await sha(JSON.stringify(row.requestBody)),
          attempt: await sha(row.attemptId),
        })),
    )
  })
}

// 失敗時は公開UIと相関の状態だけを記録し、Cookie/本文/資格値は出さない。
test.afterEach(async ({ page }, info) => {
  if (info.status === info.expectedStatus || page.isClosed()) return
  const diagnostic = await page
    .evaluate(() => {
      let phase: string | null = null
      try {
        phase =
          JSON.parse(localStorage.getItem('bb.auth.intent') ?? 'null')?.phase ??
          null
      } catch {
        /* 原文は出さない。 */
      }
      return {
        path: location.pathname,
        onlineHint: navigator.onLine,
        secure: isSecureContext,
        intentPhase: phase,
        uncertaintyConfirmed:
          localStorage.getItem('bb.auth.uncertain') ===
          localStorage.getItem('bb.auth.uncertain.ack'),
        headings: [...document.querySelectorAll('h1,h2')].map((n) =>
          n.textContent?.slice(0, 100),
        ),
        notices: [
          ...document.querySelectorAll('[role="status"],[role="alert"]'),
        ].map((n) => n.textContent?.slice(0, 250)),
      }
    })
    .catch(() => ({ unavailable: true }))
  console.log('PITCHLOG_OFFLINE_UI_DIAGNOSTIC=' + JSON.stringify(diagnostic))
})

async function confirmSafety(page: import('@playwright/test').Page) {
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

test('production SWで真の断中cold再起動から2球を同原文順で同期する', async ({
  page,
  context,
}) => {
  page.setDefaultTimeout(30_000)
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('production SW縦断には実HTTPSが必要です')
  const { gameId, pitchKey } = await createAndStart(page)
  await waitForPreparedScope(page, gameId)
  await page.waitForFunction(
    async () => {
      const registration = await navigator.serviceWorker.getRegistration()
      return registration?.active?.state === 'activated'
    },
    null,
    { timeout: 30_000 },
  )
  await page.reload()
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null)
  // オンラインreload自身のsession/C2と新nonceの準備完了後に切断する。
  await expect(page.getByTestId('ordinary-pitch-result')).toBeVisible()
  await expect(
    page.getByTestId('first-ball-pitch-type').locator('option'),
  ).not.toHaveCount(1)
  await waitForPreparedScope(page, gameId)
  const syncPath = `/api/games/${gameId}/sync/events`
  const requests: { body: string; attempt: string }[] = []
  page.on('request', (request) => {
    if (request.method() !== 'POST' || path(request.url()) !== syncPath) return
    const body = request.postData()
    const attempt = request.headers()['x-pitchlog-sync-attempt']
    if (!body || !attempt)
      throw new Error('原文またはattempt headerがありません')
    requests.push({
      body: createHash('sha256').update(body).digest('hex'),
      attempt: createHash('sha256').update(attempt).digest('hex'),
    })
  })
  await context.setOffline(true)
  expect(await page.evaluate(() => navigator.onLine)).toBe(false)
  await page.reload()
  await expect(
    page.getByRole('heading', { name: '端末内の記録' }),
  ).toBeVisible()
  await expect(page.getByTestId('ordinary-local-notice')).toBeVisible()
  await confirmSafety(page)
  for (const n of [1, 2]) {
    await expect(page.getByTestId('first-ball-pitch-type')).toBeEnabled()
    await page.getByTestId('first-ball-pitch-type').selectOption(pitchKey)
    await page.getByTestId('first-ball-course').locator('svg').click()
    // 通常結果は可視の結果パッドが保存を開始する。sr-onlyの保存ボタンは使わない。
    await page.locator('[data-result-id="batting-result.ball"]').click()
    await expect(page.getByTestId('ordinary-local-balls')).toHaveText(String(n))
  }
  expect(requests).toHaveLength(0)
  await page.reload()
  await expect(
    page.getByRole('heading', { name: '端末内の記録' }),
  ).toBeVisible()
  // 新しいpageの入力開始条件は再確認し、旧mountの確認を認証済みとして持ち越さない。
  await confirmSafety(page)
  await expect(page.getByTestId('ordinary-local-balls')).toHaveText('2')
  const originals = await preparedHashes(page)
  expect(originals).toHaveLength(2)
  expect(requests).toHaveLength(0)

  await context.setOffline(false)
  await page.waitForFunction(() => navigator.onLine === true)
  const verified = page.waitForResponse(
    (response) =>
      response.request().method() === 'GET' &&
      path(response.url()) === '/api/auth/session' &&
      response.status() === 200,
  )
  await page
    .getByRole('button', { name: '接続を確認して未送信記録を同期する' })
    .click()
  await verified
  await expect(page.getByTestId('ordinary-pitch-result')).toBeVisible()
  await confirmSafety(page)
  await expect.poll(() => requests.length, { timeout: 180_000 }).toBe(2)
  expect(requests).toEqual(originals)

  const finalRead = page.waitForResponse(
    async (response) =>
      response.request().method() === 'GET' &&
      path(response.url()) === `/api/games/${gameId}/started` &&
      response.status() === 200 &&
      (await response.json()).prefix_ref?.length === '2',
  )
  // 第2要求のACKと自動GETが終わるまでreloadで通信を中断しない。
  const final = (await (await finalRead).json()) as {
    read_kind: string
    prefix_ref: { length: string }
    after: { stateFields: Record<string, string> }
  }
  expect(final.read_kind).toBe('lineup-prefix')
  expect(final.prefix_ref.length).toBe('2')
  expect(final.after.stateFields['state.count.balls']).toBe('2')
  const reloadedRead = page.waitForResponse(
    async (response) =>
      response.request().method() === 'GET' &&
      path(response.url()) === `/api/games/${gameId}/started` &&
      response.status() === 200 &&
      (await response.json()).prefix_ref?.length === '2',
  )
  await page.reload()
  expect(
    (await (await reloadedRead).json()).after.stateFields['state.count.balls'],
  ).toBe('2')
  await expect(page.getByTestId('ordinary-local-balls')).toHaveText('2')
  console.log('PITCHLOG_OFFLINE_RECORDING_GAME_ID=' + gameId)
})
