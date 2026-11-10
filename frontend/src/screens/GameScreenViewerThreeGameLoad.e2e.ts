import {
  observeCompleteViewerSnapshot,
  type ViewerSnapshotExpectation,
} from './viewerThreeGameSnapshot.e2e-support'
/** 実画面の3記録と30閲覧を同じ隔離サーバーで照合する。 */
import { writeFileSync } from 'node:fs'
import { isAbsolute } from 'node:path'
import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import type { LineupPrefixGame } from '../api/lineupPrefixGame'
import {
  apiPath,
  baseURL,
  createAndStartRealGame,
  realLogin,
  recordRealPitch,
} from './RealGameRecording.e2e-support'

function loadCount(name: string, fallback: number): number {
  const raw = process.env[name]
  if (raw === undefined) return fallback
  const value = Number(raw)
  if (!Number.isInteger(value) || value < 0)
    throw new Error(`${name} は0以上の整数が必要`)
  return value
}
const gameCount = loadCount('PITCHLOG_VIEWER_LOAD_GAMES', 3)
const viewersPerGame = loadCount('PITCHLOG_VIEWER_LOAD_VIEWERS_PER_GAME', 10)

const results = [
  ['batting-result.ball', 'batting-result.ball'],
  ['batting-result.called-pitch', 'batting-result.called-pitch'],
  ['batting-result.swinging-strike', 'batting-result.ball'],
] as const

const countTargets = [
  [
    { balls: '1', strikes: '0' },
    { balls: '2', strikes: '0' },
  ],
  [
    { balls: '0', strikes: '1' },
    { balls: '0', strikes: '2' },
  ],
  [
    { balls: '0', strikes: '1' },
    { balls: '1', strikes: '1' },
  ],
] as const

/** 同じbrowser callbackをJSdomでも検査し、後段waitで成功を補完しない。 */
function completeViewerSnapshot(
  page: Page,
  expected: ViewerSnapshotExpectation,
) {
  return page.evaluate(observeCompleteViewerSnapshot, expected)
}

type Writer = { page: Page; head: LineupPrefixGame }
type Viewer = { page: Page; game: number; requests: string[] }

