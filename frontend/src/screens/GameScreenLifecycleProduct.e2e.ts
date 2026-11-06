import { createHash } from 'node:crypto'
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
async function login(page: Page, redirect = '/games'): Promise<string> {
  await page.goto(`${baseURL}/login?redirect=${encodeURIComponent(redirect)}`)
  await expect(page.locator('form[aria-busy]')).toHaveAttribute(
    'aria-busy',
    'false',
    { timeout: 30_000 },
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

test('実画面の新規作成→開始→1球→終了→再開→2球→再終了→reload', async ({
  page,
}) => {
  const syncDurationsMs: number[] = []
  page.on('requestfailed', (request) => {
    if (new URL(request.url()).origin === baseURL)
      console.log(
        'PITCHLOG_LIFECYCLE_TRANSPORT_FAILURE=' +
          JSON.stringify({
            method: request.method(),
            path: apiPath(request.url()),
            failure: request.failure()?.errorText ?? 'unknown',
          }),
      )
  })
  page.on('pageerror', (error) => {
    console.log(
      'PITCHLOG_LIFECYCLE_PAGE_ERROR=' +
        JSON.stringify({
          type: error.name,
          moduleLoadFailed: error.message.includes(
            'dynamically imported module',
          ),
          initializationFailed: error.message.includes('before initialization'),
          isSyntaxError: error instanceof SyntaxError,
        }),
    )
  })
  page.on('response', (response) => {
    if (apiPath(response.url()).endsWith('/sync/events'))
      console.log(
        'PITCHLOG_LIFECYCLE_TRANSPORT_RESPONSE=' +
          JSON.stringify({
            method: response.request().method(),
            http: response.status(),
          }),
      )
  })

  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame())
      console.log(
        'PITCHLOG_LIFECYCLE_PAGE_PATH=' + new URL(frame.url()).pathname,
      )
  })
  page.on('response', (response) => {
    const path = apiPath(response.url())
    if (path.startsWith('/api/') && response.request().method() === 'GET')
      console.log(
        'PITCHLOG_LIFECYCLE_READ_RESPONSE=' +
          JSON.stringify({
            route: path.endsWith('/started')
              ? 'started'
              : path.endsWith('/preparing')
                ? 'preparing'
                : path === '/api/auth/session'
                  ? 'session'
                  : 'other',
            http: response.status(),
          }),
      )
  })
  page.on('response', (response) => {
    const url = new URL(response.url())
    if (
      url.searchParams.get('projection') !== 'lifecycle-prefix-v1' ||
      response.status() !== 200
    )
      return
    void response
      .json()
      .then(async (value: unknown) => {
        if (value === null || typeof value !== 'object') return
        const row = value as Record<string, unknown>
        const validation = await page.evaluate(async (packet) => {
          const lifecycleUrl = '/src/api/gameLifecycle.ts'
          const nativeUrl = '/src/api/nativeUndoGame.ts'
          const life = await import(lifecycleUrl)
          const native = await import(nativeUrl)
          const { status, lifecycle, ...prefix } = packet as Record<
            string,
            unknown
          >
          return {
            full: life.isGameLifecycleGame(packet),
            metadata: life.isGameLifecycleMeta(lifecycle, status),
            prefix: native.isNativeUndoGame({
              ...prefix,
              status: 'in_progress',
            }),
          }
        }, value)
        const meta =
          row.lifecycle !== null && typeof row.lifecycle === 'object'
            ? (row.lifecycle as Record<string, unknown>)
            : {}
        console.log(
          'PITCHLOG_LIFECYCLE_DTO=' +
            JSON.stringify({
              readKind: row.read_kind,
              profile: row.profile,
              status: row.status,
              lastVersion: meta.lastVersion,
              format: meta.formatVersion,
              validation,
            }),
        )
      })
      .catch(() => console.log('PITCHLOG_LIFECYCLE_DTO=unavailable'))
  })
  page.on('console', (message) => {
    if (message.text().startsWith('PITCHLOG_LIFECYCLE_CLIENT_STAGE='))
      console.log(message.text())
  })
  page.setDefaultTimeout(30_000)
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('実HTTPSが必要です')
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
  await form.getByLabel('新しい大会名', { exact: true }).fill('画面作成大会')
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
  console.log('PITCHLOG_LIFECYCLE_ATTEMPT_GAME=' + saved.id)
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

  const requests: Array<{
    bodySha256: string
    attemptSha256: string
    kind: string
  }> = []
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      apiPath(request.url()) === `/api/games/${saved.id}/sync/events`
    ) {
      const raw = request.postData(),
        attempt = request.headers()['x-pitchlog-sync-attempt']
      if (!raw || !attempt) throw new Error('実要求識別が不足')
      const body = JSON.parse(raw)
      requests.push({
        bodySha256: createHash('sha256').update(raw).digest('hex'),
        attemptSha256: createHash('sha256').update(attempt).digest('hex'),
        kind: body.events[0]?.event_kind,
      })
    }
  })
  await page
    .getByRole('button', {
      name: '三振・攻守交代を含む投球の記録へ',
      exact: true,
    })
    .click()
  for (let n = 1; n <= 1; n++) {
    await expect(page.getByTestId('ordinary-state-source')).toHaveText(
      'サーバー確認済みの状態',
    )
    for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
      await page.getByTestId(`first-ball-env-${name}`).check()
    await page
      .getByTestId('ordinary-pitch-result')
      .selectOption('batting-result.ball')
    const pitch = page.getByTestId('first-ball-pitch-type')
    await expect(pitch.locator('option')).not.toHaveCount(1)
    await pitch.selectOption({ index: 1 })
    await page.getByTestId('first-ball-course').locator('svg').click()
    const syncStarted = Date.now()
    const posted = page
      .waitForResponse(
        (res) =>
          res.request().method() === 'POST' &&
          apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
        { timeout: 30_000 },
      )
      .catch(() => null)
    await page.getByTestId('first-ball-save').click()
    const response = await posted
    syncDurationsMs.push(Date.now() - syncStarted)
    console.log(
      'PITCHLOG_LIFECYCLE_ORDINARY_HTTP=' +
        JSON.stringify({
          pitch: n,
          postedRequests: requests.length,
          locks: await page.evaluate(async () => {
            if (!navigator.locks) return null
            const snapshot = await navigator.locks.query()
            return {
              held: snapshot.held?.length ?? 0,
              pending: snapshot.pending?.length ?? 0,
            }
          }),
          http: response?.status() ?? null,
          status: await page
            .getByTestId('first-ball-status')
            .evaluateAll((elements) => elements[0]?.textContent ?? 'unmounted'),
        }),
    )
    expect(response).not.toBeNull()
    expect(response!.status()).toBe(200)
    const ack = await response!.json()
    const a5 = ack.eventResults?.[0]?.a5Result
    console.log(
      'PITCHLOG_LIFECYCLE_ORDINARY_ACK=' +
        JSON.stringify({
          pitch: n,
          a5: ['受理', '重複', '拒否', '退避', '未処理'].includes(a5)
            ? a5
            : 'unexpected',
          d3: Number.isSafeInteger(ack.advancedD3) ? ack.advancedD3 : null,
        }),
    )
    expect(a5).toBe('受理')
    await expect(page.getByTestId('restore-history')).toHaveText(`${n}件`)
  }
  const lifecycle = page.getByTestId('lifecycle-product')
  await lifecycle.getByTestId('lifecycle-refresh').click()
  for (const box of await lifecycle.locator('input[type=checkbox]').all())
    await box.check()
  await expect(lifecycle.getByTestId('lifecycle-status')).toHaveText('進行中')
  async function lifecycleOperation(
    kind: 'end' | 'reopen',
    expectedStatus: string,
  ) {
    const posted = page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
      { timeout: 30_000 },
    )
    await lifecycle.getByTestId(`lifecycle-${kind}`).click()
    const response = await posted
    expect(response.status()).toBe(200)
    const ack = await response.json()
    expect(ack.eventResults?.[0]?.a5Result).toBe('受理')
    try {
      await expect(
        lifecycle.getByTestId('lifecycle-confirmed-status'),
      ).toHaveText(expectedStatus, { timeout: 30_000 })
    } catch (error) {
      const diagnostics: Record<string, string | null> = {}
      for (const name of [
        'status',
        'confirmed-status',
        'last-version',
        'failure',
        'blocked-reason',
        'save-ack',
        'refresh-state',
      ])
        diagnostics[name] = await lifecycle
          .getByTestId(`lifecycle-${name}`)
          .evaluateAll((elements) => elements[0]?.textContent ?? null)
      console.log('PITCHLOG_LIFECYCLE_VIEW=' + JSON.stringify(diagnostics))
      throw error
    }
  }
  await lifecycleOperation('end', '終了')
  await expect(lifecycle.getByTestId('lifecycle-last-version')).toContainText(
    '1',
  )
  await lifecycleOperation('reopen', '進行中')
  await lifecycle.getByTestId('lifecycle-resume').click()
  const input = page.getByTestId('undo-product-panel')
  await input.getByTestId('undo-product-reload').click()
  await expect(input.getByTestId('undo-product-balls')).toHaveText('1', {
    timeout: 30_000,
  })
  for (const box of await input.locator('input[type=checkbox]').all())
    await box.check()
  for (const balls of [2, 3]) {
    const pitch = input.getByTestId('undo-product-pitch-type')
    await expect(pitch.locator('option')).not.toHaveCount(1)
    await pitch.selectOption({ index: 1 })
    await input.getByTestId('undo-product-course').locator('svg').click()
    const posted = page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
      { timeout: 30_000 },
    )
    await input.getByTestId('undo-product-ball').click()
    const response = await posted
    expect(response.status()).toBe(200)
    expect((await response.json()).eventResults?.[0]?.a5Result).toBe('受理')
    await expect(input.getByTestId('undo-product-balls')).toHaveText(
      String(balls),
      { timeout: 30_000 },
    )
  }
  await lifecycle.getByTestId('lifecycle-refresh').click()
  await lifecycleOperation('end', '終了')
  await expect(lifecycle.getByTestId('lifecycle-last-version')).toContainText(
    '2',
  )
  await page.reload()
  await expect(lifecycle.getByTestId('lifecycle-confirmed-status')).toHaveText(
    '終了',
    { timeout: 30_000 },
  )
  await expect(lifecycle.getByTestId('lifecycle-last-version')).toContainText(
    '2',
  )
  expect(requests).toHaveLength(6)
  // 初回投球の性能判定は機能待機とは独立して維持する。
  expect(syncDurationsMs.every((elapsed) => elapsed <= 5000)).toBe(true)
  console.log(
    'PITCHLOG_LIFECYCLE_FINAL=' +
      JSON.stringify({
        gameId: saved.id,
        requests: requests.length,
        balls: 3,
        version: 2,
      }),
  )
})
