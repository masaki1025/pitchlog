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

test('実HTTPS画面で三振3PA・攻守交代・相手側球・元D5・ACK喪失reloadを通す', async ({
  page,
}) => {
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('初球縦断には実HTTPS originが必要です')
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window)
    let loseNext = false
    Object.defineProperty(window, '__loseLineupAckOnce', {
      value: () => {
        loseNext = true
      },
    })
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
      const response = await nativeFetch(input, init)
      if (
        loseNext &&
        init?.method === 'POST' &&
        /\/sync\/events$/.test(new URL(url, location.href).pathname)
      ) {
        loseNext = false
        throw new TypeError('test-only lost ACK after real response')
      }
      return response
    }
    Object.defineProperty(window, '__repeatLineupForTest', {
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
  const requests: Array<{ bodySha256: string; attemptSha256: string }> = []
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      apiPath(request.url()) === `/api/games/${saved.id}/sync/events`
    ) {
      const body = request.postData(),
        attempt = request.headers()['x-pitchlog-sync-attempt']
      if (body === null || !attempt)
        throw new Error('同期の原要求/attempt識別値が不足')
      requests.push({
        bodySha256: createHash('sha256').update(body).digest('hex'),
        attemptSha256: createHash('sha256').update(attempt).digest('hex'),
      })
    }
  })
  const readHead = (n: string) =>
    page.waitForResponse(
      async (res) =>
        res.request().method() === 'GET' &&
        apiPath(res.url()) === `/api/games/${saved.id}/started` &&
        res.status() === 200 &&
        (await res.json()).read_kind === 'lineup-prefix' &&
        (await res.json()).prefix_ref.length === n,
    )
  const zeroRead = readHead('0')
  await page
    .getByRole('button', {
      name: '三振・攻守交代を含む投球の記録へ',
      exact: true,
    })
    .click()
  const zero = await (await zeroRead).json()
  expect(zero.after.battingOrderBySide).toEqual({ away: '1', home: '1' })
  async function selectAndSave(result: string, loseAck = false) {
    await expect(page.getByTestId('ordinary-pitch-result')).toBeVisible()
    for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
      await page.getByTestId(`first-ball-env-${name}`).check()
    const pitch = page.getByTestId('first-ball-pitch-type')
    await expect(pitch).toBeEnabled()
    await expect(pitch.locator('option')).not.toHaveCount(1)
    await pitch.selectOption({ index: 1 })
    await page.getByTestId('ordinary-pitch-result').selectOption(result)
    await page.getByTestId('first-ball-course').locator('svg').click()
    if (loseAck)
      await page.evaluate(() => {
        ;(
          window as unknown as { __loseLineupAckOnce: () => void }
        ).__loseLineupAckOnce()
      })
    const posted = page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
    )
    await page.getByTestId('first-ball-save').click()
    expect((await posted).status()).toBe(200)
  }
  for (let n = 1; n <= 9; n++) {
    const read = readHead(String(n))
    await selectAndSave(
      n % 3 === 0
        ? 'batting-result.called-strikeout'
        : 'batting-result.called-pitch',
    )
    const head = await (await read).json()
    expect(head.page.items).toHaveLength(n)
    await expect(page.getByTestId('restore-history')).toHaveText(`${n}件`)
    if (n === 9) {
      expect(head.after.stateFields['state.half']).toBe('bottom')
      expect(head.after.stateFields['state.outs']).toBe('0')
      expect(head.after.battingOrderBySide).toEqual({ away: '4', home: '1' })
      expect(head.lineup).toEqual(zero.lineup)
      expect(head.participants.pitcherId).toBe(zero.lineup.away.pitcherId)
      expect(head.participants.catcherId).toBe(zero.lineup.away.catcherId)
      expect(head.participants.batterId).toBe(
        zero.lineup.home.battingOrder['1'],
      )
    }
  }
  expect(
    await page.evaluate(async () => {
      return (
        window as unknown as { __repeatLineupForTest: () => Promise<number> }
      ).__repeatLineupForTest()
    }),
  ).toBe(200)
  await selectAndSave('batting-result.ball', true)
  await expect(page.getByTestId('first-ball-retry')).toBeVisible()
  const original = requests.at(-1)!
  const reloaded = readHead('10')
  await page.reload()
  const tenth = await (await reloaded).json()
  expect(tenth.after.stateFields['state.count.balls']).toBe('1')
  expect(tenth.after.battingOrderBySide).toEqual({ away: '4', home: '1' })
  await expect(page.getByTestId('first-ball-retry')).toBeVisible()
  for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${name}`).check()
  const retried = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
  )
  const finalRead = readHead('10')
  await page.getByTestId('first-ball-retry').click()
  expect((await retried).status()).toBe(200)
  const final = await (await finalRead).json()
  expect(requests.at(-1)).toEqual(original)
  expect(final.after).toEqual(tenth.after)
  expect(final.prefix_ref).toEqual(tenth.prefix_ref)
  expect(final.page.items).toHaveLength(10)
  expect(final.last_entry).toEqual(tenth.last_entry)
  console.log('PITCHLOG_LINEUP_GAME_ID=' + saved.id)
})
