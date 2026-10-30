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
async function login(page: Page): Promise<string> {
  await page.goto(`${baseURL}/login?redirect=/games`)
  await expect(page.locator('form[aria-busy]')).toHaveAttribute(
    'aria-busy',
    'false',
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

test('実HTTPS画面で新規作成・開始・初球ボール保存・同要求再送・reloadを通す', async ({
  page,
}) => {
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('初球縦断には実HTTPS originが必要です')
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window)
    let recorded: { url: string; init: RequestInit } | undefined
    // 実fetchは変更せず、既要求の再送に必要な原値だけをブラウザ内closureへ保持する。
    window.fetch = async (input, init) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url
      if (
        init?.method === 'POST' &&
        /\/games\/[^/]+\/sync\/events$/.test(
          new URL(url, location.href).pathname,
        )
      ) {
        if (typeof init.body !== 'string')
          throw new Error('同期本文が文字列ではありません')
        recorded = {
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
    Object.defineProperty(window, '__repeatFirstBallForTest', {
      value: async () => {
        if (!recorded) throw new Error('既送信の初球要求がありません')
        const response = await nativeFetch(recorded.url, recorded.init)
        return response.status
      },
    })
  })

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
  // 開始後の実サーバー再取得で復元入口が出たら、実UIから再取得する。
  const initialRead = page.waitForResponse(
    (res) =>
      res.request().method() === 'GET' &&
      apiPath(res.url()) === `/api/games/${saved.id}/started` &&
      res.status() === 200,
  )
  await page
    .getByRole('button', { name: /^サーバーから(?:復元|再取得)$/ })
    .click()
  const view = (await (await initialRead).json()) as {
    read_kind: string
    id: string
    state: { stateFields: Record<string, unknown>; scoreboard: unknown }
  }
  await expect(
    page.getByText('開始済み（記録前）', { exact: true }),
  ).toBeVisible()
  await expect(page.getByTestId('first-ball-pitch-type')).toBeVisible()
  expect(view.read_kind).toBe('initial')
  expect(view.id).toBe(saved.id)
  expect(view.state.stateFields['state.count.balls']).toBe('0')

  expect(
    await page.evaluate(
      () =>
        window.isSecureContext &&
        window.top === window &&
        location.protocol === 'https:',
    ),
  ).toBe(true)
  for (const id of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${id}`).check()
  const pitchType = page.getByTestId('first-ball-pitch-type')
  await expect(pitchType).toBeEnabled()
  // 実tenant GETが供給した先頭の選択肢をUIで選ぶ。fixture keyを指定しない。
  await expect(pitchType.locator('option')).not.toHaveCount(1)
  await pitchType.selectOption({ index: 1 })
  await page.getByTestId('first-ball-course').locator('svg').click()
  const synchronized = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
  )
  const restored = page.waitForResponse(
    async (res) =>
      res.request().method() === 'GET' &&
      apiPath(res.url()) === `/api/games/${saved.id}/started` &&
      res.status() === 200 &&
      (await res.json()).read_kind === 'recorded',
  )
  // この初球限定画面では、結果の選択と確定をボール専用ボタンで行う。
  await page.getByTestId('first-ball-save').click()
  expect((await synchronized).status()).toBe(200)
  const recorded = (await (await restored).json()) as {
    read_kind: string
    history: unknown[]
    play_rows: unknown[]
    after: { stateFields: Record<string, unknown>; scoreboard: unknown }
  }
  expect(recorded.read_kind).toBe('recorded')
  expect(recorded.history).toHaveLength(1)
  expect(recorded.play_rows).toHaveLength(1)
  expect(recorded.after.stateFields).toStrictEqual({
    ...view.state.stateFields,
    'state.count.balls': '1',
  })
  expect(recorded.after.scoreboard).toStrictEqual(view.state.scoreboard)
  await expect(page.getByTestId('restore-balls')).toHaveText('1')
  await expect(page.getByTestId('restore-strikes')).toHaveText('0')
  await expect(page.getByTestId('restore-history')).toHaveText('1件')
  const replayStatus = await page.evaluate(async () => {
    const repeat = (
      window as unknown as { __repeatFirstBallForTest: () => Promise<number> }
    ).__repeatFirstBallForTest
    return repeat()
  })
  expect(replayStatus).toBe(200)
  const reloadRead = page.waitForResponse(
    (res) =>
      res.request().method() === 'GET' &&
      apiPath(res.url()) === `/api/games/${saved.id}/started` &&
      res.status() === 200,
  )
  await page.reload()
  const reloaded = (await (await reloadRead).json()) as typeof recorded
  expect(reloaded.read_kind).toBe('recorded')
  expect(reloaded.after).toStrictEqual(recorded.after)
  expect(reloaded.history).toHaveLength(1)
  expect(reloaded.play_rows).toHaveLength(1)
  await expect(page.getByTestId('restore-balls')).toHaveText('1')
  await expect(page.getByTestId('restore-strikes')).toHaveText('0')
  await expect(page.getByTestId('restore-history')).toHaveText('1件')
  console.log('PITCHLOG_FIRST_BALL_GAME_ID=' + saved.id)
})
