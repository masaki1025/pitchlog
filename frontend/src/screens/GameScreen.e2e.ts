import {
  expect,
  test,
  type Page,
  type Request,
  type Response,
  type Route,
} from '@playwright/test'
import { readGameScreenE2eRuntime } from './GameScreenE2eSupport'

const uncertaintyText =
  '認証状態を確認できません。状態を再確認するか、ログアウトしてやり直してください。'

function isResponse(
  response: Response,
  method: string,
  pathname: string,
): boolean {
  return isRequest(response.request(), method, pathname)
}

function isRequest(
  request: Request,
  method: string,
  pathname: string,
): boolean {
  return (
    request.method() === method && new URL(request.url()).pathname === pathname
  )
}

function isGetResponse(response: Response, pathname: string): boolean {
  return isResponse(response, 'GET', pathname)
}

function pathname(page: Page): string {
  return new URL(page.url()).pathname
}

function diagnosticPath(value: string): string {
  return value
    .replace(/\/games\/[^/]+\/record(?=\/|$)/g, '/games/:id/record')
    .replace(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi,
      ':id',
    )
}

function observeSafeTraffic(page: Page): {
  report: () => Promise<string>
  stop: () => void
} {
  type Entry = {
    method: string
    pathname: string
    status: number | 'failed' | 'pending'
    elapsedMs: number
  }
  const start = performance.now()
  const pending = new Map<Request, Omit<Entry, 'status'>>()
  const completed: Entry[] = []
  const route = (request: Request): Omit<Entry, 'status'> | null => {
    const url = new URL(request.url())
    if (url.protocol !== 'https:' || url.hostname !== '127.0.0.1') return null
    return {
      method: request.method(),
      pathname: diagnosticPath(url.pathname),
      elapsedMs: Math.round(performance.now() - start),
    }
  }
  const onRequest = (request: Request): void => {
    const entry = route(request)
    if (entry) pending.set(request, entry)
  }
  const onResponse = (response: Response): void => {
    const request = response.request()
    const entry = pending.get(request) ?? route(request)
    pending.delete(request)
    if (entry) {
      completed.push({
        ...entry,
        status: response.status(),
        elapsedMs: Math.round(performance.now() - start),
      })
      if (completed.length > 80) completed.shift()
    }
  }
  const onFailed = (request: Request): void => {
    const entry = pending.get(request) ?? route(request)
    pending.delete(request)
    if (entry) {
      completed.push({
        ...entry,
        status: 'failed',
        elapsedMs: Math.round(performance.now() - start),
      })
      if (completed.length > 80) completed.shift()
    }
  }
  page.on('request', onRequest)
  page.on('response', onResponse)
  page.on('requestfailed', onFailed)
  return {
    async report(): Promise<string> {
      const form = page.locator('form[aria-busy]')
      const uncertainty = page.getByRole('alert').filter({
        hasText: uncertaintyText,
      })
      const safe = async <T>(
        read: () => Promise<T>,
        fallback: T,
      ): Promise<T> => {
        try {
          return await read()
        } catch {
          return fallback
        }
      }
      return JSON.stringify({
        elapsedMs: Math.round(performance.now() - start),
        ui: {
          pathname: diagnosticPath(pathname(page)),
          formBusy: await safe(
            () => form.getAttribute('aria-busy', { timeout: 300 }),
            null,
          ),
          uncertainty: await safe(() => uncertainty.isVisible(), false),
          reverify: await safe(
            () =>
              page.getByRole('button', { name: '状態を再確認' }).isVisible(),
            false,
          ),
          team: await safe(
            () =>
              page.getByRole('heading', { name: 'チーム・選手' }).isVisible(),
            false,
          ),
        },
        completed,
        pending: [...pending.values()].map((entry) => ({
          ...entry,
          status: 'pending',
          elapsedMs: Math.round(performance.now() - start) - entry.elapsedMs,
        })),
      })
    },
    stop(): void {
      page.off('request', onRequest)
      page.off('response', onResponse)
      page.off('requestfailed', onFailed)
    },
  }
}

