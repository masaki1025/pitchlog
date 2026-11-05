import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const away = process.env.PITCHLOG_E2E_AWAY_TEAM
const home = process.env.PITCHLOG_E2E_HOME_TEAM
const otherTeam = process.env.PITCHLOG_E2E_OTHER_TEAM
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
  await page.getByRole('button', { name: '新規作成', exact: true }).click()
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
    .fill('走者安打大会-' + label)
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
    'サーバー確認済みの状態',
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
  expect(response.status()).toBe(200)
  expect((await response.json()).eventResults[0].a5Result).toBe('受理')
}

function requestRecorder(page: Page, gameId: string) {
  const requests: Array<{ body: string; attempt: string }> = []
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      apiPath(request.url()) === `/api/games/${gameId}/sync/events`
    ) {
      const body = request.postData(),
        attempt = request.headers()['x-pitchlog-sync-attempt']
      if (body === null || !attempt) throw new Error('同期の原要求が不足')
      requests.push({
        body: createHash('sha256').update(body).digest('hex'),
        attempt: createHash('sha256').update(attempt).digest('hex'),
      })
    }
  })
  return requests
}

function repeatWindow(page: Page) {
  return page.evaluate(() =>
    (
      window as unknown as {
        __repeatRunnerBattedForTest: () => Promise<{
          status: number
          body: { eventResults: Array<{ a5Result: string }> }
        }>
      }
    ).__repeatRunnerBattedForTest(),
  )
}

test('走者一塁の単打→三塁明示→再送→reload', async ({ page }) => {
  page.setDefaultTimeout(httpTimeout)
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window)
    let recorded: { url: string; init: RequestInit } | undefined
    window.fetch = async (input, init) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url
      if (
        recorded === undefined &&
        init?.method === 'POST' &&
        /\/games\/[^/]+\/sync\/events$/.test(
          new URL(url, location.href).pathname,
        ) &&
        typeof init.body === 'string' &&
        init.body.includes('"kind":"applied"')
      ) {
        if (typeof init.body !== 'string') throw new Error('原同期本文が不足')
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
    Object.defineProperty(window, '__repeatRunnerBattedForTest', {
      value: async () => {
        if (!recorded) throw new Error('再送対象の原要求がない')
        const response = await nativeFetch(recorded.url, {
          ...recorded.init,
          signal: AbortSignal.timeout(30_000),
        })
        const body = (await response.json()) as {
          eventResults: Array<{ a5Result: string }>
        }
        return { status: response.status, body }
      },
    })
  })
  await login(page)
  const saved = await createGame(page, 'A')
  const requests = requestRecorder(page, saved.id)
  const zeroRead = readHead(page, saved.id, '0')
  await page
    .getByRole('button', {
      name: '三振・攻守交代を含む投球の記録へ',
      exact: true,
    })
    .click()
  const zero = (await (await zeroRead).json()) as Head
  const fielder = zero.roster.teams
    .find((t) => t.side === 'home')
    ?.participants.find((p) =>
      p.roles.some((r) => r.kind === 'fielding' && r.position === '9'),
    )
  if (!fielder) throw new Error('実守備rosterに位置9の野手がない')
  await selectPitch(
    page,
    'batting-result.single',
    fielder.player.player_id,
    null,
  )
  const firstRead = readHead(page, saved.id, '1')
  await save(page, saved.id)
  const first = (await (await firstRead).json()) as Head
  expect(first.page.items).toHaveLength(1)
  expect(first.after.stateFields['state.runners']).toBe('first')
  expect(first.after.battingOrderBySide).toEqual({ away: '2', home: '1' })
  const firstBatter = zero.lineup.away.battingOrder['1']!
  expect(first.runners).toEqual([
    {
      runnerId: firstBatter,
      responsiblePitcherId: zero.lineup.home.pitcherId,
      base: '1',
      status: '継続',
      statusSource: 'auto',
    },
  ])
  await selectPitch(
    page,
    'batting-result.single',
    fielder.player.player_id,
    '3',
  )
  const secondRead = readHead(page, saved.id, '2')
  await save(page, saved.id)
  const second = (await (await secondRead).json()) as Head
  expect(second.page.items).toHaveLength(2)
  expect(second.page.items[0]).toEqual(first.page.items[0])
  expect(second.after.stateFields['state.runners']).toBe('first-third')
  expect(second.after.stateFields['state.count.balls']).toBe('0')
  expect(second.after.stateFields['state.count.strikes']).toBe('0')
  expect(second.after.stateFields['state.outs']).toBe('0')
  expect(second.after.stateFields['state.half']).toBe('top')
  expect(second.after.stateFields['state.inning']).toBe('1')
  expect(second.after.stateFields['state.score']).toEqual({
    home: '0',
    away: '0',
  })
  expect(second.after.scoreboard).toEqual({
    inningScores: { home: '0', away: '0' },
    hits: '2',
    errors: '0',
    strikeouts: '0',
    walks: '0',
  })
  expect(second.after.battingOrderBySide).toEqual({ away: '3', home: '1' })
  const secondBatter = zero.lineup.away.battingOrder['2']!
  expect(
    second.runners.slice().sort((a, b) => Number(a.base) - Number(b.base)),
  ).toEqual([
    {
      runnerId: secondBatter,
      responsiblePitcherId: zero.lineup.home.pitcherId,
      base: '1',
      status: '継続',
      statusSource: 'auto',
    },
    {
      runnerId: firstBatter,
      responsiblePitcherId: zero.lineup.home.pitcherId,
      base: '3',
      status: '継続',
      statusSource: 'auto',
    },
  ])
  const original = Object.freeze({ ...requests[1]! })
  const replay = await repeatWindow(page)
  expect(replay.status).toBe(200)
  expect(replay.body.eventResults[0]!.a5Result).toBe('重複')
  expect(requests).toHaveLength(3)
  expect(requests[1]).toEqual(original)
  expect(requests.at(-1)).toEqual(original)
  const restoredRead = readHead(page, saved.id, '2')
  await page.reload({ timeout: httpTimeout })
  const restored = (await (await restoredRead).json()) as Head
  expect(restored.after).toEqual(second.after)
  expect(restored.prefix_ref).toEqual(second.prefix_ref)
  expect(restored.page.items).toEqual(second.page.items)
  expect(restored.last_entry).toEqual(second.last_entry)
  expect(restored.runners).toEqual(second.runners)
  if (resultFile) writeFileSync(resultFile, saved.id)
  console.log(
    'PITCHLOG_RUNNER_SCREEN_RESULT=' +
      JSON.stringify({
        game: saved.id,
        scenario: 'single-first-to-third',
        rows: restored.page.items,
        after: restored.after,
        runners: restored.runners,
      }),
  )
})

