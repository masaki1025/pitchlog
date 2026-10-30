"""通常3球の実画面試験専用Playwright資産をowned一時領域へ生成する。"""

from __future__ import annotations

import json
from pathlib import Path

# test専用のTLS trustであり実機・運用TLSの検証ではない。trace等に資格を残さない。
_SPEC = r"""
import { expect, test, type Page } from '__PLAYWRIGHT_MODULE__'

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

test('実HTTPSの新規試合で通常3球を保存・同要求再送・reloadする', async ({
  page,
}) => {
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('HTTPSが必要です')
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window)
    const originals: { url: string; init: RequestInit }[] = []
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
          throw new Error('同期本文がありません')
        originals.push({
          url,
          init: {
            ...init,
            headers: new Headers(init.headers),
            body: init.body,
          },
        })
      }
      return nativeFetch(input, init)
    }
    // 原要求・資格・attemptはブラウザclosureだけに保持し、外部へ返さない。
    Object.defineProperty(window, '__ordinaryReplayFirst', {
      value: async () => {
        if (originals.length !== 3) throw new Error('3要求が必要です')
        const original = originals[0]!
        const event = JSON.parse(original.init.body as string).events[0]
        const response = await nativeFetch(original.url, original.init)
        const ack = await response.json()
        const item = ack.eventResults?.[0]
        return {
          status: response.status,
          count: originals.length,
          sameSlot:
            ack.eventResults?.length === 1 &&
            item?.d1 === event.d1 &&
            item?.d4 === event.d4 &&
            item?.d5 === event.d5,
          advanced: ack.advancedD3 === 3 && item?.a5Result === '受理',
        }
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
    .fill('画面作成大会')
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
  await page
    .getByRole('button', { name: '試合を開始', exact: true })
    .click()
  const startedResponse = await started
  expect(startedResponse.status()).toBe(200)
  // 開始後の実サーバー再取得で復元入口が出たら、実UIから再取得する。
  const isPrefix = (res: import('__PLAYWRIGHT_MODULE__').Response) => {
    const url = new URL(res.url())
    return (
      res.request().method() === 'GET' &&
      url.pathname === `/api/games/${saved.id}/started` &&
      url.searchParams.get('projection') === 'ordinary-prefix-v1' &&
      res.status() === 200
    )
  }
  const initialRead = page.waitForResponse(isPrefix)
  await page
    .getByRole('button', { name: /^サーバーから(?:復元|再取得)$/ })
    .click()
  const initial = await (await initialRead).json()
  expect(initial.read_kind).toBe('recorded-prefix')
  expect(initial.prefix_ref.length).toBe('0')
  await expect(page.getByTestId('ordinary-pitch-result')).toBeVisible()
  expect(
    await page.evaluate(
      () =>
        window.isSecureContext &&
        window.top === window &&
        location.protocol === 'https:',
    ),
  ).toBe(true)
  let latest = initial
  const results = [
    'batting-result.ball',
    'batting-result.called-pitch',
    'batting-result.ball',
  ]
  const balls = ['1', '1', '2'],
    strikes = ['0', '1', '1']
  for (let index = 0; index < results.length; index++) {
    for (const id of ['profile', 'mode', 'bucket', 'lockdown'])
      await page.getByTestId(`first-ball-env-${id}`).check()
    await page
      .getByTestId('ordinary-pitch-result')
      .selectOption(results[index]!)
    const pitchType = page.getByTestId('first-ball-pitch-type')
    await expect(pitchType).toBeEnabled()
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
        isPrefix(res) &&
        (await res.json()).prefix_ref.length === String(index + 1),
    )
    await expect(page.getByTestId('first-ball-save')).toBeEnabled()
    await page.getByTestId('first-ball-save').click()
    const acknowledged = await synchronized
    expect(acknowledged.status()).toBe(200)
    const ack = await acknowledged.json()
    const sent = acknowledged.request().postDataJSON().events[0]
    // 失敗時も原本文や資格をexpect差分へ表示しない。
    expect(
      ack.eventResults?.length === 1 &&
        ack.eventResults[0].a5Result === '受理' &&
        ack.eventResults[0].d1 === sent.d1 &&
        ack.eventResults[0].d4 === sent.d4 &&
        ack.eventResults[0].d5 === sent.d5 &&
        ack.advancedD3 === index + 1,
    ).toBe(true)
    latest = await (await restored).json()
    expect(latest.read_kind).toBe('recorded-prefix')
    expect(latest.page.items).toHaveLength(index + 1)
    expect(latest.after.stateFields).toStrictEqual({
      ...initial.after.stateFields,
      'state.count.balls': balls[index],
      'state.count.strikes': strikes[index],
    })
    expect(latest.after.scoreboard).toStrictEqual(initial.after.scoreboard)
    await expect(page.getByTestId('restore-balls')).toHaveText(
      balls[index]!,
    )
    await expect(page.getByTestId('restore-strikes')).toHaveText(
      strikes[index]!,
    )
    await expect(page.getByTestId('restore-history')).toHaveText(
      `${index + 1}件`,
    )
  }
  const replay = await page.evaluate(async () =>
    (
      window as unknown as {
        __ordinaryReplayFirst: () => Promise<{
          status: number
          count: number
          sameSlot: boolean
          advanced: boolean
        }>
      }
    ).__ordinaryReplayFirst(),
  )
  expect(replay).toStrictEqual({
    status: 200,
    count: 3,
    sameSlot: true,
    advanced: true,
  })
  const reloadedRead = page.waitForResponse(isPrefix)
  await page.reload()
  const reloaded = await (await reloadedRead).json()
  expect(reloaded.read_kind).toBe('recorded-prefix')
  expect(reloaded.prefix_ref).toStrictEqual(latest.prefix_ref)
  expect(reloaded.after).toStrictEqual(latest.after)
  expect(reloaded.page).toStrictEqual(latest.page)
  expect(reloaded.last_entry).toStrictEqual(latest.last_entry)
  await expect(page.getByTestId('restore-balls')).toHaveText('2')
  await expect(page.getByTestId('restore-strikes')).toHaveText('1')
  await expect(page.getByTestId('restore-history')).toHaveText('3件')
  await expect(page.getByTestId('restore-plays')).toHaveText('3件')
  console.log(`PITCHLOG_ORDINARY_GAME_ID=${saved.id}`)
})

"""


def write_browser_assets(directory: Path, frontend: Path) -> Path:
    """実Playwrightを使うspec/configを書き、configの絶対PATHを返す。"""
    directory.mkdir(parents=True, exist_ok=False)
    module = (frontend / "node_modules/@playwright/test/index.mjs").as_posix()
    spec = _SPEC.replace("__PLAYWRIGHT_MODULE__", module)
    (directory / "ordinary-screen.spec.ts").write_text(spec, encoding="utf-8")
    config = directory / "playwright.config.mjs"
    config.write_text(
        f"import {{defineConfig,devices}} from {json.dumps(module)};\n"
        "export default defineConfig({testDir:'.',testMatch:'ordinary-screen.spec.ts',"
        "fullyParallel:false,workers:1,timeout:300000,"
        "use:{...devices['Desktop Chrome'],ignoreHTTPSErrors:true,"
        "trace:'off',screenshot:'off',video:'off'},reporter:'list',"
        f"outputDir:{json.dumps(str(directory / 'output'))}}});\n",
        encoding="utf-8",
    )
    return config
