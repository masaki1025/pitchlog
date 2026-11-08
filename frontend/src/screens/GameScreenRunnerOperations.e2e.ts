import { createHash } from 'node:crypto'
import { readFileSync, renameSync, writeFileSync } from 'node:fs'
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
const httpTimeout = 60_000
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
  let response
  try {
    response = await posted
  } catch (error) {
    // 機能診断は資格/本文を出さず、現在のUI状態だけを保存する。
    console.log(
      'PITCHLOG_RUNNER_SEND_STATE=' +
        JSON.stringify({
          path: new URL(page.url()).pathname,
          status: await page
            .getByTestId('first-ball-status')
            .textContent()
            .catch(() => null),
          source: await page
            .getByTestId('ordinary-state-source')
            .textContent()
            .catch(() => null),
        }),
    )
    throw error
  }
  expect(response.status()).toBe(200)
}

type StartedGame = {
  id: string
  status: string
  applied_rules: { dh: boolean }
}
async function createGame(
  page: Page,
  label: string,
): Promise<StartedGame & { initialHead: Head }> {
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
  const initialRead = readHead(page, saved.id, '0')
  const started = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${saved.id}/start`,
    { timeout: httpTimeout },
  )
  await page.getByRole('button', { name: '試合を開始', exact: true }).click()
  expect((await started).status()).toBe(200)
  const initialHead = (await (await initialRead).json()) as Head
  await expect(page.getByTestId('ordinary-state-source')).toHaveText(
    'サーバー確認済みの状態',
  )
  return { ...saved, initialHead }
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
  let previous: { d5: string; attempt: string; body: string } | null = null
  const comparisons: Array<Record<string, boolean | number | null>> = []
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
      if (process.env.PITCHLOG_E2E_RUNNER_DIAGNOSTIC === '1') {
        const value = JSON.parse(body) as { events?: Array<{ d5?: unknown }> }
        const d5 = value.events?.[0]?.d5
        if (typeof d5 !== 'string' || !resultFile)
          throw Error('診断要求の構造が不正')
        if (comparisons.length < 8)
          comparisons.push({
            ordinal: comparisons.length + 1,
            prior: previous !== null,
            sameD5: previous === null ? null : previous.d5 === d5,
            sameAttempt:
              previous === null ? null : previous.attempt === attempt,
            sameBody: previous === null ? null : previous.body === body,
          })
        previous = { d5, attempt, body }
        writeFileSync(
          resultFile + '.comparison.json',
          JSON.stringify({
            comparisons,
            limit: 8,
            atLimit: comparisons.length >= 8,
          }),
        )
      }
    }
  })
  return requests
}

function repeatWindow(page: Page) {
  return page.evaluate(() =>
    (
      window as unknown as {
        __repeatRunnerOperationForTest: () => Promise<{
          status: number
          body: { eventResults: Array<{ a5Result: string }> }
        }>
      }
    ).__repeatRunnerOperationForTest(),
  )
}

async function userPreconditions(page: Page) {
  for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${name}`).check()
}
async function commitHead(page: Page, id: string, length: number) {
  const head = readHead(page, id, String(length))
  await save(page, id)
  return (await (await head).json()) as Head
}
function actualFielder(head: Head) {
  const side = head.after.stateFields['state.half'] === 'top' ? 'home' : 'away'
  const found = head.roster.teams
    .find((t) => t.side === side)
    ?.participants.find((p) =>
      p.roles.some((r) => r.kind === 'fielding' && r.position === '9'),
    )
  if (!found) throw Error('実名簿の右翼手がない')
  return found.player.player_id
}
async function normalPitch(page: Page, result: string) {
  await userPreconditions(page)
  await page.getByTestId('ordinary-pitch-result').selectOption(result)
  await page
    .getByTestId('first-ball-pitch-type')
    .selectOption('u06-first-ball-fastball')
  await page.getByTestId('first-ball-course').locator('svg').click()
}
type RunnerAction = {
  operation: string
  base: '1' | '2' | '3'
  outcome: 'safe-advance' | 'out'
  destination: string
  cause?: string
  third?: string
}
async function runnerInput(page: Page, a: RunnerAction) {
  await userPreconditions(page)
  await page
    .getByTestId('ordinary-pitch-result')
    .selectOption('batting-result.ball')
  await page.getByTestId('runner-operation-enable').check()
  await page.getByTestId('runner-operation-kind').selectOption(a.operation)
  await page.getByTestId(`runner-${a.base}-outcome`).selectOption(a.outcome)
  await page
    .getByTestId(`runner-${a.base}-destination`)
    .selectOption(a.destination)
  if (a.cause)
    await page.getByTestId(`runner-${a.base}-cause`).selectOption(a.cause)
  await page.getByTestId('runner-third-out').selectOption(a.third ?? 'none')
  await page.getByTestId('runner-no-error').check()
  await page.getByTestId('runner-observation-confirm').click()
  await expect(page.getByTestId('runner-observation-ready')).toBeVisible()
  const np =
    a.operation === 'steal-nonpitch' ||
    a.operation === 'secondary-result.balk' ||
    a.operation.includes('pickoff-destination')
  if (np) await expect(page.getByTestId('first-ball-course')).toHaveCount(0)
  else {
    await page
      .getByTestId('first-ball-pitch-type')
      .selectOption('u06-first-ball-fastball')
    await page.getByTestId('first-ball-course').locator('svg').click()
  }
}
const fullActions: Array<'single' | 'strike' | RunnerAction> = [
  'single',
  {
    operation: 'steal-nonpitch',
    base: '1',
    outcome: 'safe-advance',
    destination: 'second',
  },
  {
    operation: 'secondary-result.wild-pitch',
    base: '2',
    outcome: 'safe-advance',
    destination: 'third',
  },
  {
    operation: 'secondary-result.passed-ball',
    base: '3',
    outcome: 'safe-advance',
    destination: 'home',
  },
  'single',
  {
    operation: 'pitcher-pickoff-destination.first',
    base: '1',
    outcome: 'out',
    destination: 'first',
    cause: 'pitcher-pickoff-out',
  },
  'single',
  'strike',
  'strike',
  {
    operation: 'batting-result.strikeout-double-play',
    base: '1',
    outcome: 'out',
    destination: 'second',
    cause: 'caught-stealing',
    third: 'not-required',
  },
  'single',
  {
    operation: 'secondary-result.balk',
    base: '1',
    outcome: 'safe-advance',
    destination: 'second',
  },
  {
    operation: 'catcher-pickoff-destination.second',
    base: '2',
    outcome: 'out',
    destination: 'second',
    cause: 'catcher-pickoff-out',
  },
  'single',
  {
    operation: 'steal-nonpitch',
    base: '1',
    outcome: 'out',
    destination: 'second',
    cause: 'caught-stealing',
  },
  'single',
  {
    operation: 'steal-nonpitch',
    base: '1',
    outcome: 'out',
    destination: 'second',
    cause: 'caught-stealing',
    third: 'not-required',
  },
]

