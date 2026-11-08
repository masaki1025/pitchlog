/** 実画面の3記録と30閲覧を同じ隔離サーバーで照合する。 */
import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import type { LineupPrefixGame } from '../api/lineupPrefixGame'
import {
  apiPath,
  baseURL,
  createAndStartRealGame,
  realLogin,
  recordRealPitch,
} from './RealGameRecording.e2e-support'

const results = [
  ['batting-result.ball', 'batting-result.ball'],
  ['batting-result.called-pitch', 'batting-result.called-pitch'],
  ['batting-result.swinging-strike', 'batting-result.ball'],
] as const

type Writer = { page: Page; head: LineupPrefixGame }
type Viewer = { page: Page; game: number; requests: string[] }

test('3試合の実記録と30閲覧が保存から10秒以内で同じ状態へ更新する', async ({
  browser,
}) => {
  if (!baseURL || new URL(baseURL).protocol !== 'https:')
    throw new Error('所有HTTPS環境が必要')
  const contexts: BrowserContext[] = []
  const writers: Writer[] = []
  const viewers: Viewer[] = []
  const cookies = new Set<string>()
  const writeTraffic: Array<{
    wave: number
    game: number
    start: number
    end: number
  }> = []
  const timings: Array<{
    wave: number
    game: number
    viewer: number
    milliseconds: number
  }> = []
  async function ownedPage(): Promise<Page> {
    const context = await browser.newContext({ ignoreHTTPSErrors: true })
    contexts.push(context)
    const page = await context.newPage()
    page.setDefaultTimeout(45_000)
    return page
  }
  async function distinctCookie(page: Page) {
    const cookie = (await page.context().cookies()).find(
      (c) => c.name === '__Host-pitchlog_token',
    )
    if (!cookie || cookies.has(cookie.value))
      throw new Error('独立した実認証Cookieが不足')
    cookies.add(cookie.value)
  }
  try {
    // 三つとも画面で新規作成する。fixture試合の読取で代用しない。
    for (let game = 0; game < 3; game++) {
      const page = await ownedPage()
      const created = await createAndStartRealGame(
        page,
        `同時閲覧試合${game + 1}`,
      )
      await distinctCookie(page)
      writers.push({ page, head: created.head })
    }
    expect(new Set(writers.map((w) => w.head.id)).size).toBe(3)
    for (let game = 0; game < 3; game++) {
      for (let index = 0; index < 10; index++) {
        const page = await ownedPage()
        await realLogin(page)
        await distinctCookie(page)
        const requests: string[] = []
        page.on('request', (request) => {
          if (apiPath(request.url()).startsWith('/api/'))
            requests.push(`${request.method()} ${apiPath(request.url())}`)
        })
        viewers.push({ page, game, requests })
      }
    }
    expect(cookies.size).toBe(33)
    await Promise.all(
      viewers.map(async ({ page, game }) => {
        await page.goto(`${baseURL}/games/${writers[game]!.head.id}/view`)
        await expect(page.getByTestId('viewer-status')).toHaveText('更新済み')
        await expect(
          page.getByTestId('viewer-server-only-notice'),
        ).toContainText('未送信分は含まれません')
        await expect(page.getByTestId('viewer-history')).toContainText(
          'まだ確定済みの投球はありません。',
        )
        await expect(
          page.getByTestId('viewer-lineup').locator('ol > li'),
        ).toHaveCount(18)
      }),
    )
    for (let wave = 1; wave <= 2; wave++) {
      // 先に全閲覧の自然更新を待ち始め、三つの実保存を並行して操作する。
      const visible = Promise.all(
        viewers.map(async ({ page }, viewer) => {
          await expect(
            page
              .getByTestId('viewer-history')
              .getByText(new RegExp(`第${wave}球:`)),
          ).toBeVisible({ timeout: 120_000 })
          return { viewer, at: Date.now() }
        }),
      )
      const overlapping = Promise.all(
        writers.map(async (writer, game) => {
          const requested = writer.page
            .waitForRequest(
              (request) =>
                request.method() === 'POST' &&
                apiPath(request.url()) ===
                  `/api/games/${writer.head.id}/sync/events`,
              { timeout: 120_000 },
            )
            .then(() => Date.now())
          const responded = writer.page
            .waitForResponse(
              (response) =>
                response.request().method() === 'POST' &&
                apiPath(response.url()) ===
                  `/api/games/${writer.head.id}/sync/events`,
              { timeout: 120_000 },
            )
            .then(() => Date.now())
          const [start, end] = await Promise.all([requested, responded])
          return { wave, game, start, end }
        }),
      )
      const recorded = Promise.all(
        writers.map(async (writer, game) => {
          const result = await recordRealPitch(
            writer.page,
            writer.head,
            results[game]![wave - 1]!,
            wave,
          )
          writer.head = result.head
          return result
        }),
      )
      const [seen, saved, traffic] = await Promise.all([
        visible,
        recorded,
        overlapping,
      ])
      expect(Math.max(...traffic.map((row) => row.start))).toBeLessThan(
        Math.min(...traffic.map((row) => row.end)),
      )
      writeTraffic.push(...traffic)
      expect(seen).toHaveLength(30)
      expect(saved).toHaveLength(3)
      for (const { viewer, at } of seen) {
        const item = viewers[viewer]!
        const head = saved[item.game]!.head
        const serverSavedAt = Date.parse(head.last_saved_at)
        const elapsed = at - serverSavedAt
        if (!Number.isFinite(serverSavedAt) || elapsed < 0 || elapsed > 10_000)
          throw new Error(
            `閲覧更新10秒条件未達 game=${item.game} viewer=${viewer} ms=${elapsed}`,
          )
        timings.push({ wave, game: item.game, viewer, milliseconds: elapsed })
        const state = head.after.stateFields
        const score = item.page.getByTestId('viewer-score')
        await expect(item.page.getByTestId('viewer-status')).toHaveText(
          '更新済み',
        )
        await expect(score).toContainText(
          `先攻 ${state['state.score'].away} – 後攻 ${state['state.score'].home}`,
        )
        await expect(score).toContainText('1回表')
        await expect(score).toContainText(`${state['state.outs']}アウト`)
        await expect(score).toContainText(
          `${state['state.count.balls']}ボール ${state['state.count.strikes']}ストライク`,
        )
        await expect(score).toContainText('走者: なし')
        await expect(
          item.page.getByTestId('viewer-history').locator('ol > li'),
        ).toHaveCount(wave)
        await expect(
          item.page
            .getByTestId('viewer-history')
            .locator('ol > li')
            .nth(wave - 1),
        ).toContainText(results[item.game]![wave - 1]!)
        await expect(
          item.page.getByTestId('viewer-lineup').locator('ol > li'),
        ).toHaveCount(18)
      }
    }
    for (const viewer of viewers) {
      expect(viewer.requests.length).toBeGreaterThan(0)
      expect(
        viewer.requests.every((request) => request.startsWith('GET ')),
      ).toBe(true)
      expect(
        viewer.requests.filter((request) =>
          /devices\/enroll|sync\/events|sync\/attempts\/recover|\/start$/.test(
            request,
          ),
        ),
      ).toEqual([])
    }
    expect(timings).toHaveLength(60)
    console.log(
      'PITCHLOG_VIEWER_THREE_GAME_RESULT=' +
        JSON.stringify({
          gameIds: writers.map((writer) => writer.head.id),
          gameResults: results,
          writers: 3,
          viewers: 30,
          independentContexts: contexts.length,
          waves: 2,
          timings,
          writeTraffic,
          viewerRequests: viewers.map((viewer) => viewer.requests.length),
        }),
    )
  } finally {
    await Promise.all(
      contexts.map((context) => context.close().catch(() => undefined)),
    )
  }
})
