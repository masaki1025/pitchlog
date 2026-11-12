/** 実login/create/startを画面操作する。保存成功応答の代替は作らない。 */
import { randomUUID } from 'node:crypto'
import { expect, type Page } from '@playwright/test'
import type { LineupPrefixGame } from '../api/lineupPrefixGame'
export const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const away = process.env.PITCHLOG_E2E_AWAY_TEAM
const home = process.env.PITCHLOG_E2E_HOME_TEAM
if (!baseURL || !team || !password || !away || !home)
  throw new Error('所有E2E環境が不足')
export function apiPath(url: string): string {
  return new URL(url).pathname
}
export async function realLogin(
  page: Page,
  redirect = '/games',
): Promise<string> {
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
  // 試合一覧へ戻る経路だけ、認証済み画面のhydrateを待つ。
  if (redirect === '/games')
    await expect(
      page.getByRole('button', { name: '新しい試合', exact: true }),
    ).toBeVisible({ timeout: 30_000 })
  return body.tenant_id
}

export async function createAndStartRealGame(
  page: Page,
  label: string,
  expectedRegulationInnings = 9,
  gameType = 'game_other',
) {
  const tenantId = await realLogin(page)
  await page.getByRole('button', { name: '新しい試合', exact: true }).click()
  const form = page.getByRole('region', {
    name: '試合の新規作成',
    exact: true,
  })
  await expect(form.getByLabel('日時（日本時間）')).toBeEnabled()
  await form.getByLabel('日時（日本時間）').fill('2026-10-31T10:00')
  await form.getByTestId('game-type').selectOption(gameType)
  await form.getByTestId('away').selectOption(away!)
  await form.getByTestId('home').selectOption(home!)
  await form.getByTestId('tournament-kind').selectOption('new')
  await form.getByLabel('新しい大会名', { exact: true }).fill(label)
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
    applied_rules: { dh: boolean; regulationInnings: number }
  }
  expect(saved.status).toBe('preparing')
  // 作成した試合の保存値を確認すると記録画面へ遷移する。
  await form
    .getByRole('button', {
      name: '作成した試合IDの保存値を確認',
      exact: true,
    })
    .click()
  // 候補環境のcold start/初回route解決を含め、製品の同期5秒目標とは別に待つ。
  await expect(page).toHaveURL(`${baseURL}/games/${saved.id}/record`, {
    timeout: 30_000,
  })
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

  await expect(page).toHaveURL(
    `${baseURL}/games/${saved.id}/record?recording=play-prefix-v3`,
  )
  // 初球前のv3 zero readは409を返し得るため、開始済みmetadataをtenant照合付きで
  // 実GETする。roster/stateは初球UIの実入力にだけ使い、保存成功の証拠にはしない。
  const initialResponse = await page.request.get(
    `${baseURL}/api/games/${saved.id}/started`,
    {
      headers: {
        'X-Pitchlog-Expected-Tenant': tenantId,
        'X-Pitchlog-Tenant-Challenge': randomUUID(),
      },
    },
  )
  expect(initialResponse.status()).toBe(200)
  const metadata = (await initialResponse.json()) as {
    read_kind?: unknown
    roster: unknown
    state: unknown
  }
  expect(metadata.read_kind).toBe('initial')
  const initial = {
    ...metadata,
    id: saved.id,
    after: metadata.state,
    runners: [],
  } as unknown as LineupPrefixGame
  expect(saved.applied_rules.regulationInnings).toBe(expectedRegulationInnings)
  return { game: saved, head: initial }
}

/** サーバーが実際に返したv3 headだけを待つ。fixture応答を供給しない。 */
export function nextRecordedHead(page: Page, gameId: string, count: number) {
  return page.waitForResponse(async (response) => {
    if (
      response.request().method() !== 'GET' ||
      apiPath(response.url()) !== `/api/games/${gameId}/started` ||
      response.status() !== 200
    )
      return false
    // reloadで中断された旧応答は本文を読めない。別の実GETだけを待つ。
    let value: { read_kind?: unknown; prefix_ref?: { length?: unknown } }
    try {
      value = (await response.json()) as typeof value
    } catch {
      return false
    }
    return (
      value.read_kind === 'lineup-prefix' &&
      value.prefix_ref?.length === String(count)
    )
  })
}

/** 実server headの半回から現在守備sideだけを閉選択する。 */
export function realDefendingSide(head: LineupPrefixGame): 'home' | 'away' {
  const half = head.after.stateFields['state.half']
  if (half === 'top') return 'home'
  if (half === 'bottom') return 'away'
  throw new Error('実server headの半回が未定義')
}

