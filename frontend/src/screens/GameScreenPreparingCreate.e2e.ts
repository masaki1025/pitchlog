import { spawn, type ChildProcess } from 'node:child_process'
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { createServer as reservePort } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'
import { expect, test, type Page, type Response } from '@playwright/test'
import { createServer, type ViteDevServer } from 'vite'
import { stripApiPrefix } from '../../vite.config.ts'
import type { PreparingGame } from '../api/games'
import { finishGameScreenChild } from './GameScreenE2eProcess'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const backendRoot = resolve(frontendRoot, '../backend')
interface Runtime {
  port: number
  identities: { name: string; password: string; tenantId: string }[]
  teams: string[]
}
interface DatabaseEvidence {
  game_count: number
  game: PreparingGame
  tournament_display_name: string
  activation_open_count: number
}
let directory: string | undefined
let backend: ChildProcess | undefined
let vite: ViteDevServer | undefined
let runtime: Runtime
let baseURL: string
let stopped = false

async function ownPort(): Promise<number> {
  return new Promise((resolvePort, reject) => {
    const server = reservePort()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      server.close((error) => {
        if (error) return reject(error)
        if (typeof address !== 'object' || address === null)
          return reject(new Error('所有loopback portがない'))
        resolvePort(address.port)
      })
    })
  })
}

/** 子の実fixture cleanup完走後にのみ、実保存観測を返す。 */
async function stopOwned(): Promise<DatabaseEvidence | null> {
  if (stopped) return null
  stopped = true
  let evidence: DatabaseEvidence | null = null
  try {
    await vite?.close()
  } finally {
    try {
      if (directory && backend) {
        writeFileSync(resolve(directory, 'stop'), '', {
          flag: 'wx',
          mode: 0o600,
        })
        await finishGameScreenChild(backend, 90_000, 90_000)
        evidence = JSON.parse(
          readFileSync(resolve(directory, 'database-evidence.json'), 'utf8'),
        ) as DatabaseEvidence
      }
    } finally {
      if (directory) rmSync(directory, { recursive: true, force: true })
    }
  }
  return evidence
}

test.beforeAll(async () => {
  test.setTimeout(180_000)
  if (process.env.PLAYWRIGHT_NO_COPY_PROMPT !== '1')
    throw new Error('DOM/資格の自動保存抑止がない')
  const port = await ownPort()
  baseURL = `http://127.0.0.1:${port}`
  directory = mkdtempSync(resolve(tmpdir(), 'pitchlog-e2e-'))
  const ready = resolve(directory, 'backend-ready.json')
  const inherited = Object.fromEntries(
    ['PATH', 'HOME', 'USER', 'TMPDIR', 'LANG', 'LC_ALL']
      .filter((key) => process.env[key] !== undefined)
      .map((key) => [key, process.env[key]]),
  )
  backend = spawn(
    resolve(backendRoot, '.venv/bin/python'),
    ['../frontend/src/screens/GameScreenPreparingCreateE2eServer.py'],
    {
      cwd: backendRoot,
      stdio: 'ignore',
      env: {
        ...inherited,
        PITCHLOG_E2E_READY_FILE: ready,
        PITCHLOG_E2E_STOP_FILE: resolve(directory, 'stop'),
        PITCHLOG_E2E_FRONTEND_ORIGIN: baseURL,
        PYTHONDONTWRITEBYTECODE: '1',
        PYTHONPATH: [
          resolve(backendRoot, 'tests'),
          resolve(backendRoot, 'src'),
        ].join(':'),
      },
    },
  )
  let failed = false
  backend.once('error', () => {
    failed = true
  })
  try {
    const deadline = Date.now() + 120_000
    while (!existsSync(ready)) {
      if (failed || backend.exitCode !== null || backend.signalCode !== null)
        throw new Error('実authority/controller/APIの起動に失敗')
      if (Date.now() > deadline) throw new Error('所有backend起動期限超過')
      await delay(100)
    }
    runtime = JSON.parse(readFileSync(ready, 'utf8')) as Runtime
    if (
      !Number.isInteger(runtime.port) ||
      runtime.port < 1 ||
      runtime.port > 65535
    )
      throw new Error('所有API portが不正')
    vite = await createServer({
      configFile: resolve(frontendRoot, 'vite.config.ts'),
      root: frontendRoot,
      envDir: false,
      server: {
        host: '127.0.0.1',
        port,
        strictPort: true,
        proxy: {
          '/api': {
            target: `http://127.0.0.1:${runtime.port}`,
            changeOrigin: true,
            rewrite: stripApiPrefix,
          },
        },
      },
    })
    await vite.listen()
  } catch (error) {
    await stopOwned().catch(() => undefined)
    throw error
  }
})