async function requireTenantResponse(
  response: Response | null,
  tenantId: string,
): Promise<void> {
  if (!response || response.status() !== 200)
    throw new Error('実認証応答が200ではない')
  const body: unknown = await response.json()
  if (
    typeof body !== 'object' ||
    body === null ||
    !('tenant_id' in body) ||
    body.tenant_id !== tenantId
  )
    throw new Error('実認証応答のtenantが一致しない')
}

function watchInitialRosterRequests(
  page: Page,
  finalSessionSeen: () => boolean,
): {
  teamStart: Promise<Request | null>
  team: Promise<Response | null>
  players: Promise<Request | null>
} {
  let finalTeamRequest: Request | null = null
  let teamResponseSeen = false
  const teamStart = page
    .waitForRequest((request) => {
      if (
        !finalSessionSeen() ||
        !isRequest(request, 'GET', '/api/team-records')
      )
        return false
      finalTeamRequest = request
      return true
    })
    .catch(() => null)
  const team = page
    .waitForResponse((response) => {
      if (finalTeamRequest === null || response.request() !== finalTeamRequest)
        return false
      teamResponseSeen = true
      return true
    })
    .catch(() => null)
  const players = page
    .waitForRequest(
      (request) =>
        teamResponseSeen && isRequest(request, 'GET', '/api/players'),
    )
    .catch(() => null)
  return { teamStart, team, players }
}

async function requireInitialRosterReady(
  page: Page,
  requests: ReturnType<typeof watchInitialRosterRequests>,
  opponentName: string,
): Promise<void> {
  if (!(await requests.teamStart))
    throw new Error('最終認証後の実チーム一覧GETがない')
  const teamResponse = await requests.team
  if (!teamResponse || teamResponse.status() !== 200)
    throw new Error('実チーム一覧GETが200ではない')
  if (teamResponse.headers()['x-pitchlog-tenant-match'] !== '1')
    throw new Error('実チーム一覧GETのtenant照合がない')
  if ((await teamResponse.finished()) !== null)
    throw new Error('実チーム一覧GETが完了しない')
  let teamBody: unknown
  try {
    teamBody = await teamResponse.json()
  } catch {
    throw new Error('実チーム一覧応答の読取に失敗')
  }
  const records =
    typeof teamBody === 'object' &&
    teamBody !== null &&
    'items' in teamBody &&
    Array.isArray(teamBody.items)
      ? teamBody.items
      : null
  const opponent = records?.find(
    (record: unknown) =>
      typeof record === 'object' &&
      record !== null &&
      'kind' in record &&
      record.kind === 'opponent' &&
      'name' in record &&
      record.name === opponentName,
  ) as { id?: unknown } | undefined
  if (typeof opponent?.id !== 'string')
    throw new Error('現在tenantの対戦相手を実チーム一覧で確認できない')

  const playersRequest = await requests.players
  if (
    !playersRequest ||
    new URL(playersRequest.url()).searchParams.get('team_record_id') !==
      opponent.id
  )
    throw new Error('選択中の対戦相手に対応する実選手GETがない')
  const playersResponse = await playersRequest.response().catch(() => null)
  if (!playersResponse || playersResponse.status() !== 200)
    throw new Error('実選手GETが200ではない')
  if (playersResponse.headers()['x-pitchlog-tenant-match'] !== '1')
    throw new Error('実選手GETのtenant照合がない')
  if ((await playersResponse.finished()) !== null)
    throw new Error('実選手GETが完了しない')
  let playersBody: unknown
  try {
    playersBody = await playersResponse.json()
  } catch {
    throw new Error('実選手一覧応答の読取に失敗')
  }
  if (
    typeof playersBody !== 'object' ||
    playersBody === null ||
    !('items' in playersBody) ||
    !Array.isArray(playersBody.items) ||
    playersBody.items.length !== 0
  )
    throw new Error('専用fixtureの選手一覧読取結果が一致しない')
  await expect(page.getByText('チームを読み込んでいます。')).toBeHidden()
  await expect
    .poll(() =>
      page
        .getByTestId('team-record-list')
        .locator('button[aria-pressed="true"]')
        .getByText(opponentName, { exact: true })
        .isVisible(),
    )
    .toBe(true)
  await expect
    .poll(() => page.getByRole('heading', { name: opponentName }).isVisible())
    .toBe(true)
  await expect(page.getByText('選手を読み込んでいます。')).toBeHidden()
  await expect(page.getByText('登録済みの選手はいません。')).toBeVisible()
  if (pathname(page) !== '/team') throw new Error('実team画面に到達しない')
  // 初期認証に連動した読取が静まってから、別の保護経路へ移る。
  await page.waitForLoadState('networkidle')
}