test('新規作成から共通走者結果の実保存・再送・reload・越境まで同じ試合で通す', async ({
  page,
  browser,
}) => {
  page.setDefaultTimeout(httpTimeout)
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    let request: { url: string; init: RequestInit } | null = null
    window.fetch = async (input, init) => {
      if (
        typeof input === 'string' &&
        input.includes('/sync/events') &&
        init?.method === 'POST' &&
        typeof init.body === 'string'
      )
        request = {
          url: input,
          init: {
            ...init,
            headers: new Headers(init.headers),
            body: init.body,
          },
        }
      return original(input, init)
    }
    Object.defineProperty(window, '__repeatRunnerOperationForTest', {
      value: async () => {
        if (!request) throw Error('元要求がない')
        const r = await original(request.url, {
          ...request.init,
          signal: AbortSignal.timeout(60_000),
        })
        return { status: r.status, body: await r.json() }
      },
    })
  })
  await login(page)
  const game = await createGame(page, '共通走者操作')
  let head = game.initialHead
  const requests = requestRecorder(page, game.id)
  const scope =
    process.env.PITCHLOG_E2E_RUNNER_OPERATIONS_SCOPE === 'first'
      ? 'first'
      : 'full'
  const actions = scope === 'first' ? fullActions.slice(0, 2) : fullActions
  const records: Array<{
    operation: string
    length: number
    after: Head['after']
    runners: Runner[]
    lastEntry: unknown
  }> = []
  let duplicate: { status: number; a5: string } | null = null
  for (const [index, action] of actions.entries()) {
    const before = structuredClone(head)
    if (typeof action === 'string') {
      await page
        .getByTestId('ordinary-pitch-result')
        .selectOption('batting-result.ball')
      await page.getByTestId('runner-operation-enable').uncheck()
      if (action === 'single')
        await selectPitch(
          page,
          'batting-result.single',
          actualFielder(head),
          null,
        )
      else await normalPitch(page, 'batting-result.called-pitch')
    } else await runnerInput(page, action)
    head = await commitHead(page, game.id, index + 1)
    records.push({
      operation: typeof action === 'string' ? action : action.operation,
      length: index + 1,
      after: head.after,
      runners: head.runners,
      lastEntry: head.last_entry,
    })
    if (index === 1) {
      expect(
        head.runners.map((r) => [r.base, r.runnerId, r.responsiblePitcherId]),
      ).toEqual([
        [
          '2',
          before.runners[0]!.runnerId,
          before.runners[0]!.responsiblePitcherId,
        ],
      ])
      expect(head.after.stateFields['state.count.balls']).toBe('0')
      const repeated = await repeatWindow(page)
      expect(repeated.status).toBe(200)
      expect(repeated.body.eventResults[0]!.a5Result).toBe('重複')
      duplicate = {
        status: repeated.status,
        a5: repeated.body.eventResults[0]!.a5Result,
      }
      const prior = structuredClone(head)
      const restored = readHead(page, game.id, String(index + 1))
      await page.reload()
      head = (await (await restored).json()) as Head
      expect({
        after: head.after,
        runners: head.runners,
        last: head.last_entry,
      }).toEqual({
        after: prior.after,
        runners: prior.runners,
        last: prior.last_entry,
      })
    }
  }
  if (scope === 'full') {
    expect(head.after.stateFields['state.inning']).toBe('2')
    expect(head.after.stateFields['state.half']).toBe('top')
    expect(head.after.stateFields['state.outs']).toBe('0')
    expect(head.after.stateFields['state.score']).toEqual({
      home: '0',
      away: '1',
    })
    expect(head.after.battingOrderBySide).toEqual({ away: '5', home: '4' })
    expect(head.runners).toEqual([])
  }
  const last = structuredClone(head)
  const finalRead = readHead(page, game.id, String(actions.length))
  await page.reload()
  head = (await (await finalRead).json()) as Head
  expect({
    after: head.after,
    runners: head.runners,
    last: head.last_entry,
  }).toEqual({
    after: last.after,
    runners: last.runners,
    last: last.last_entry,
  })
  if (!resultFile) throw Error('実測結果の固定先がない')
  writeFileSync(
    resultFile,
    JSON.stringify(
      {
        scope,
        gameId: game.id,
        length: actions.length,
        records,
        requests,
        replay: duplicate,
        reloaded: {
          after: head.after,
          runners: head.runners,
          last: head.last_entry,
        },
      },
      null,
      2,
    ),
  )
  if (!otherTeam) throw Error('越境対向の実tenantがない')
  // 記録profileを保ち、別contextで実login/Cookieによる越境拒否を確認する。
  const otherContext = await browser.newContext({ ignoreHTTPSErrors: true })
  try {
    const otherPage = await otherContext.newPage()
    await login(otherPage, otherTeam)
    const foreign = await otherPage.request.get(
      `${baseURL}/api/games/${game.id}/started?projection=play-prefix-v3`,
    )
    expect(foreign.status()).toBe(404)
  } finally {
    await otherContext.close()
  }
})