test.afterAll(async () => {
  test.setTimeout(180_000)
  await stopOwned()
})

function matches(response: Response, method: string, path: string): boolean {
  return (
    response.request().method() === method &&
    new URL(response.url()).pathname === path
  )
}

async function successful(
  response: Response,
  status: number,
): Promise<Response> {
  expect(response.status()).toBe(status)
  expect(response.headers()['cache-control']).toBe('no-store')
  expect(response.headers()['x-pitchlog-tenant-match']).toBe('1')
  expect(response.headers()['x-pitchlog-tenant-challenge']).toBe(
    response.request().headers()['x-pitchlog-tenant-challenge'],
  )
  return response
}

async function login(page: Page): Promise<void> {
  const identity = runtime.identities[0]
  if (!identity) throw new Error('所有認証fixtureがない')
  await page.goto(`${baseURL}/login?redirect=/games`)
  await expect(page.locator('form[aria-busy]')).toHaveAttribute(
    'aria-busy',
    'false',
  )
  await page.getByRole('textbox', { name: 'チーム名' }).fill(identity.name)
  await page.getByLabel('パスワード').fill(identity.password)
  const result = page.waitForResponse((response) =>
    matches(response, 'POST', '/api/auth/login'),
  )
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
  const response = await result
  expect(response.status()).toBe(200)
  expect((await response.json()).tenant_id).toBe(identity.tenantId)
  const retry = page.getByRole('button', { name: '状態を再確認', exact: true })
  await expect(
    page.getByRole('heading', { name: '準備中の試合' }).or(retry),
  ).toBeVisible()
  if (await retry.isVisible()) await retry.click()
  await expect(page).toHaveURL(`${baseURL}/games`)
  const cookies = await page.context().cookies()
  if (
    !cookies.some(
      (cookie) =>
        cookie.name === '__Host-pitchlog_token' &&
        cookie.domain === '127.0.0.1' &&
        cookie.path === '/' &&
        cookie.secure &&
        cookie.httpOnly,
    )
  )
    throw new Error('実loginで得たSecure/HttpOnly Cookieがない')
  expect(await page.evaluate(() => window.isSecureContext)).toBe(true)
}

