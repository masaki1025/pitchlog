import { createHash } from 'node:crypto'
import { writeFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const away = process.env.PITCHLOG_E2E_AWAY_TEAM
const home = process.env.PITCHLOG_E2E_HOME_TEAM
const resultFile = process.env.PITCHLOG_E2E_RESULT_FILE
if (!baseURL || !team || !password || !away || !home)
  throw new Error('E2Eの実app資格がenvにない')

function apiPath(url: string): string {
  return new URL(url).pathname
}
const httpTimeout = 30_000
type HistoryItem = {
  play_row: Record<string, unknown>
  play_runners: Array<Record<string, unknown>>
  history_entry: unknown
}
type Runner = {
  runnerId: string
  responsiblePitcherId: string
  base: string
  status: string
  statusSource: string
}
type Head = {
  read_kind: string
  after: {
    stateFields: Record<string, unknown>
    scoreboard: Record<string, unknown>
    battingOrderBySide: { away: string; home: string }
  }
  prefix_ref: { length: string }
  runners: Runner[]
  lineup: {
    away: { battingOrder: Record<string, string> }
    home: { pitcherId: string }
  }
  roster: {
    teams: Array<{
      side: string
      participants: Array<{
        player: { player_id: string }
        roles: Array<{ kind: string; position?: string }>
      }>
    }>
  }
  page: { items: HistoryItem[] }
  last_entry: unknown
}

async function login(page: Page, name: string = team!): Promise<void> {
  await page.goto(`${baseURL}/login?redirect=/games`, { timeout: httpTimeout })
  await expect(page.locator('form[aria-busy]')).toHaveAttribute(
    'aria-busy',
    'false',
  )
  await page.getByRole('textbox', { name: 'チーム名' }).fill(name)
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
}

type StartedGame = {
  id: string
  status: string
  applied_rules: { dh: boolean }
}
async function createGame(page: Page, label: string): Promise<StartedGame> {
  await page.getByRole('button', { name: '新しい試合', exact: true }).click()
  const form = page.getByRole('region', {
    name: '試合の新規作成',
    exact: true,
  })
  await expect(form.getByLabel('日時（日本時間）')).toBeEnabled()
  await form.getByLabel('日時（日本時間）').fill('2026-11-06T10:00')
  await form.getByTestId('game-type').selectOption('game_other')
  await form.getByTestId('away').selectOption(away!)
  await form.getByTestId('home').selectOption(home!)
  await form.getByTestId('tournament-kind').selectOption('new')
  await form
    .getByLabel('新しい大会名', { exact: true })
    .fill('申告敬遠大会-' + label)
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
  const saved = (await createdResponse.json()) as StartedGame
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
  return saved
}

function readHead(page: Page, gameId: string, length: string) {
  return page.waitForResponse(
    async (response) =>
      response.request().method() === 'GET' &&
      apiPath(response.url()) === `/api/games/${gameId}/started` &&
      response.status() === 200 &&
      (await response.json()).read_kind === 'lineup-prefix' &&
      (await response.json()).prefix_ref.length === length,
    { timeout: httpTimeout },
  )
}

async function selectPitch(
  page: Page,
  result: string,
  fielderId: string,
  runnerDestination: 'hold' | '2' | '3' | '4' | null,
) {
  await expect(page.getByTestId('ordinary-state-source')).toHaveText(
    'サーバー確認済み',
  )
  for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${name}`).check()
  const pitch = page.getByTestId('first-ball-pitch-type')
  await expect(pitch).toBeEnabled()
  await expect(pitch.locator('option')).not.toHaveCount(1)
  await pitch.selectOption('u06-first-ball-fastball')
  await page.getByTestId('ordinary-pitch-result').selectOption(result)
  await page.getByTestId('first-ball-course').locator('svg').click()
  for (const [key, value] of [
    ['typeKey', 'batted.screen.line'],
    ['strengthKey', 'batted.screen.hard'],
    ['hitX', '0.25'],
    ['hitY', '0.75'],
    ['rawFielderPosition', '9'],
    ['resolvedFielderId', fielderId],
  ] as const) {
    await page.getByTestId(`batted-mode-${key}`).selectOption('observed')
    const input = page.getByTestId(`batted-value-${key}`)
    if (
      key === 'typeKey' ||
      key === 'strengthKey' ||
      key === 'resolvedFielderId'
    )
      await input.selectOption(value)
    else await input.fill(value)
  }
  if (runnerDestination !== null) {
    await page
      .getByTestId('batted-runner-1-destination')
      .selectOption(runnerDestination)
    await page.getByTestId('batted-runner-confirmed').check()
  }
  for (const key of ['scoring', 'interference', 'overrides', 'thirdOut'])
    await page
      .getByTestId('batted-hit-observation')
      .locator(`[data-question-key="${key}"] select`)
      .selectOption('confirmed')
}
async function save(page: Page, gameId: string) {
  const posted = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${gameId}/sync/events`,
    { timeout: httpTimeout },
  )
  await expect(page.getByTestId('first-ball-save')).toBeEnabled()
  await page.getByTestId('first-ball-save').click()
  const response = await posted
  const result = (await response.json()) as {
    eventResults?: Array<{ a5Result: string }>
  }
  expect(response.status(), JSON.stringify(result)).toBe(200)
  expect(result.eventResults?.[0]?.a5Result).toBe('受理')
}

