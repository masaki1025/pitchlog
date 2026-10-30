"""実ACK本文消失のowned HTTPS試験専用資産。成功経路は実app/DBを使う。"""

from __future__ import annotations

import json
from pathlib import Path

# 新規作成・開始のUI操作は既通常3球witnessの同じ導線を再利用する。
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

test('実commit後のACK本文喪失から同要求を重複再掲し1球へ復元する', async ({
  page,
}) => {
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('実HTTPSが必要です')
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window)
    const marker = 'pitchlog-owned-ack-loss-v1'
    const digest = async (value: string) =>
      Array.from(
        new Uint8Array(
          await crypto.subtle.digest(
            'SHA-256',
            new TextEncoder().encode(value),
          ),
        ),
      )
        .map((x) => x.toString(16).padStart(2, '0'))
        .join('')
    window.fetch = async (input, init) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url
      if (
        init?.method !== 'POST' ||
        !/\/games\/[^/]+\/sync\/events$/.test(
          new URL(url, location.href).pathname,
        )
      )
        return nativeFetch(input, init)
      if (typeof init.body !== 'string')
        throw new Error('元要求本文を確認できません')
      const attempt = new Headers(init.headers).get(
        'X-Pitchlog-Sync-Attempt',
      )
      if (!attempt) throw new Error('耐久attemptヘッダがありません')
      const bodyDigest = await digest(init.body),
        attemptDigest = await digest(attempt)
      const event = JSON.parse(init.body).events[0]
      const prior = sessionStorage.getItem(marker)
      const first = prior === null
      const expected = first
        ? { bodyDigest, attemptDigest, count: 0 }
        : JSON.parse(prior!)
      const response = await nativeFetch(input, init)
      // 元通信と実commitを必ず通す。元本文/資格/ACK原値はブラウザ外へ返さない。
      const ack = await response.clone().json()
      const item = ack.eventResults?.[0]
      const sameSlot =
        ack.eventResults?.length === 1 &&
        item?.d1 === event.d1 &&
        item?.d4 === event.d4 &&
        item?.d5 === event.d5
      const values = {
        ...expected,
        count: expected.count + 1,
        sameBody: bodyDigest === expected.bodyDigest,
        sameAttempt: attemptDigest === expected.attemptDigest,
        sameSlot,
        watermark: ack.advancedD3 === 1,
        status200: response.status === 200,
        nativeAccepted: first && item?.a5Result === '受理',
        duplicate: !first && item?.a5Result === '重複',
        injected: first || expected.injected === true,
      }
      sessionStorage.setItem(marker, JSON.stringify(values))
      if (first) {
        if (
          response.status !== 200 ||
          !sameSlot ||
          ack.advancedD3 !== 1 ||
          item?.a5Result !== '受理'
        )
          throw new Error('実commit受理を確認できません')
        // header受信後の本文読取故障。fetch拒否のCookie不確実性とは別の注入。
        Object.defineProperty(response, 'text', {
          value: async () => {
            throw new TypeError('owned ACK body-loss injection')
          },
        })
      }
      return response
    }
    Object.defineProperty(window, '__ackLossEvidence', {
      value: () => {
        const raw = sessionStorage.getItem(marker)
        if (!raw) return null
        const value = JSON.parse(raw)
        // digestや原値も返さず、有限件数とbooleanだけを外へ出す。
        return {
          count: value.count,
          sameBody: value.sameBody,
          sameAttempt: value.sameAttempt,
          sameSlot: value.sameSlot,
          watermark: value.watermark,
          status200: value.status200,
          injected: value.injected,
          duplicate: value.duplicate,
          nativeAccepted: value.nativeAccepted,
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
  const initialRead = page.waitForResponse(isPrefix, { timeout: 30000 })
  await page
    .getByRole('button', { name: /^サーバーから(?:復元|再取得)$/ })
    .click()
  const initial = await (await initialRead).json()
  expect(initial.read_kind).toBe('recorded-prefix')
  expect(initial.prefix_ref.length).toBe('0')
  await expect(page.getByTestId('ordinary-pitch-result')).toBeVisible()
  for (const suffix of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${suffix}`).check()
  await page
    .getByTestId('ordinary-pitch-result')
    .selectOption('batting-result.ball')
  const types = page.getByTestId('first-ball-pitch-type')
  await expect(types).toBeEnabled()
  await expect(types.locator('option')).not.toHaveCount(1)
  await types.selectOption({ index: 1 })
  await page.getByTestId('first-ball-course').locator('svg').click()
  const committed = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
    { timeout: 30000 },
  )
  await page.getByTestId('first-ball-save').click()
  expect((await committed).status()).toBe(200)
  await expect(page.getByTestId('first-ball-status')).toContainText(
    '未確認',
  )
  await expect(page.getByTestId('ordinary-local-balls')).toHaveText('1')
  await expect(page.getByTestId('ordinary-local-strikes')).toHaveText('0')
  await expect(page.getByTestId('ordinary-state-source')).toContainText(
    '暫定状態',
  )
  const firstEvidence = await page.evaluate(() =>
    (
      window as unknown as { __ackLossEvidence: () => unknown }
    ).__ackLossEvidence(),
  )
  expect(firstEvidence).toStrictEqual({
    count: 1,
    sameBody: true,
    sameAttempt: true,
    sameSlot: true,
    watermark: true,
    status200: true,
    injected: true,
    duplicate: false,
    nativeAccepted: true,
  })
  const scope = {
    tenantId: initial.prefix_ref.tenantId,
    gameId: saved.id,
    d4: initial.current_d4,
  }
  const readSlot = () =>
    page.evaluate(async (scope) => {
      const { openDurableQueue } =
        await import('/src/lib/sync/durableQueue.ts')
      const { queueStateId } = await import('/src/lib/sync/queueState.ts')
      const queue = await openDurableQueue({
        databaseName: 'pitchlog-first-ball-queue-' + scope.tenantId,
      })
      try {
        const slot = await queue.readSlot(
          { game: scope.gameId, d4: scope.d4 },
          1,
        )
        return {
          count: await queue.countSlots(),
          unsent: slot?.state === queueStateId('未送信'),
          synced: slot?.state === queueStateId('同期済み'),
        }
      } finally {
        queue.close()
      }
    }, scope)
  expect(await readSlot()).toStrictEqual({
    count: 1,
    unsent: true,
    synced: false,
  })
  const afterCommit = page.waitForResponse(isPrefix, { timeout: 30000 })
  await page.reload()
  const restored = await (await afterCommit).json()
  expect(restored.prefix_ref.length).toBe('1')
  expect(restored.after.stateFields).toStrictEqual({
    ...initial.after.stateFields,
    'state.count.balls': '1',
  })
  expect(restored.after.scoreboard).toStrictEqual(initial.after.scoreboard)
  expect(restored.page.items).toHaveLength(1)
  await expect(page.getByTestId('restore-balls')).toHaveText('1')
  await expect(page.getByTestId('restore-history')).toHaveText('1件')
  await expect(page.getByTestId('ordinary-local-balls')).toHaveText('1')
  await expect(page.getByTestId('ordinary-state-source')).toContainText(
    'サーバー確認済み',
  )
  await expect(page.getByTestId('first-ball-status')).toContainText(
    '未確認',
  )
  expect(await readSlot()).toStrictEqual({
    count: 1,
    unsent: true,
    synced: false,
  })
  for (const suffix of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${suffix}`).check()
  const repeated = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
    { timeout: 30000 },
  )
  const terminalRead = page.waitForResponse(isPrefix, { timeout: 30000 })
  await page.getByTestId('first-ball-retry').click()
  expect((await repeated).status()).toBe(200)
  const terminal = await (await terminalRead).json()
  expect(terminal.after).toStrictEqual(restored.after)
  expect(terminal.prefix_ref).toStrictEqual(restored.prefix_ref)
  expect(terminal.page).toStrictEqual(restored.page)
  const replayEvidence = await page.evaluate(() =>
    (
      window as unknown as { __ackLossEvidence: () => unknown }
    ).__ackLossEvidence(),
  )
  expect(replayEvidence).toStrictEqual({
    count: 2,
    sameBody: true,
    sameAttempt: true,
    sameSlot: true,
    watermark: true,
    status200: true,
    injected: true,
    duplicate: true,
    nativeAccepted: false,
  })
  expect(await readSlot()).toStrictEqual({
    count: 1,
    unsent: false,
    synced: true,
  })
  const finalRead = page.waitForResponse(isPrefix, { timeout: 30000 })
  await page.reload()
  const final = await (await finalRead).json()
  expect(final.after).toStrictEqual(restored.after)
  expect(final.prefix_ref.length).toBe('1')
  expect(final.page.items).toHaveLength(1)
  await expect(page.getByTestId('restore-balls')).toHaveText('1')
  await expect(page.getByTestId('restore-strikes')).toHaveText('0')
  await expect(page.getByTestId('restore-history')).toHaveText('1件')
  await expect(page.getByTestId('restore-plays')).toHaveText('1件')
  expect(await readSlot()).toStrictEqual({
    count: 1,
    unsent: false,
    synced: true,
  })
  console.log(`PITCHLOG_ACK_LOSS_GAME_ID=${saved.id}`)
})

"""


def write_browser_assets(directory: Path, frontend: Path) -> Path:
    """TLS trustを試験専用に限定したPlaywright資産をowned一時dirへ書く。"""
    directory.mkdir(parents=True, exist_ok=False)
    module = (frontend / "node_modules/@playwright/test/index.mjs").as_posix()
    (directory / "ordinary-ack-loss.spec.ts").write_text(
        _SPEC.replace("__PLAYWRIGHT_MODULE__", module), encoding="utf-8"
    )
    config = directory / "playwright.config.mjs"
    config.write_text(
        f"import {{defineConfig,devices}} from {json.dumps(module)};\n"
        "export default defineConfig({testDir:'.',"
        "testMatch:'ordinary-ack-loss.spec.ts',"
        "fullyParallel:false,workers:1,timeout:180000,"
        "use:{...devices['Desktop Chrome'],ignoreHTTPSErrors:true,"
        "trace:'off',screenshot:'off',video:'off'},reporter:'list',"
        f"outputDir:{json.dumps(str(directory / 'output'))}}});\n",
        encoding="utf-8",
    )
    return config