test('画面で新試合を作成し一覧・詳細・reloadと実DBの全保存値を照合する', async ({
  page,
}) => {
  const posts: string[] = []
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      new URL(request.url()).pathname === '/api/games'
    )
      posts.push(request.url())
  })
  const firstList = page.waitForResponse((response) =>
    matches(response, 'GET', '/api/games'),
  )
  await login(page)
  expect((await (await successful(await firstList, 200)).json()).items).toEqual(
    [],
  )
  await page.getByRole('button', { name: '新規作成', exact: true }).click()
  const form = page.getByRole('region', { name: '試合の新規作成', exact: true })
  await expect(form.getByLabel('日時（日本時間）')).toBeEnabled()
  const input = {
    scheduled_at: '2026-10-24T13:45:00+09:00',
    game_type_key: 'game_open',
    away_team_record_id: runtime.teams[0],
    home_team_record_id: runtime.teams[1],
    tournament: { kind: 'new', display_name: ' 画面作成大会　' },
    plate_umpire: ' 実画面主審　',
    section_label: '<b>画面保存節</b>',
    week_label: '第2週',
    day_label: '第3日',
    game_number_label: '第4試合',
  }
  await form.getByLabel('日時（日本時間）').fill('2026-10-24T13:45')
  // label内のselectは選択肢の文言もaccessible nameへ含むので、固定入力IDとprefixを照合する。
  await expect(form.getByTestId('game-type')).toHaveAccessibleName(/^試合区分/)
  await form.getByTestId('game-type').selectOption(input.game_type_key)
  if (!input.away_team_record_id || !input.home_team_record_id)
    throw new Error('実選択肢の両team IDがない')
  await expect(form.getByTestId('away')).toHaveAccessibleName(/^先攻チーム/)
  await form.getByTestId('away').selectOption(input.away_team_record_id)
  await expect(form.getByTestId('home')).toHaveAccessibleName(/^後攻チーム/)
  await form.getByTestId('home').selectOption(input.home_team_record_id)
  await expect(form.getByTestId('tournament-kind')).toHaveAccessibleName(
    /^大会の指定/,
  )
  await form.getByTestId('tournament-kind').selectOption('new')
  await form
    .getByLabel('新しい大会名', { exact: true })
    .fill(input.tournament.display_name)
  await form
    .getByLabel('主審（任意）', { exact: true })
    .fill(input.plate_umpire)
  await form.getByLabel('節（任意）', { exact: true }).fill(input.section_label)
  await form.getByLabel('週（任意）', { exact: true }).fill(input.week_label)
  await form.getByLabel('日（任意）', { exact: true }).fill(input.day_label)
  await form
    .getByLabel('試合番号（任意）', { exact: true })
    .fill(input.game_number_label)
  const posted = page.waitForResponse((response) =>
    matches(response, 'POST', '/api/games'),
  )
  await form
    .getByRole('button', { name: '準備中の試合を作成', exact: true })
    .click()
  const response = await successful(await posted, 201)
  expect(response.request().postDataJSON()).toEqual(input)
  const saved = (await response.json()) as PreparingGame
  expect(saved.id).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
  )
  expect(saved.status).toBe('preparing')
  expect(Date.parse(saved.scheduled_at)).toBe(Date.parse(input.scheduled_at))
  for (const key of [
    'game_type_key',
    'away_team_record_id',
    'home_team_record_id',
    'plate_umpire',
    'section_label',
    'week_label',
    'day_label',
    'game_number_label',
  ] as const)
    expect(saved[key]).toBe(input[key])
  expect(saved.applied_rules).toBeTruthy()
  expect(Object.keys(saved.applied_rules).length).toBeGreaterThan(0)
  await expect(form).toContainText(`作成応答の試合ID：${saved.id}`)
  const path = `/api/games/${saved.id}`
  const confirmation = page.waitForResponse((reply) =>
    matches(reply, 'GET', path),
  )
  await form
    .getByRole('button', { name: '作成した試合IDの保存値を確認', exact: true })
    .click()
  expect(await (await successful(await confirmation, 200)).json()).toEqual(
    saved,
  )
  await expect(page).toHaveURL(`${baseURL}/games/${saved.id}/record`)
  await expect(page.locator('pre')).toHaveText(
    JSON.stringify(saved.applied_rules, null, 2),
  )
  const listing = page.waitForResponse((reply) =>
    matches(reply, 'GET', '/api/games'),
  )
  await page.getByRole('link', { name: '試合一覧へ', exact: true }).click()
  expect((await (await successful(await listing, 200)).json()).items).toEqual([
    saved,
  ])
  const list = page.getByRole('region', { name: '試合一覧', exact: true })
  await expect(list).toContainText(input.section_label)
  await expect(list.locator('b')).toHaveCount(0)
  const read = page.waitForResponse((reply) => matches(reply, 'GET', path))
  await list.getByRole('link', { name: '閲覧画面へ', exact: true }).click()
  expect(await (await successful(await read, 200)).json()).toEqual(saved)
  const reload = page.waitForResponse((reply) => matches(reply, 'GET', path))
  await page.reload()
  expect(await (await successful(await reload, 200)).json()).toEqual(saved)
  await expect(page).toHaveURL(`${baseURL}/games/${saved.id}/record`)
  await expect(page.locator('pre')).toHaveText(
    JSON.stringify(saved.applied_rules, null, 2),
  )
  await expect(page.locator('main').last()).toContainText(saved.id)
  await expect(page.locator('main').last()).toContainText(input.plate_umpire)
  await expect(page.locator('main').last()).toContainText(input.section_label)
  await expect(page.getByRole('button', { name: '1球を確定' })).toHaveCount(0)
  expect(posts).toHaveLength(1)
  const evidence = await stopOwned()
  expect(evidence?.game_count).toBe(1)
  expect(evidence?.activation_open_count).toBe(1)
  expect(evidence?.tournament_display_name).toBe(input.tournament.display_name)
  if (!evidence) throw new Error('実DBの保存観測がない')
  // PGのISO表記とHTTPのUTC表記は同じ瞬間として照合し、他の全保存値は完全一致させる。
  expect(Date.parse(evidence.game.scheduled_at)).toBe(
    Date.parse(saved.scheduled_at),
  )
  expect({ ...evidence.game, scheduled_at: saved.scheduled_at }).toEqual(saved)
})