async function requireNoHorizontalOverflow(page: Page): Promise<void> {
  const width = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }))
  expect(width.document).toBe(width.viewport)
}

test.afterEach(async ({ context }) => {
  // 失敗時の自動画面snapshotへ使い捨て認証主体を残さない。
  for (const page of context.pages()) {
    if (!page.isClosed()) await page.close()
  }
})

async function login(page: Page, index = 0): Promise<void> {
  const runtime = readGameScreenE2eRuntime()
  const identity = runtime.identities[index]
  if (!identity) throw new Error('使い捨て DB の認証 fixture がない')
  const traffic = observeSafeTraffic(page)
  let phase = 'initial-auth-bootstrap'
  try {
    await page.goto(`${runtime.baseURL}/login`)
    const form = page.locator('form[aria-busy]')
    const teamInput = page.getByRole('textbox', { name: 'チーム名' })
    const passwordInput = page.getByLabel('パスワード')
    await expect(form).toBeVisible()
    await expect(form).toHaveAttribute('aria-busy', 'false')
    await expect(teamInput).toBeEnabled()
    await expect(passwordInput).toBeEnabled()

    phase = 'explicit-login-post'
    await teamInput.fill(identity.name)
    await passwordInput.fill(identity.password)
    const submit = page.getByRole('button', { name: 'ログイン' })
    await expect(submit).toBeEnabled()
    // 待機は失敗時にpageを閉じても未処理rejectionを出さない。
    let loginPostSeen = false
    let sessionGetSeen = false
    const post = page
      .waitForResponse((response) => {
        if (!isResponse(response, 'POST', '/api/auth/login')) return false
        loginPostSeen = true
        return true
      })
      .catch(() => null)
    const verify = page
      .waitForResponse((response) => {
        if (!loginPostSeen || !isGetResponse(response, '/api/auth/session'))
          return false
        sessionGetSeen = true
        return true
      })
      .catch(() => null)
    const initialRoster = watchInitialRosterRequests(page, () => sessionGetSeen)
    await submit.click()
    await requireTenantResponse(await post, identity.tenantId)
    phase = 'correlated-session-get'
    const verified = await verify
    if (verified?.status() === 200)
      await requireTenantResponse(verified, identity.tenantId)

    phase = 'auth-ui-outcome'
    const teamHeading = page.getByRole('heading', { name: 'チーム・選手' })
    const uncertainty = page.getByRole('alert').filter({
      hasText: uncertaintyText,
    })
    await expect(teamHeading.or(uncertainty)).toBeVisible()
    let finalRoster = initialRoster
    if (await uncertainty.isVisible()) {
      phase = 'explicit-session-reverification'
      const reverify = page.getByRole('button', { name: '状態を再確認' })
      await expect(reverify).toBeEnabled()
      let manualSessionSeen = false
      const manualGet = page
        .waitForResponse((response) => {
          if (!isGetResponse(response, '/api/auth/session')) return false
          manualSessionSeen = true
          return true
        })
        .catch(() => null)
      finalRoster = watchInitialRosterRequests(page, () => manualSessionSeen)
      await reverify.click()
      await requireTenantResponse(await manualGet, identity.tenantId)
      await expect(teamHeading).toBeVisible()
    } else if (!verified || verified.status() !== 200) {
      throw new Error('相関した実session GETの成功がない')
    }

    phase = 'team-and-players-initial-read'
    await requireInitialRosterReady(page, finalRoster, identity.name)
    const cookies = await page.context().cookies(runtime.baseURL)
    if (!cookies.some((cookie) => cookie.secure && cookie.httpOnly))
      throw new Error('SecureかつHttpOnlyの実Cookieがない')
    if (!(await page.evaluate(() => window.isSecureContext)))
      throw new Error('実ブラウザがsecure contextではない')
  } catch {
    throw new Error(`login ${phase}: ${await traffic.report()}`)
  } finally {
    traffic.stop()
  }
}