test('非投球盗塁のT4途中故障は成功表示せず、先行1球だけをサーバーに残す', async ({
  page,
}) => {
  page.setDefaultTimeout(httpTimeout)
  await login(page)
  const saved = await createGame(page, 'H')
  const zero = saved.initialHead
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
  const beforeRead = readHead(page, saved.id, '1')
  await save(page, saved.id)
  const beforeResponse = await beforeRead
  const before = (await beforeResponse.json()) as Head
  expect(before.after.stateFields['state.runners']).toBe('first')
  // ownedホストが実DB全T5版を読んだ後にだけ故障要求を出す。
  const checkpoint = process.env.PITCHLOG_E2E_RUNNER_FAULT_CHECKPOINT
  if (!checkpoint) throw new Error('故障前の実DB観測同期点が供給されていない')
  writeFileSync(checkpoint + '.tmp', JSON.stringify({ game: saved.id }))
  renameSync(checkpoint + '.tmp', checkpoint)
  await expect
    .poll(
      () => {
        try {
          return readFileSync(checkpoint + '.ready', 'utf8')
        } catch {
          return null
        }
      },
      { timeout: httpTimeout },
    )
    .toBe(saved.id)
  let failedD5: string | undefined
  let failedPlayId: string | undefined
  let failedEventId: string | undefined
  await page.route(`**/api/games/${saved.id}/sync/events`, async (route) => {
    const original = route.request()
    const value = original.postDataJSON() as {
      events: Array<{
        d5: string
        payload: {
          calculation: {
            request: {
              playIdentity: {
                playId: string
                eventId: string
              }
            }
          }
        }
      }>
    }
    if (failedD5 !== undefined && failedD5 !== value.events[0]?.d5)
      throw new Error('結果不明の要求を新D5へ置換している')
    failedD5 = value.events[0]?.d5
    failedPlayId =
      value.events[0]?.payload.calculation.request.playIdentity.playId
    failedEventId =
      value.events[0]?.payload.calculation.request.playIdentity.eventId
    // 公開test flagだけを追加する。元本文/Cookie/端末資格/attemptは変更しない。
    await route.continue({
      headers: {
        ...(await original.allHeaders()),
        'X-Pitchlog-Owned-Runner-Fault': 'after_t4_projection',
      },
    })
  })
  await runnerInput(page, {
    operation: 'steal-nonpitch',
    base: '1',
    outcome: 'safe-advance',
    destination: 'second',
  })
  const posted = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
    { timeout: httpTimeout },
  )
  await expect(page.getByTestId('first-ball-save')).toBeEnabled()
  await page.getByTestId('first-ball-save').click()
  const failed = await posted
  expect(failed.status()).toBe(500)
  await expect(
    page.getByText(/^未確認の要求が端末に残っています/),
  ).toBeVisible()
  const originalRead = beforeResponse.request()
  const afterRead = await page.request.get(originalRead.url(), {
    // HTTP/2 pseudo headerはHTTP/1 request APIへ送れない。資格原値は維持する。
    headers: Object.fromEntries(
      Object.entries(await originalRead.allHeaders()).filter(
        ([name]) => !name.startsWith(':'),
      ),
    ),
    timeout: httpTimeout,
  })
  expect(afterRead.status()).toBe(200)
  const after = (await afterRead.json()) as Head
  expect(after.after).toEqual(before.after)
  expect(after.runners).toEqual(before.runners)
  expect(after.prefix_ref).toEqual(before.prefix_ref)
  expect(after.page.items).toEqual(before.page.items)
  expect(after.last_entry).toEqual(before.last_entry)
  if (!failedD5 || !failedPlayId || !failedEventId)
    throw new Error('故障させた実要求のidentityがない')
  if (!resultFile) throw Error('実測結果の固定先がない')
  writeFileSync(
    resultFile + '.fault',
    JSON.stringify({
      game: saved.id,
      failedD5,
      failedPlayId,
      failedEventId,
      status: failed.status(),
      prefix: after.prefix_ref.length,
    }),
  )
})