test('3試合の実記録と30閲覧が保存から10秒以内で同じ状態へ更新する', async ({
  browser,
}) => {
  if (!baseURL || new URL(baseURL).protocol !== 'https:')
    throw new Error('所有HTTPS環境が必要')
  const gameEvidence = process.env.PITCHLOG_VIEWER_LOAD_GAME_PATH
  if (!gameEvidence || !isAbsolute(gameEvidence))
    throw new Error('当runの試合証拠先が必要')
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
    page.on('pageerror', (error) =>
      console.log('PITCHLOG_VIEWER_PAGEERROR=' + error.message),
    )
    page.on('console', (message) => {
      if (message.type() === 'error')
        console.log(
          'PITCHLOG_VIEWER_CONSOLE=' +
            message.text().slice(0, 300) +
            ' url=' +
            message.location().url,
        )
    })
    await page.addInitScript(() => {
      const scope = globalThis as {
        __pitchlogE2eDiagnostics?: boolean
        __pitchlogHeartbeat?: { last: number; maxGap: number }
      }
      scope.__pitchlogE2eDiagnostics = true
      scope.__pitchlogHeartbeat = { last: Date.now(), maxGap: 0 }
      window.setInterval(() => {
        const heartbeat = scope.__pitchlogHeartbeat
        if (!heartbeat) return
        const now = Date.now()
        heartbeat.maxGap = Math.max(heartbeat.maxGap, now - heartbeat.last)
        heartbeat.last = now
      }, 200)
    })
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
    for (let game = 0; game < gameCount; game++) {
      const page = await ownedPage()
      const created = await createAndStartRealGame(
        page,
        `同時閲覧試合${game + 1}`,
      )
      await distinctCookie(page)
      writers.push({ page, head: created.head })
      writeFileSync(
        gameEvidence,
        JSON.stringify({ gameIds: writers.map((writer) => writer.head.id) }),
      )
    }
    expect(new Set(writers.map((w) => w.head.id)).size).toBe(gameCount)
    for (let game = 0; game < gameCount; game++) {
      for (let index = 0; index < viewersPerGame; index++) {
        const page = await ownedPage()
        await realLogin(page, `/games/${writers[game]!.head.id}/view`)
        await distinctCookie(page)
        const requests: string[] = []
        page.on('request', (request) => {
          if (apiPath(request.url()).startsWith('/api/'))
            requests.push(`${request.method()} ${apiPath(request.url())}`)
        })
        viewers.push({ page, game, requests })
      }
    }
    expect(cookies.size).toBe(gameCount + gameCount * viewersPerGame)
    await Promise.all(
      viewers.map(async ({ page }) => {
        // loginのredirect先をviewerへ向け、記録画面の一覧/詳細readを挟まない。
        // 30閲覧の初回loadはcold startを含む。保存後10秒の更新期限は
        // completeViewerSnapshot側で別に測る。
        await expect(page.getByTestId('viewer-status')).toHaveText('更新済み', {
          // 初回cold startは10秒更新条件と別。artifact再pin後のVite初回変換を含む。
          timeout: 60_000,
        })
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
        viewers.map(async ({ page, game }, viewer) => {
          const snapshot = await completeViewerSnapshot(page, {
            wave,
            result: results[game]![wave - 1]!,
            ...countTargets[game]![wave - 1]!,
          })
          return { viewer, snapshot }
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
          const traffic: {
            request: number | null
            response: number | null
            failure: string | null
          } = { request: null, response: null, failure: null }
          const onRequest = (request: import('@playwright/test').Request) => {
            if (
              request.method() === 'POST' &&
              apiPath(request.url()) ===
                `/api/games/${writer.head.id}/sync/events`
            )
              traffic.request = Date.now()
          }
          const onResponse = (
            response: import('@playwright/test').Response,
          ) => {
            if (
              response.request().method() === 'POST' &&
              apiPath(response.url()) ===
                `/api/games/${writer.head.id}/sync/events`
            )
              traffic.response = Date.now()
          }
          const onFailed = (request: import('@playwright/test').Request) => {
            if (
              request.method() === 'POST' &&
              apiPath(request.url()) ===
                `/api/games/${writer.head.id}/sync/events`
            )
              traffic.failure = request.failure()?.errorText ?? 'unknown'
          }
          writer.page.on('request', onRequest)
          writer.page.on('response', onResponse)
          writer.page.on('requestfailed', onFailed)
          try {
            const result = await recordRealPitch(
              writer.page,
              writer.head,
              results[game]![wave - 1]!,
              wave,
            )
            writer.head = result.head
            return result
          } catch (error) {
            // 45秒の内訳を、送信前停止・main thread starvation・HTTP待ちへ分ける。
            const diagnostic = await writer.page
              .evaluate(() => {
                const scope = globalThis as {
                  __pitchlogSaveEnteredAt?: number
                  __pitchlogSaveEnteredStatus?: Record<string, unknown>
                  __pitchlogSubmitError?: string
                  __pitchlogSubmitDetail?: string
                  __pitchlogLastObservation?: string
                  __pitchlogHeartbeat?: { last: number; maxGap: number }
                }
                return {
                  saveEnteredAt: scope.__pitchlogSaveEnteredAt ?? null,
                  saveEnteredStatus: scope.__pitchlogSaveEnteredStatus ?? null,
                  submitError: scope.__pitchlogSubmitError ?? null,
                  submitDetail: scope.__pitchlogSubmitDetail ?? null,
                  observation: scope.__pitchlogLastObservation ?? null,
                  heartbeat: scope.__pitchlogHeartbeat ?? null,
                  now: Date.now(),
                  status:
                    document.querySelector('[data-testid="first-ball-status"]')
                      ?.textContent ?? null,
                  stateSource:
                    document.querySelector(
                      '[data-testid="ordinary-state-source"]',
                    )?.textContent ?? null,
                  readyState: document.readyState,
                }
              })
              .catch((reason: unknown) => ({ evaluateError: String(reason) }))
            throw new Error(
              `wave ${wave} game ${game} writer save failed: ${String(error)}\n` +
                `PITCHLOG_VIEWER_LOAD_WRITER_DIAGNOSTIC=${JSON.stringify({
                  ...diagnostic,
                  http: traffic,
                })}`,
            )
          } finally {
            writer.page.off('request', onRequest)
            writer.page.off('response', onResponse)
            writer.page.off('requestfailed', onFailed)
          }
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
      expect(seen).toHaveLength(gameCount * viewersPerGame)
      expect(saved).toHaveLength(gameCount)
      for (const { viewer, snapshot } of seen) {
        const item = viewers[viewer]!
        const head = saved[item.game]!.head
        expect(snapshot.savedAt).toBe(head.last_saved_at)
        // last_saved_atは保存TX内の刻印でcommit前。利用者の「保存から」は
        // writerのACK応答時刻を起点に測る。
        const acknowledged = traffic.find(
          (row) => row.wave === wave && row.game === item.game,
        )
        if (!acknowledged) throw new Error('保存ACKの時刻がありません')
        const elapsed = snapshot.at - acknowledged.end
        if (elapsed < 0 || elapsed > 10_000)
          throw new Error(
            `閲覧全表示10秒条件未達 game=${item.game} viewer=${viewer} ms=${elapsed}`,
          )
        timings.push({ wave, game: item.game, viewer, milliseconds: elapsed })
        const state = head.after.stateFields
        expect(snapshot.status).toBe('更新済み')
        expect(snapshot.score).toContain(
          `先攻 ${state['state.score'].away} – 後攻 ${state['state.score'].home}`,
        )
        expect(snapshot.score).toContain(`${state['state.inning']}回表`)
        expect(snapshot.score).toContain(`${state['state.outs']}アウト`)
        expect(snapshot.score).toContain(
          `${state['state.count.balls']}ボール ${state['state.count.strikes']}ストライク`,
        )
        expect(snapshot.score).toContain('走者: なし')
        expect(snapshot.history).toHaveLength(wave)
        expect(snapshot.history[wave - 1]).toContain(
          results[item.game]![wave - 1]!,
        )
        expect(snapshot.lineup).toHaveLength(18)
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
    expect(timings).toHaveLength(gameCount * viewersPerGame * 2)
    console.log(
      'PITCHLOG_VIEWER_THREE_GAME_RESULT=' +
        JSON.stringify({
          gameIds: writers.map((writer) => writer.head.id),
          gameResults: results.slice(0, gameCount),
          writers: gameCount,
          viewers: gameCount * viewersPerGame,
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