test('実画面の一三塁から申告敬遠を非投球として保存し次球と再読取へ接続する', async ({
  page,
}) => {
  page.setDefaultTimeout(httpTimeout)
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window)
    let original: { url: string; init: RequestInit } | undefined
    window.fetch = async (input, init) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url
      if (
        original === undefined &&
        init?.method === 'POST' &&
        /\/games\/[^/]+\/sync\/events$/.test(
          new URL(url, location.href).pathname,
        ) &&
        typeof init.body === 'string' &&
        init.body.includes('intentional-walk')
      ) {
        original = {
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
    Object.defineProperty(window, '__repeatIntentionalWalkForTest', {
      value: async () => {
        if (!original) throw new Error('申告敬遠の原同期本文がない')
        const response = await nativeFetch(original.url, {
          ...original.init,
          signal: AbortSignal.timeout(30_000),
        })
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
  const game = await createGame(page, 'A')
  const requests: Array<{ body: string; attempt: string }> = []
  page.on('request', (request) => {
    if (
      request.method() !== 'POST' ||
      apiPath(request.url()) !== `/api/games/${game.id}/sync/events` ||
      !request.postData()?.includes('intentional-walk')
    )
      return
    const body = request.postData()
    const attempt = request.headers()['x-pitchlog-sync-attempt']
    if (body === null || !attempt)
      throw new Error('申告敬遠の原本文/attemptがない')
    requests.push({
      body: createHash('sha256').update(body).digest('hex'),
      attempt: createHash('sha256').update(attempt).digest('hex'),
    })
  })
  const zeroRead = readHead(page, game.id, '0')
  // 現行の開始成功後は記録画面が同ゲームのv3入口へ自動遷移する。
  await page.waitForURL(
    `${baseURL}/games/${game.id}/record?recording=play-prefix-v3`,
  )
  const zero = (await (await zeroRead).json()) as Head
  const fielder = zero.roster.teams
    .find((team) => team.side === 'home')
    ?.participants.find((person) =>
      person.roles.some(
        (role) => role.kind === 'fielding' && role.position === '9',
      ),
    )
  if (!fielder) throw new Error('実守備rosterに位置9の野手がない')
  await selectPitch(
    page,
    'batting-result.single',
    fielder.player.player_id,
    null,
  )
  const firstRead = readHead(page, game.id, '1')
  await save(page, game.id)
  const first = (await (await firstRead).json()) as Head
  expect(first.after.stateFields['state.runners']).toBe('first')
  await selectPitch(
    page,
    'batting-result.single',
    fielder.player.player_id,
    '3',
  )
  const secondRead = readHead(page, game.id, '2')
  await save(page, game.id)
  const second = (await (await secondRead).json()) as Head
  expect(second.after.stateFields['state.runners']).toBe('first-third')
  expect(second.after.stateFields['state.count.balls']).toBe('0')
  expect(second.after.stateFields['state.count.strikes']).toBe('0')
  expect(second.after.stateFields['state.outs']).toBe('0')

  const button = page.getByTestId('nonpitch-intentional-walk')
  await expect(button).toBeEnabled()
  const posted = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${game.id}/sync/events`,
    { timeout: httpTimeout },
  )
  const thirdRead = readHead(page, game.id, '3')
  await button.click()
  const accepted = await posted
  const acceptedBody = (await accepted.json()) as {
    eventResults?: Array<{ a5Result: string }>
  }
  expect(accepted.status(), JSON.stringify(acceptedBody)).toBe(200)
  expect(acceptedBody.eventResults?.[0]?.a5Result).toBe('受理')
  const third = (await (await thirdRead).json()) as Head
  expect(third.page.items).toHaveLength(3)
  expect(third.after.stateFields['state.runners']).toBe('first-second-third')
  expect(third.after.stateFields['state.count.balls']).toBe('0')
  expect(third.after.stateFields['state.count.strikes']).toBe('0')
  expect(third.after.stateFields['state.outs']).toBe('0')
  expect(third.after.stateFields['state.score']).toEqual({
    home: '0',
    away: '0',
  })
  expect(third.after.scoreboard).toMatchObject({ walks: '1', hits: '2' })
  expect(third.page.items[2]?.play_row).toMatchObject({
    event_kind: 'non_pitch',
    batting_result_key: 'batting-result.intentional-walk',
    course: null,
    pitch_type_key: null,
  })
  expect(requests).toHaveLength(1)
  const original = { ...requests[0]! }
  const replayed = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${game.id}/sync/events`,
    { timeout: httpTimeout },
  )
  const replay = await page.evaluate(() =>
    (
      window as unknown as {
        __repeatIntentionalWalkForTest: () => Promise<{
          status: number
          body: { eventResults: Array<{ a5Result: string }> }
        }>
      }
    ).__repeatIntentionalWalkForTest(),
  )
  expect(replay.status).toBe(200)
  expect((await replayed).status()).toBe(200)
  expect(replay.body.eventResults[0]?.a5Result).toBe('重複')
  expect(requests).toHaveLength(2)
  expect(requests[1]).toEqual(original)

  await expect(page.getByTestId('ordinary-state-source')).toHaveText(
    'サーバー確認済み',
  )
  for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${name}`).check()
  const pitch = page.getByTestId('first-ball-pitch-type')
  await expect(pitch.locator('option')).not.toHaveCount(1)
  await pitch.selectOption('u06-first-ball-fastball')
  await page
    .getByTestId('ordinary-pitch-result')
    .selectOption('batting-result.ball')
  await page.getByTestId('first-ball-course').locator('svg').click()
  const fourthRead = readHead(page, game.id, '4')
  await save(page, game.id)
  const fourth = (await (await fourthRead).json()) as Head
  expect(fourth.after.stateFields['state.runners']).toBe('first-second-third')
  expect(fourth.after.stateFields['state.count.balls']).toBe('1')
  expect(fourth.page.items).toHaveLength(4)
  const restoredRead = readHead(page, game.id, '4')
  await page.reload({ timeout: httpTimeout })
  const restored = (await (await restoredRead).json()) as Head
  expect(restored.after).toEqual(fourth.after)
  expect(restored.page.items).toEqual(fourth.page.items)
  if (resultFile) writeFileSync(resultFile, game.id)
  console.log(
    'PITCHLOG_NONPITCH_SCREEN_RESULT=' +
      JSON.stringify({
        game: game.id,
        after: restored.after,
        rows: restored.page.items,
        runners: restored.runners,
      }),
  )
})
