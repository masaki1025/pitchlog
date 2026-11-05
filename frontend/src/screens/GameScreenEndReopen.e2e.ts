import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const away = process.env.PITCHLOG_E2E_AWAY_TEAM
const home = process.env.PITCHLOG_E2E_HOME_TEAM
const otherTeam = process.env.PITCHLOG_E2E_OTHER_TEAM
const otherTenant = process.env.PITCHLOG_E2E_OTHER_TENANT
if (
  !baseURL ||
  !team ||
  !password ||
  !away ||
  !home ||
  !otherTeam ||
  !otherTenant
)
  throw new Error('E2Eの実app資格がenvにない')

const httpTimeout = 30_000
function apiPath(url: string): string {
  return new URL(url).pathname
}

type AckBody = Readonly<{
  eventResults: readonly Readonly<{
    a5Result: '受理' | '重複' | '拒否' | '退避' | '未処理'
  }>[]
}>

async function login(page: Page): Promise<string> {
  await page.goto(`${baseURL}/login?redirect=/games`, { timeout: httpTimeout })
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
    { timeout: httpTimeout },
  )
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
  const response = await posted
  expect(response.status()).toBe(200)
  const body = (await response.json()) as { tenant_id?: unknown }
  if (typeof body.tenant_id !== 'string')
    throw new Error('login応答のtenantがない')
  return body.tenant_id
}