/** 実入力・実POST・実GETの完了をそれぞれ確認する。 */
export async function recordRealPitch(
  page: Page,
  head: LineupPrefixGame,
  result: string,
  count: number,
) {
  await expect(page.getByTestId('ordinary-state-source')).toHaveText(
    'サーバー確認済み',
  )
  // 未確認時は可視の安全確認導線からSheetを開き、4項目を実際に確認する。
  const safety = page.getByRole('button', { name: /記録端末の安全確認/ })
  if (await safety.isVisible().catch(() => false)) {
    await safety.click()
    for (const label of [
      'ほかの記録タブと同じブラウザプロファイルを使います',
      '通常・プライベートなどの閲覧モードを統一します',
      '同じサイトの保存領域を使うタブだけで記録します',
      'この端末でLockdownモードを適用していません',
    ])
      await page.getByRole('checkbox', { name: label }).last().check()
    await page
      .getByRole('button', { name: '確認して記録へ戻る', exact: true })
      .click()
  }
  // 開始直後のcontroller再読取が終わる前に結果を選ぶとblockedのままになる。
  await expect(page.getByTestId('first-ball-status')).toHaveText(
    '投球を記録できます',
    { timeout: 30_000 },
  )
  const pitch = page.getByTestId('first-ball-pitch-type')
  await expect(pitch.locator('option')).not.toHaveCount(1)
  await pitch.selectOption({ index: 1 })
  // 前球の打球観測を閉じ、投球コースを入れてから結果を選ぶ。
  await page
    .getByTestId('ordinary-pitch-result')
    .selectOption('batting-result.ball')
  await page.getByTestId('first-ball-course').locator('svg').click()
  await page.getByTestId('ordinary-pitch-result').selectOption(result)
  if (
    result === 'batting-result.home-run' ||
    result === 'batting-result.batted-out'
  ) {
    const fielder = head.roster.teams
      .find((t) => t.side === realDefendingSide(head))
      ?.participants.find((p) =>
        p.roles.some(
          (role) => role.kind === 'fielding' && role.position === '9',
        ),
      )
    if (!fielder) throw new Error('実守備rosterに右翼手がいない')
    const panel = page
      .getByTestId('batted-hit-observation')
      .filter({ visible: true })
      .last()
    for (const [key, value] of [
      ['typeKey', 'batted.screen.line'],
      ['strengthKey', 'batted.screen.hard'],
      ['hitX', '0.25'],
      ['hitY', '0.75'],
      ['rawFielderPosition', '9'],
      ['resolvedFielderId', fielder.player.player_id],
    ] as const) {
      await panel.getByTestId(`batted-mode-${key}`).selectOption('observed')
      const input = panel.getByTestId(`batted-value-${key}`)
      // 打球語彙の実GETが終わるまで観測値はdisabled。固定値で補完しない。
      await expect(input).toBeEnabled({ timeout: 30_000 })
      if (
        key === 'typeKey' ||
        key === 'strengthKey' ||
        key === 'resolvedFielderId'
      )
        await input.selectOption(value)
      else await input.fill(value)
    }
    for (const key of ['scoring', 'interference', 'overrides', 'thirdOut'])
      await panel
        .locator(`[data-question-key="${key}"] select`)
        .selectOption('confirmed')
  }
  await expect(page.getByTestId('first-ball-save')).toBeEnabled()
  const confirmed = nextRecordedHead(page, head.id, count)
  const posted = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${head.id}/sync/events`,
  )
  await page
    .evaluate(() => {
      const scope = globalThis as {
        __pitchlogE2eDiagnostics?: boolean
        __pitchlogClickDispatchedAt?: number
      }
      if (scope.__pitchlogE2eDiagnostics === true)
        scope.__pitchlogClickDispatchedAt = Date.now()
    })
    .catch(() => undefined)
  const started = Date.now()
  await page.getByTestId('first-ball-save').click()
  const response = await posted
  const elapsedMs = Date.now() - started
  expect(response.status()).toBe(200)
  const ack = await response.json()
  expect(ack.eventResults?.[0]?.a5Result).toBe('受理')
  const next = (await (await confirmed).json()) as LineupPrefixGame
  await expect(page.getByTestId('restore-history')).toHaveText(`${count}件`)
  return { head: next, elapsedMs }
}
