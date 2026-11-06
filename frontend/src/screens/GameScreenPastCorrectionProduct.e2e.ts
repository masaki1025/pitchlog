import { createHash } from 'node:crypto'
import {
  expect,
  test,
  type Page,
  type Response as PlaywrightResponse,
} from '@playwright/test'
import type { P3ChangeBody } from '../api/pastCorrectionProduct'
import type { LineupPrefixGame } from '../api/lineupPrefixGame'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const away = process.env.PITCHLOG_E2E_AWAY_TEAM
const home = process.env.PITCHLOG_E2E_HOME_TEAM
if (!baseURL || !team || !password || !away || !home)
  throw new Error('P3実画面資格がenvにありません')

function apiPath(url: string): string {
  return new URL(url).pathname
}

async function finishedWithin(
  response: PlaywrightResponse,
): Promise<'finished' | 'failed' | 'timeout'> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      response
        .finished()
        .then((error) =>
          error === null ? ('finished' as const) : ('failed' as const),
        ),
      new Promise<'timeout'>((resolve) => {
        timer = setTimeout(() => resolve('timeout'), 30_000)
      }),
    ])
  } finally {
    clearTimeout(timer)
  }
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

test('真正HTTPS画面で三球の末尾過去訂正、同要求再掲、再読込を通す', async ({
  page,
}) => {
  test.setTimeout(480_000)
  page.setDefaultTimeout(30_000)
  const startedAt = Date.now()
  const stage = (name: string) =>
    console.log(
      'PITCHLOG_P3_STAGE=' +
        JSON.stringify({ name, elapsedMs: Date.now() - startedAt }),
    )
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('実HTTPSが必要です')
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window)
    let captured: { url: string; init: RequestInit } | null = null
    window.fetch = async (input, init) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url
      if (
        init?.method === 'POST' &&
        /\/games\/[^/]+\/sync\/change$/.test(
          new URL(url, location.href).pathname,
        )
      ) {
        captured = {
          url,
          init: {
            ...init,
            headers: new Headers(init.headers),
            body: init.body,
          },
        }
      }
      return nativeFetch(input, init)
    }
    Object.defineProperty(window, '__repeatP3Original', {
      value: async () => {
        if (!captured) throw new Error('P3原要求がありません')
        const response = await nativeFetch(captured.url, captured.init)
        return response.status
      },
    })
  })
  await login(page)
  stage('login')
  await page.getByRole('button', { name: '新規作成', exact: true }).click()
  const form = page.getByRole('region', { name: '試合の新規作成', exact: true })
  await form.getByLabel('日時（日本時間）').fill('2026-11-07T10:00')
  await form.getByTestId('game-type').selectOption('game_other')
  await form.getByTestId('away').selectOption(away!)
  await form.getByTestId('home').selectOption(home!)
  await form.getByTestId('tournament-kind').selectOption('new')
  await form
    .getByLabel('新しい大会名', { exact: true })
    .fill('過去球訂正画面試験大会')
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
  stage('created')
  await form
    .getByRole('button', { name: '作成した試合IDの保存値を確認', exact: true })
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
      apiPath(res.url()) === `/api/games/${saved.id}/start`,
  )
  await page.getByRole('button', { name: '試合を開始', exact: true }).click()
  expect((await started).status()).toBe(200)
  stage('started')
  await expect(page).toHaveURL(/\/record\?recording=play-prefix-v3/)
  await expect(page.getByTestId('ordinary-state-source')).toHaveText(
    'サーバー確認済みの状態',
  )
  for (let number = 1; number <= 3; number++) {
    for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
      await page.getByTestId(`first-ball-env-${name}`).check()
    await page.getByTestId('first-ball-pitch-type').selectOption({ index: 1 })
    await page
      .getByTestId('ordinary-pitch-result')
      .selectOption(
        number === 3
          ? 'batting-result.called-strikeout'
          : 'batting-result.called-pitch',
      )
    await page.getByTestId('first-ball-course').locator('svg').click()
    const posted = page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
    )
    await page.getByTestId('first-ball-save').click()
    expect((await posted).status()).toBe(200)
    await expect(page.getByTestId('restore-history')).toHaveText(`${number}件`)
    stage(`pitch-${number}`)
    if (number === 1) {
      const early = page.getByRole('region', { name: '過去の投球を訂正' })
      await expect(early).toBeVisible()
      for (const box of await early.locator('input[type=checkbox]').all())
        await box.check()
      await early.getByTestId('p3-target').selectOption('1')
      const probe = page.waitForResponse(
        (res) =>
          res.request().method() === 'GET' &&
          apiPath(res.url()) === `/api/games/${saved.id}/sync/change-target/1`,
      )
      await early.getByTestId('p3-inspect').click()
      const response = await probe
      expect(response.status()).toBe(200)
      stage('early-target-headers')
      expect(await finishedWithin(response)).toBe('finished')
      await expect(
        early.getByText('対象版 1、元結果 batting-result.called-pitch'),
      ).toBeVisible()
      stage('early-target-ready')
    }
  }
  const panel = page.getByRole('region', { name: '過去の投球を訂正' })
  await expect(panel).toBeVisible()
  for (const box of await panel.locator('input[type=checkbox]').all())
    await box.check()
  await panel.getByTestId('p3-target').selectOption('3')
  const targetRead = page.waitForResponse(
    (res) =>
      res.request().method() === 'GET' &&
      apiPath(res.url()) === `/api/games/${saved.id}/sync/change-target/3`,
  )
  await panel.getByTestId('p3-inspect').click()
  const targetResponse = await targetRead
  expect(targetResponse.status()).toBe(200)
  stage('target-headers')
  const targetBody = await finishedWithin(targetResponse)
  expect(targetBody).toBe('finished')
  await expect(
    panel.getByText('対象版 1、元結果 batting-result.called-strikeout'),
  ).toBeVisible()
  stage('target-ready')
  await panel.getByTestId('p3-result').selectOption('batting-result.ball')
  await panel.getByTestId('p3-pitch-type').selectOption({ index: 1 })
  await panel.locator('svg[aria-label^="ストライクゾーン"]').click()
  for (const box of await panel.locator('input[type=checkbox]').all())
    await box.check()
  const requests: Array<{ body: string; attempt: string }> = []
  const diagnostic: {
    submittedBody: P3ChangeBody | null
    postHeadersSeen: boolean
    afterRead: Promise<LineupPrefixGame | null> | null
  } = { submittedBody: null, postHeadersSeen: false, afterRead: null }
  page.on('response', (response) => {
    if (
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${saved.id}/sync/change`
    )
      diagnostic.postHeadersSeen = true
    if (response.request().method() !== 'GET') return
    const path = apiPath(response.url())
    if (path === `/api/games/${saved.id}/started`) {
      stage(`current-get-${response.status()}`)
      if (diagnostic.postHeadersSeen && diagnostic.afterRead === null)
        diagnostic.afterRead = response
          .json()
          .then((value) => value as LineupPrefixGame)
          .catch(() => null)
    }
    if (path === `/api/games/${saved.id}/stats`)
      stage(`stats-get-${response.status()}`)
    if (path === `/api/games/${saved.id}/sync/change-confirmation/3`)
      stage(`confirmation-get-${response.status()}`)
  })
  page.on('request', (request) => {
    if (
      request.method() !== 'POST' ||
      apiPath(request.url()) !== `/api/games/${saved.id}/sync/change`
    )
      return
    const body = request.postData(),
      attempt = request.headers()['x-pitchlog-sync-attempt']
    if (!body || !attempt) throw new Error('P3原要求がありません')
    diagnostic.submittedBody = JSON.parse(body) as P3ChangeBody
    requests.push({
      body: createHash('sha256').update(body).digest('hex'),
      attempt: createHash('sha256').update(attempt).digest('hex'),
    })
  })
  const posted = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${saved.id}/sync/change`,
  )
  await expect(panel.getByTestId('p3-apply')).toBeEnabled()
  await panel.getByTestId('p3-apply').click()
  const applied = await posted
  expect(applied.status()).toBe(200)
  expect((await applied.json()).boundary).toBe('変更受理')
  stage('p3-accepted')
  expect(requests).toHaveLength(1)
  await expect(panel.getByTestId('p3-status')).toHaveText(
    /訂正を保存し、再取得と現行成績を確認しました。|受理結果は端末へ保存しました。再取得が未完了です。/,
    { timeout: 30000 },
  )
  const read = diagnostic.afterRead === null ? null : await diagnostic.afterRead
  const submitted = diagnostic.submittedBody
  const target =
    read && submitted
      ? read.page.items[submitted.change.target_reference.d1 - 1]?.play_row
      : null
  console.log(
    'PITCHLOG_P3_READ_PREDICATES=' +
      JSON.stringify({
        read: read !== null,
        target: target !== null && target !== undefined,
        idChanged:
          !!target && !!submitted &&
          target.id !== submitted.change.payload.targetPlayId,
        sourceChanged:
          !!target && !!submitted &&
          target.source_event_id !== submitted.change.payload.targetEventId,
        resultMatched:
          !!target && !!submitted &&
          target.batting_result_key === submitted.change.payload.replacementResultId,
        headChanged:
          !!read && !!submitted &&
          JSON.stringify(read.prefix_ref) !==
            JSON.stringify(submitted.change.payload.expectedPrefixRef),
        checkpointIdChanged:
          !!read && !!submitted &&
          read.prefix_ref.checkpoint.id !==
            submitted.change.payload.expectedPrefixRef.checkpoint.id,
        checkpointDigestChanged:
          !!read && !!submitted &&
          read.prefix_ref.checkpoint.digest !==
            submitted.change.payload.expectedPrefixRef.checkpoint.digest,
        revisionUnchanged:
          !!read && !!submitted &&
          BigInt(read.prefix_ref.checkpoint.revision) ===
            BigInt(submitted.change.payload.expectedPrefixRef.checkpoint.revision),
        afterBall:
          read?.after.stateFields['state.count.balls'] === '1',
        afterStrikes:
          read?.after.stateFields['state.count.strikes'] === '2',
      }),
  )
  await expect(panel.getByTestId('p3-status')).toHaveText(
    '訂正を保存し、再取得と現行成績を確認しました。',
  )
  stage('p3-screen-saved')
  await expect(page.getByTestId('restore-balls')).toHaveText('1')
  await expect(page.getByTestId('restore-strikes')).toHaveText('2')
  stage('p3-refreshed')
  expect(
    await page.evaluate(async () =>
      (
        window as unknown as { __repeatP3Original: () => Promise<number> }
      ).__repeatP3Original(),
    ),
  ).toBe(200)
  stage('p3-replayed')
  await page.reload()
  await expect(page.getByTestId('restore-balls')).toHaveText('1')
  await expect(page.getByTestId('restore-strikes')).toHaveText('2')
  stage('p3-reloaded')
  console.log(
    'PITCHLOG_P3_SCREEN=' +
      JSON.stringify({ gameId: saved.id, accepted: 1, replayStatus: 200 }),
  )
})