test('認証なし・失効時に実 App の保護 route が開かない', async ({ page }) => {
  const { baseURL } = readGameScreenE2eRuntime()
  const traffic = observeSafeTraffic(page)
  try {
    await page.goto(`${baseURL}/games`)
    await expect(page.locator('form[aria-busy]')).toBeVisible()
    await expect(page.locator('form[aria-busy]')).toHaveAttribute(
      'aria-busy',
      'false',
    )
    if (pathname(page) !== '/login')
      throw new Error('匿名の実Appがloginへ遷移しない')
  } catch {
    throw new Error(`anonymous-auth-bootstrap: ${await traffic.report()}`)
  } finally {
    traffic.stop()
  }
  await login(page)
  const cookie = (await page.context().cookies(baseURL)).find(
    (value) => value.secure && value.httpOnly,
  )
  if (!cookie) throw new Error('製品認証 Cookie を取得できない')
  const logoutStatus = await page.evaluate(async () => {
    const response = await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Pitchlog-Request': '1' },
    })
    await response.text()
    return response.status
  })
  expect(logoutStatus).toBe(200)
  // 実 logout が失効させた旧提示値を再提示し、サーバーの拒否を確認する。
  await page.context().addCookies([cookie])
  const rejected = page
    .waitForResponse((response) => isGetResponse(response, '/api/auth/session'))
    .catch(() => null)
  await page.goto(`${baseURL}/games`)
  expect((await rejected)?.status()).toBe(401)
  await expect.poll(() => pathname(page)).toBe('/login')
})

test('実認証で封鎖された一覧と正規 ID の記録入口を表示する', async ({
  page,
}) => {
  const { baseURL } = readGameScreenE2eRuntime()
  await login(page)
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto(`${baseURL}/games`)
  await expect(
    page.getByRole('heading', { name: '試合', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: '試合を開始（未提供）' }),
  ).toBeDisabled()
  await expect(
    page.getByRole('button', { name: 'スタメンを確認・設定（未提供）' }),
  ).toBeDisabled()
  await requireNoHorizontalOverflow(page)
  await expect(
    page.getByRole('region', { name: '記録開始前提' }),
  ).toContainText('前提1')
  await page.reload()
  await expect(
    page.getByRole('button', { name: '試合を開始（未提供）' }),
  ).toBeDisabled()
  await page.goto(
    `${baseURL}/games/00000000-0000-4000-8000-000000000001/record`,
  )
  await expect(
    page.getByRole('button', { name: '記録を再開（未提供）' }),
  ).toBeDisabled()
  await expect(page.getByRole('button', { name: '1球を確定' })).toBeDisabled()
  await expect(page.getByText('記録内容は未取得です。')).toBeVisible()
  await requireNoHorizontalOverflow(page)
  await page.setViewportSize({ width: 320, height: 700 })
  await requireNoHorizontalOverflow(page)
})