test('実HTTPS画面の9回制非同時点で終了→再送→再開→再終了→reload', async ({
  page,
}) => {
  page.setDefaultTimeout(httpTimeout)
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('実HTTPS originが必要')
  const tenant = await login(page)
  const syncRequests: Array<{
    url: string
    body: string
    headers: Record<string, string>
  }> = []
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      apiPath(request.url()).endsWith('/sync/events')
    ) {
      syncRequests.push({
        url: request.url(),
        body: request.postData() ?? '',
        headers: request.headers(),
      })
    }
  })

  const faultHeaders = {
    Origin: baseURL!,
    'X-Pitchlog-Request': '1',
    'X-Pitchlog-Expected-Tenant': tenant,
    'X-Pitchlog-Tenant-Challenge': randomUUID(),
  }
  async function setFault(point: 'after_lifecycle_projection' | null) {
    const response = await page.request.post(
      `${baseURL}/api/spike/games/${saved.id}/lifecycle/fault`,
      { data: { point }, headers: faultHeaders },
    )
    expect(response.status()).toBe(200)
  }

  await page.getByRole('button', { name: '新規作成', exact: true }).click()
  const form = page.getByRole('region', {
    name: '試合の新規作成',
    exact: true,
  })
  await expect(form.getByLabel('日時（日本時間）')).toBeEnabled()
  await form.getByLabel('日時（日本時間）').fill('2026-11-05T10:00')
  await form.getByTestId('game-type').selectOption('game_other')
  await form.getByTestId('away').selectOption(away!)
  await form.getByTestId('home').selectOption(home!)
  await form.getByTestId('tournament-kind').selectOption('new')
  await form
    .getByLabel('新しい大会名', { exact: true })
    .fill('画面終了再開大会-' + Date.now())
  const created = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' && apiPath(res.url()) === '/api/games',
    { timeout: httpTimeout },
  )
  await form
    .getByRole('button', { name: '準備中の試合を作成', exact: true })
    .click()
  const createdResponse = await created
  expect(createdResponse.status()).toBe(201)
  const saved = (await createdResponse.json()) as {
    id: string
    status: string
    applied_rules: { dh: boolean; regulationInnings: number }
  }
  expect(saved.status).toBe('preparing')
  expect(saved.applied_rules.regulationInnings).toBe(9)
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
    { timeout: httpTimeout },
  )
  await page.getByRole('button', { name: '試合を開始', exact: true }).click()
  expect((await started).status()).toBe(200)

  const readHead = (length: string) =>
    page.waitForResponse(
      async (response) =>
        response.request().method() === 'GET' &&
        apiPath(response.url()) === `/api/games/${saved.id}/started` &&
        response.status() === 200 &&
        (await response.json()).read_kind === 'lineup-prefix' &&
        (await response.json()).prefix_ref.length === length,
      { timeout: 240_000 },
    )
  const zeroRead = readHead('0')
  await page
    .getByRole('button', {
      name: '三振・攻守交代を含む投球の記録へ',
      exact: true,
    })
    .click()
  const zero = (await (await zeroRead).json()) as {
    after: { stateFields: Record<string, unknown> }
    roster: {
      teams: Array<{
        side: string
        participants: Array<{
          player: { player_id: string }
          roles: Array<{ kind: string; position?: string }>
        }>
      }>
    }
  }
  const fielding = zero.roster.teams.find((t) => t.side === 'home')
  const fielder = fielding?.participants.find((p) =>
    p.roles.some((r) => r.kind === 'fielding' && r.position === '9'),
  )
  if (!fielder) throw new Error('実守備rosterに位置9の野手がない')

  await expect(page.getByTestId('ordinary-state-source')).toHaveText(
    'サーバー確認済みの状態',
  )
  for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${name}`).check()
  const pitch = page.getByTestId('first-ball-pitch-type')
  await expect(pitch).toBeEnabled()
  await expect(pitch.locator('option')).not.toHaveCount(1)
  await pitch.selectOption('u06-first-ball-fastball')
  await page
    .getByTestId('ordinary-pitch-result')
    .selectOption('batting-result.home-run')
  await page.getByTestId('first-ball-course').locator('svg').click()
  for (const key of [
    'typeKey',
    'strengthKey',
    'hitX',
    'hitY',
    'rawFielderPosition',
    'resolvedFielderId',
  ])
    await page.getByTestId(`batted-mode-${key}`).selectOption('unobserved')
  for (const key of ['scoring', 'interference', 'overrides', 'thirdOut'])
    await page
      .getByTestId('batted-hit-observation')
      .locator(`[data-question-key="${key}"] select`)
      .selectOption('confirmed')
  const hitRead = readHead('1')
  const hitPosted = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${saved.id}/sync/events`,
    { timeout: httpTimeout },
  )
  await expect(page.getByTestId('first-ball-save')).toBeEnabled()
  await page.getByTestId('first-ball-save').click()
  const hitResponse = await hitPosted
  expect(hitResponse.status()).toBe(200)
  expect(
    ((await hitResponse.json()) as AckBody).eventResults[0]!.a5Result,
  ).toBe('受理')
  const first = (await (await hitRead).json()) as {
    after: { stateFields: Record<string, unknown> }
  }
  expect(first.after.stateFields['state.score']).toEqual({
    home: '0',
    away: '1',
  })

  await page.goto(`${baseURL}/games/${saved.id}/lifecycle-spike`, {
    timeout: httpTimeout,
  })
  await expect(page.getByTestId('lifecycle-screen')).toBeVisible()
  await expect(page.getByTestId('lifecycle-status')).toHaveText('進行中', {
    timeout: 120_000,
  })
  await expect(page.getByTestId('lifecycle-watermark')).toHaveText('1')
  await expect(page.getByTestId('lifecycle-version')).toHaveText('なし')

  // 投影後の故障で終了イベント全体がロールバックし、水位が進まないことを見る。
  await setFault('after_lifecycle_projection')
  const failedEnd = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${saved.id}/sync/events`,
    { timeout: httpTimeout },
  )
  await page.getByTestId('lifecycle-end').click()
  const failedStatus = (await failedEnd).status()
  expect([500, 503]).toContain(failedStatus)
  await page.getByTestId('lifecycle-refresh').click()
  await expect(page.getByTestId('lifecycle-status')).toHaveText('進行中')
  await expect(page.getByTestId('lifecycle-watermark')).toHaveText('1')
  await setFault(null)

  const endPosted = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${saved.id}/sync/events`,
    { timeout: httpTimeout },
  )
  await page.getByTestId('lifecycle-end').click()
  const endResponse = await endPosted
  expect(endResponse.status()).toBe(200)
  expect(
    ((await endResponse.json()) as AckBody).eventResults[0]!.a5Result,
  ).toBe('受理')
  await expect(page.getByTestId('lifecycle-status')).toHaveText('終了確定')
  await expect(page.getByTestId('lifecycle-version')).toHaveText('v1')
  await expect(page.getByTestId('lifecycle-watermark')).toHaveText('2')
  await expect(page.getByTestId('lifecycle-finalizations')).toContainText(
    'v1（D1 2）: 有効',
  )

  // 同じ D5・同じ本文・同じ attempt の再送は重複で、水位を進めない。
  const originalEnd = syncRequests.at(-1)
  if (!originalEnd) throw new Error('再送対象の終了要求がない')
  const replayHeaders = Object.fromEntries(
    Object.entries(originalEnd.headers).filter(
      ([name]) => !['cookie', 'content-length', 'host'].includes(name),
    ),
  )
  const duplicateResponse = await page.request.post(originalEnd.url, {
    data: originalEnd.body,
    headers: { ...replayHeaders, Origin: baseURL! },
  })
  expect(duplicateResponse.status()).toBe(200)
  const duplicateBody = (await duplicateResponse.json()) as AckBody
  expect(duplicateBody.eventResults[0]!.a5Result).toBe('重複')
  await page.getByTestId('lifecycle-refresh').click()
  await expect(page.getByTestId('lifecycle-watermark')).toHaveText('2')

  const reopenPosted = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${saved.id}/sync/events`,
    { timeout: httpTimeout },
  )
  await page.getByTestId('lifecycle-reopen').click()
  const reopenResponse = await reopenPosted
  expect(reopenResponse.status()).toBe(200)
  expect(
    ((await reopenResponse.json()) as AckBody).eventResults[0]!.a5Result,
  ).toBe('受理')
  await expect(page.getByTestId('lifecycle-status')).toHaveText('進行中')
  await expect(page.getByTestId('lifecycle-watermark')).toHaveText('3')
  await expect(page.getByTestId('lifecycle-version')).toHaveText('なし')
  await expect(page.getByTestId('lifecycle-finalizations')).toContainText(
    'v1（D1 2）: 再開 D1 3 で失効',
  )
  await expect(page.getByTestId('lifecycle-reopen-gap')).toBeVisible()

  // 再開後の追記は製品 prefix 境界が未接続のため、ここでは成功を主張しない。
  const reendPosted = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${saved.id}/sync/events`,
    { timeout: httpTimeout },
  )
  await page.getByTestId('lifecycle-end').click()
  const reendResponse = await reendPosted
  expect(reendResponse.status()).toBe(200)
  expect(
    ((await reendResponse.json()) as AckBody).eventResults[0]!.a5Result,
  ).toBe('受理')
  await expect(page.getByTestId('lifecycle-status')).toHaveText('終了確定')
  await expect(page.getByTestId('lifecycle-version')).toHaveText('v2')
  await expect(page.getByTestId('lifecycle-watermark')).toHaveText('4')
  await expect(page.getByTestId('lifecycle-finalizations')).toContainText(
    'v2（D1 4）: 有効',
  )

  // reload 後も専用GETから同じ終了確定版を読む。
  await page.reload({ timeout: httpTimeout })
  await expect(page.getByTestId('lifecycle-status')).toHaveText('終了確定', {
    timeout: 120_000,
  })
  await expect(page.getByTestId('lifecycle-version')).toHaveText('v2')
  await expect(page.getByTestId('lifecycle-watermark')).toHaveText('4')
  await expect(page.getByTestId('lifecycle-finalizations')).toContainText(
    'v1（D1 2）: 再開 D1 3 で失効',
  )

  // V12 を改竄した終了は保存されず、水位が変わらない。
  const bad = JSON.parse(originalEnd.body) as {
    recording_right_proof: string
    events: Array<{
      d5: string
      d1: number
      d2: number
      payload: {
        finalization: { version: number; previous: unknown }
      }
    }>
  }
  bad.recording_right_proof = bad.recording_right_proof + 'x'
  bad.events[0]!.d5 = randomUUID()
  bad.events[0]!.d1 = 5
  bad.events[0]!.d2 = 5001
  bad.events[0]!.payload.finalization.version = 3
  bad.events[0]!.payload.finalization.previous = { version: 2, d1: 4 }
  const badV12 = await page.request.post(originalEnd.url, {
    data: JSON.stringify(bad),
    headers: {
      ...replayHeaders,
      Origin: baseURL!,
      'X-Pitchlog-Sync-Attempt': randomUUID(),
    },
  })
  const badV12Status = badV12.status()
  expect(badV12Status).toBe(200)
  const badBody = (await badV12.json()) as AckBody
  expect(badBody.eventResults[0]!.a5Result).toBe('退避')
  await page.getByTestId('lifecycle-refresh').click()
  await expect(page.getByTestId('lifecycle-watermark')).toHaveText('4')

  // 別tenantの実loginでは、同じ試合IDの専用GETが404になる。
  const otherLogin = await page.request.post(`${baseURL}/api/auth/login`, {
    data: { team_name: otherTeam, password },
    headers: { Origin: baseURL!, 'X-Pitchlog-Request': '1' },
  })
  expect(otherLogin.status()).toBe(200)
  const otherBody = (await otherLogin.json()) as { tenant_id?: unknown }
  expect(otherBody.tenant_id).toBe(otherTenant)
  const otherRead = await page.request.get(
    `${baseURL}/api/spike/games/${saved.id}/lifecycle`,
    {
      headers: {
        Origin: baseURL!,
        'X-Pitchlog-Expected-Tenant': otherTenant!,
        'X-Pitchlog-Tenant-Challenge': randomUUID(),
      },
    },
  )
  expect(otherRead.status()).toBe(404)
  const otherFault = await page.request.post(
    `${baseURL}/api/spike/games/${saved.id}/lifecycle/fault`,
    {
      data: { point: 'after_lifecycle_projection' },
      headers: {
        Origin: baseURL!,
        'X-Pitchlog-Request': '1',
        'X-Pitchlog-Expected-Tenant': otherTenant!,
        'X-Pitchlog-Tenant-Challenge': randomUUID(),
      },
    },
  )
  expect(otherFault.status()).toBe(404)

  console.log(
    'PITCHLOG_LIFECYCLE_SCREEN_RESULT=' +
      JSON.stringify({
        game: saved.id,
        score: first.after.stateFields['state.score'],
        end: { status: endResponse.status(), a5: '受理', watermark: 2 },
        fault: { status: failedStatus, watermarkAfter: '1' },
        duplicate: { status: duplicateResponse.status(), a5: '重複' },
        reopen: { status: reopenResponse.status(), a5: '受理', watermark: 3 },
        reend: { status: reendResponse.status(), a5: '受理', watermark: 4 },
        finalVersion: 'v2',
        finalWatermark: '4',
        finalizations: [
          { version: 1, d1: 2, invalidatedBy: { d1: 3 } },
          { version: 2, d1: 4, invalidatedBy: null },
        ],
        reloaded: { status: 'finished', version: 'v2', watermark: '4' },
        badV12: {
          status: badV12Status,
          a5: '退避',
          d5: bad.events[0]!.d5,
          watermarkAfter: '4',
        },
        otherTenantStatus: otherRead.status(),
        otherTenantFaultStatus: otherFault.status(),
      }),
  )
})
