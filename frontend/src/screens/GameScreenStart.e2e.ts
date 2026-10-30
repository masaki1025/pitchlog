import { expect, test, type Page } from '@playwright/test'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const game = process.env.PITCHLOG_E2E_GAME_ID
if (!baseURL || !team || !password || !game)
  throw new Error('E2Eの実app資格がenvにない')

function apiPath(url: string): string {
  return new URL(url).pathname
}

async function loginFromRedirect(page: Page): Promise<string> {
  // 未認証で記録画面へ入り、guardが返すloginへ実フォームで認証する。
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

function waitPath(page: Page, method: string, path: string) {
  return page.waitForResponse(
    (res) => res.request().method() === method && apiPath(res.url()) === path,
    { timeout: 60_000 },
  )
}

test('実画面で端末登録・開始し、実APIの開始済み状態が返る', async ({
  page,
}) => {
  const bad: string[] = []
  page.on('response', (response) => {
    if (response.url().includes('/api/') && response.status() >= 400)
      bad.push(`${response.status()} ${apiPath(response.url())}`)
  })
  try {
    const detail = waitPath(page, 'GET', `/api/games/${game}`)
    await page.goto(`${baseURL}/games/${game}/record`)
    const tenant = await loginFromRedirect(page)
    const saved = (await (await detail).json()) as {
      applied_rules: { dh: boolean }
    }
    console.log('STEP detail')
    await expect(
      page.getByRole('heading', { name: 'スタメンと試合開始' }),
    ).toBeVisible()
    await page.getByRole('button', { name: 'この端末を登録' }).click()
    await expect(page.getByText('開始入力を確認できます')).toBeVisible()
    console.log('STEP enrolled')
    const form = page.locator('form').filter({ hasText: '試合を開始' })
    await expect(form).toBeVisible()
    const dh = saved.applied_rules.dh === true
    for (const side of ['away', 'home'] as const) {
      const rows = dh ? 10 : 9
      for (let index = 0; index < rows; index += 1) {
        await page
          .locator(`#start-${side}-${index}-player`)
          .selectOption({ index: index + 1 })
        // DH時は1〜9番に8守備位置＋DH、10行目が投手専用。重複位置を作らない。
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
    console.log('STEP lineup')
    const started = waitPath(page, 'POST', `/api/games/${game}/start`)
    await page.getByRole('button', { name: '試合を開始', exact: true }).click()
    const response = await started
    if (response.status() !== 200) throw new Error('実start POSTが成功しない')
    const body = (await response.json()) as { game_id: string }
    expect(body.game_id).toBe(game)
    console.log('STEP started')
    // 画面と同じorigin・同じCookieで、開始済み状態を実fetchする。
    const read = await page.evaluate(
      async (value) => {
        const response = await fetch(`/api/games/${value.game}/started`, {
          headers: {
            'X-Pitchlog-Expected-Tenant': value.tenant,
            'X-Pitchlog-Tenant-Challenge': crypto.randomUUID(),
            'X-Pitchlog-Request': '1',
          },
        })
        return { status: response.status, text: await response.text() }
      },
      { game: game!, tenant },
    )
    if (read.status !== 200)
      throw new Error(`started=${read.status} body=${read.text.slice(0, 300)}`)
    const view = JSON.parse(read.text) as {
      read_kind: string
      id: string
      state: { stateFields: Record<string, string> }
    }
    expect(view.read_kind).toBe('initial')
    expect(view.id).toBe(game)
    expect(view.state.stateFields['state.count.balls']).toBe('0')
    expect(view.state.stateFields['state.count.strikes']).toBe('0')
    expect(view.state.stateFields['state.outs']).toBe('0')
    await expect(page.getByText(/開始日時/)).toBeVisible()
    console.log('STEP read')
  } catch (error) {
    const text = await page
      .locator('body')
      .innerText()
      .catch(() => '(本文なし)')
    throw new Error(
      `ORIG=${String(error)} URL=${page.url()} BAD=${bad.join(',')} TEXT=${text.slice(0, 600)}`,
    )
  }
})