test('未知・不正 ID、複数タブ、認証通信失敗を封鎖する', async ({
  page,
  context,
}) => {
  const { baseURL } = readGameScreenE2eRuntime()
  await login(page)
  await page.goto(`${baseURL}/games/not-a-uuid/record`)
  await expect(page.getByText('試合IDが正しくありません。')).toBeVisible()
  const other = await context.newPage()
  await other.goto(
    `${baseURL}/games/00000000-0000-4000-8000-000000000002/record`,
  )
  await expect(
    other.getByRole('button', { name: '記録を再開（未提供）' }),
  ).toBeDisabled()
  await other.route('**/api/auth/session', async (route) => route.abort())
  await other.reload()
  await expect.poll(() => pathname(other)).toBe('/login')
  await other.close()
})

test('認証応答の遅延後も封鎖状態で表示する', async ({ page }) => {
  const { baseURL } = readGameScreenE2eRuntime()
  await login(page)
  await page.goto(`${baseURL}/games`)
  const startButton = page.getByRole('button', { name: '試合を開始（未提供）' })
  await expect(startButton).toBeDisabled()

  let releaseResponse: () => void = () => {}
  const heldResponse = new Promise<void>((resolve) => {
    releaseResponse = resolve
  })
  let requested = false
  const delaySession = async (route: Route): Promise<void> => {
    requested = true
    await heldResponse
    await route.continue()
  }
  await page.route('**/api/auth/session', delaySession)
  let delayedResponse: Response | undefined
  try {
    await page.reload({ waitUntil: 'commit' })
    await expect.poll(() => requested).toBe(true)
    await expect(startButton).toHaveCount(0)
    const response = page.waitForResponse((value) =>
      isGetResponse(value, '/api/auth/session'),
    )
    releaseResponse()
    delayedResponse = await response
  } finally {
    releaseResponse()
    await page.unroute('**/api/auth/session', delaySession)
  }
  const identity = readGameScreenE2eRuntime().identities[0]
  if (!identity) throw new Error('使い捨てDBの認証fixtureがない')
  await requireTenantResponse(delayedResponse ?? null, identity.tenantId)

  const uncertainty = page
    .getByRole('alert')
    .filter({ hasText: uncertaintyText })
  await expect(startButton.or(uncertainty)).toBeVisible()
  if (await uncertainty.isVisible()) {
    await expect.poll(() => pathname(page)).toBe('/login')
    await expect(startButton).toHaveCount(0)
    let manualSessionSeen = false
    const sessionResponse = page
      .waitForResponse((response) => {
        if (!isGetResponse(response, '/api/auth/session')) return false
        manualSessionSeen = true
        return true
      })
      .catch(() => null)
    const finalRoster = watchInitialRosterRequests(
      page,
      () => manualSessionSeen,
    )
    await page.getByRole('button', { name: '状態を再確認' }).click()
    await requireTenantResponse(await sessionResponse, identity.tenantId)
    await requireInitialRosterReady(page, finalRoster, identity.name)
    await page.goto(`${baseURL}/games`)
  }
  await expect.poll(() => pathname(page)).toBe('/games')
  await expect(startButton).toBeDisabled()
})

test('tenant の変更後も旧画面から記録を開始しない', async ({
  page,
  context,
}) => {
  const { baseURL, identities } = readGameScreenE2eRuntime()
  await login(page)
  const first = identities[0]
  const second = identities[1]
  if (!first || !second) throw new Error('二つの使い捨て認証fixtureがない')
  await expect
    .poll(() =>
      page
        .getByTestId('team-record-list')
        .getByText(first.name, { exact: true })
        .isVisible(),
    )
    .toBe(true)
  await page.goto(`${baseURL}/games`)
  await context.clearCookies()
  await login(page, 1)
  await expect
    .poll(() =>
      page
        .getByTestId('team-record-list')
        .getByText(second.name, { exact: true })
        .isVisible(),
    )
    .toBe(true)
  await expect
    .poll(
      async () =>
        (await page.getByText(first.name, { exact: true }).count()) === 0,
    )
    .toBe(true)
  await page.goto(`${baseURL}/games`)
  await expect(
    page.getByRole('button', { name: '試合を開始（未提供）' }),
  ).toBeDisabled()
})
