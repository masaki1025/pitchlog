import { createHash } from 'node:crypto'
import golden from '../../../contracts/state-transition/batted_hit_cases_v1.json'
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

type HistoryItem = {
  play_row: Record<string, unknown>
  play_runners: Array<Record<string, unknown>>
  history_entry: unknown
}
type Head = {
  read_kind: string
  after: {
    stateFields: Record<string, unknown>
    scoreboard: Record<string, unknown>
    battingOrderBySide: { away: string; home: string }
  }
  prefix_ref: { length: string }
  runners: Array<Record<string, unknown>>
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
type ReplayWindow = Window & { __repeatBattedForTest: () => Promise<number> }
const resultIds = [
  'batting-result.single',
  'batting-result.double',
  'batting-result.triple',
  'batting-result.home-run',
] as const

for (const resultId of resultIds) {
  test(`実HTTPS画面の新規試合で${resultId}→次球→元D5再送→reload`, async ({
    page,
  }) => {
    page.setDefaultTimeout(30_000)
    if (new URL(baseURL!).protocol !== 'https:')
      throw new Error('実HTTPS originが必要')
    await page.addInitScript(() => {
      const nativeFetch = window.fetch.bind(window)
      let recorded: { url: string; init: RequestInit } | undefined
      // 正常応答は加工せず、初回の安打要求だけをclosure内へ固定する。
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
          )
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
      Object.defineProperty(window, '__repeatBattedForTest', {
        value: async () => {
          if (!recorded) throw new Error('再送対象の原要求がない')
          return (await nativeFetch(recorded.url, recorded.init)).status
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
    await form
      .getByLabel('新しい大会名', { exact: true })
      .fill('画面安打大会-' + resultId)
    const created = page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === '/api/games',
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

    const requests: Array<{ body: string; attempt: string }> = []
    page.on('request', (request) => {
      if (
        request.method() === 'POST' &&
        apiPath(request.url()) === `/api/games/${saved.id}/sync/events`
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
    const readHead = (length: string) =>
      page.waitForResponse(
        async (response) =>
          response.request().method() === 'GET' &&
          apiPath(response.url()) === `/api/games/${saved.id}/started` &&
          response.status() === 200 &&
          (await response.json()).read_kind === 'lineup-prefix' &&
          (await response.json()).prefix_ref.length === length,
      )
    const zeroRead = readHead('0')
    await page
      .getByRole('button', {
        name: '三振・攻守交代を含む投球の記録へ',
        exact: true,
      })
      .click()
    const zero = (await (await zeroRead).json()) as Head
    expect(zero.runners).toEqual([])
    expect(zero.after.stateFields['state.runners']).toBe('empty')
    expect(zero.after.battingOrderBySide).toEqual({ away: '1', home: '1' })
    const fielding = zero.roster.teams.find((t) => t.side === 'home')
    const fielder = fielding?.participants.find((p) =>
      p.roles.some((r) => r.kind === 'fielding' && r.position === '9'),
    )
    if (!fielder) throw new Error('実守備rosterに位置9の野手がない')
    const nullable = resultId === 'batting-result.home-run'
    async function selectPitch(result: string) {
      // 親の履歴更新とは別に、子controllerの実context再束縛を待つ。
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
    }
    await selectPitch(resultId)
    const observations = {
      typeKey: 'batted.screen.line',
      strengthKey: 'batted.screen.hard',
      hitX: '0.25',
      hitY: '0.75',
      rawFielderPosition: '9',
      resolvedFielderId: fielder.player.player_id,
    }
    for (const key of Object.keys(observations) as Array<
      keyof typeof observations
    >) {
      await page
        .getByTestId(`batted-mode-${key}`)
        .selectOption(nullable ? 'unobserved' : 'observed')
      if (!nullable) {
        const input = page.getByTestId(`batted-value-${key}`)
        if (
          key === 'typeKey' ||
          key === 'strengthKey' ||
          key === 'resolvedFielderId'
        ) {
          await expect(input).toBeEnabled()
          await expect(
            input.locator(`option[value="${observations[key]}"]`),
          ).toHaveCount(1)
          await input.selectOption(observations[key])
        } else await input.fill(observations[key])
      }
    }
    for (const key of ['scoring', 'interference', 'overrides', 'thirdOut'])
      await page
        .getByTestId('batted-hit-observation')
        .locator(`[data-question-key="${key}"] select`)
        .selectOption('confirmed')
    async function save(): Promise<void> {
      const posted = page.waitForResponse(
        (response) =>
          response.request().method() === 'POST' &&
          apiPath(response.url()) === `/api/games/${saved.id}/sync/events`,
      )
      await expect(page.getByTestId('first-ball-save')).toBeEnabled()
      await page.getByTestId('first-ball-save').click()
      const response = await posted
      expect(response.status()).toBe(200)
      expect((await response.json()).eventResults[0].a5Result).toBe('受理')
    }
    const firstRead = readHead('1')
    await save()
    const first = (await (await firstRead).json()) as Head
    expect(requests).toHaveLength(1)
    const original = Object.freeze({ ...requests[0]! })
    expect(first.page.items).toHaveLength(1)
    expect(first.page.items[0]!.play_runners).toEqual([])
    const row = first.page.items[0]!.play_row
    expect(row.batting_result_key).toBe(resultId)
    for (const [column, key] of Object.entries({
      batted_ball_type: 'typeKey',
      batted_ball_strength: 'strengthKey',
      raw_fielder_position: 'rawFielderPosition',
      resolved_fielder_id: 'resolvedFielderId',
    }) as Array<[string, keyof typeof observations]>)
      expect(row[column]).toBe(nullable ? null : observations[key])
    expect(row.hit_x).toBe(nullable ? null : 0.25)
    expect(row.hit_y).toBe(nullable ? null : 0.75)
    // 期待は既承認の無走者golden BH-*-top-O1の固定帰結から引用する。
    // 初期1回0点の画面fixtureにはouts/inning/累計値の別計算を持ち込まない。
    const reference = golden.cases.find(
      (c) => c.request.resultId === resultId && c.caseId.endsWith('-top-O1'),
    )!
    const effect = reference.expected.value!
    expect(first.after.stateFields['state.runners']).toBe(
      effect.after.stateFields['state.runners'],
    )
    expect(first.after.stateFields['state.count.balls']).toBe('0')
    expect(first.after.stateFields['state.count.strikes']).toBe('0')
    expect(first.after.stateFields['state.outs']).toBe('0')
    expect(first.after.stateFields['state.half']).toBe('top')
    expect(first.after.stateFields['state.inning']).toBe('1')
    expect(first.after.stateFields['state.score']).toEqual({
      home: '0',
      away: nullable ? '1' : '0',
    })
    expect(first.after.scoreboard).toEqual({
      inningScores: { home: '0', away: nullable ? '1' : '0' },
      hits: '1',
      errors: '0',
      strikeouts: '0',
      walks: '0',
    })
    expect(first.after.battingOrderBySide).toEqual({ away: '2', home: '1' })
    const base =
      effect.batterDestination.kind === 'reach'
        ? String(effect.batterDestination.base)
        : null
    const expectedRunners =
      base === null
        ? []
        : [
            {
              runnerId: zero.lineup.away.battingOrder['1'],
              responsiblePitcherId: zero.lineup.home.pitcherId,
              base,
              status: '継続',
              statusSource: 'auto',
            },
          ]
    expect(first.runners).toEqual(expectedRunners)
    await expect(page.getByTestId('restore-history')).toHaveText('1件')
    // 次球のcount/holdはST-MATRIX-99b1523fb41399e3と
    // play_prefix_v2_cases.json V2-FOLLOW-ORDINARY-PITCH-25の既採用帰結。
    await selectPitch('batting-result.ball')
    const nextRead = readHead('2')
    await save()
    const next = (await (await nextRead).json()) as Head
    expect(next.page.items).toHaveLength(2)
    expect(next.page.items[0]).toEqual(first.page.items[0])
    expect(next.page.items[1]!.play_row.batting_result_key).toBe(
      'batting-result.ball',
    )
    expect(next.runners).toEqual(expectedRunners)
    expect(next.after).toEqual({
      ...first.after,
      stateFields: { ...first.after.stateFields, 'state.count.balls': '1' },
    })
    const physicalBefore = next.page.items[1]!.play_runners
    expect(physicalBefore).toHaveLength(nullable ? 0 : 1)
    if (!nullable) {
      expect(physicalBefore[0]!.runner_id).toBe(
        zero.lineup.away.battingOrder['1'],
      )
      expect(physicalBefore[0]!.responsible_pitcher_id).toBe(
        zero.lineup.home.pitcherId,
      )
      expect(physicalBefore[0]!.base).toBe(Number(base))
    }
    const replayed = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        apiPath(response.url()) === `/api/games/${saved.id}/sync/events`,
    )
    expect(
      await page.evaluate(() =>
        (window as unknown as ReplayWindow).__repeatBattedForTest(),
      ),
    ).toBe(200)
    expect((await (await replayed).json()).eventResults[0].a5Result).toBe(
      '重複',
    )
    expect(requests).toHaveLength(3)
    expect(requests[0]).toEqual(original)
    expect(requests.at(-1)).toEqual(original)
    const restoredRead = readHead('2')
    await page.reload()
    const restored = (await (await restoredRead).json()) as Head
    expect(restored.after).toEqual(next.after)
    expect(restored.prefix_ref).toEqual(next.prefix_ref)
    expect(restored.page.items).toEqual(next.page.items)
    expect(restored.last_entry).toEqual(next.last_entry)
    expect(restored.runners).toEqual(next.runners)
    await expect(page.getByTestId('restore-history')).toHaveText('2件')
    console.log(
      'PITCHLOG_BATTED_SCREEN_RESULT=' +
        JSON.stringify({
          game: saved.id,
          resultId,
          rows: restored.page.items,
          after: restored.after,
          runners: restored.runners,
          goldenCase: reference.caseId,
        }),
    )
  })
}