test('走者一塁の二塁打→生還明示→得点1・打点1→reload', async ({ page }) => {
  page.setDefaultTimeout(httpTimeout)
  await login(page)
  const saved = await createGame(page, 'B')
  const zeroRead = readHead(page, saved.id, '0')
  await page
    .getByRole('button', {
      name: '三振・攻守交代を含む投球の記録へ',
      exact: true,
    })
    .click()
  const zero = (await (await zeroRead).json()) as Head
  const fielder = zero.roster.teams
    .find((t) => t.side === 'home')
    ?.participants.find((p) =>
      p.roles.some((r) => r.kind === 'fielding' && r.position === '9'),
    )
  if (!fielder) throw new Error('実守備rosterに位置9の野手がない')
  await selectPitch(
    page,
    'batting-result.single',
    fielder.player.player_id,
    null,
  )
  const firstRead = readHead(page, saved.id, '1')
  await save(page, saved.id)
  const first = (await (await firstRead).json()) as Head
  const firstBatter = zero.lineup.away.battingOrder['1']!
  expect(first.runners[0]?.runnerId).toBe(firstBatter)
  await selectPitch(
    page,
    'batting-result.double',
    fielder.player.player_id,
    '4',
  )
  const secondRead = readHead(page, saved.id, '2')
  await save(page, saved.id)
  const second = (await (await secondRead).json()) as Head
  expect(second.after.stateFields['state.runners']).toBe('second')
  expect(second.after.stateFields['state.score']).toEqual({
    home: '0',
    away: '1',
  })
  expect(second.after.scoreboard).toEqual({
    inningScores: { home: '0', away: '1' },
    hits: '2',
    errors: '0',
    strikeouts: '0',
    walks: '0',
  })
  expect(second.after.stateFields['state.outs']).toBe('0')
  expect(second.after.battingOrderBySide).toEqual({ away: '3', home: '1' })
  const secondBatter = zero.lineup.away.battingOrder['2']!
  expect(second.runners).toEqual([
    {
      runnerId: secondBatter,
      responsiblePitcherId: zero.lineup.home.pitcherId,
      base: '2',
      status: '継続',
      statusSource: 'auto',
    },
  ])
  const entry = second.last_entry as {
    difference: { statFlags: Record<string, boolean> }
  }
  expect(entry.difference.statFlags['得点']).toBe(true)
  expect(entry.difference.statFlags['打点']).toBe(true)
  const restoredRead = readHead(page, saved.id, '2')
  await page.reload({ timeout: httpTimeout })
  const restored = (await (await restoredRead).json()) as Head
  expect(restored.after).toEqual(second.after)
  expect(restored.page.items).toEqual(second.page.items)
  expect(restored.last_entry).toEqual(second.last_entry)
  expect(restored.runners).toEqual(second.runners)
  console.log(
    'PITCHLOG_RUNNER_SCREEN_RESULT=' +
      JSON.stringify({
        game: saved.id,
        scenario: 'double-first-to-home',
        rows: restored.page.items,
        after: restored.after,
        runners: restored.runners,
      }),
  )
})

test('別tenantは対象試合のprefixを取得できない', async ({ page }) => {
  test.skip(!otherTeam || !resultFile, '他tenant資格または結果ファイルが未供給')
  const game = readFileSync(resultFile!, 'utf8')
  await login(page, otherTeam!)
  const response = await page.request.get(
    `${baseURL}/api/games/${game}/started?projection=play-prefix-v3`,
    { timeout: httpTimeout },
  )
  expect(response.status()).toBe(404)
})
