/** 9回59プレイと終了版の成績/CSV通し。性能未達・他操作未実装をMVP完成へ読み替えない。 */
import { expect, test } from '@playwright/test'
import { lstatSync, writeFileSync } from 'node:fs'
import { isAbsolute, resolve, basename } from 'node:path'
import { createHash } from 'node:crypto'
import {
  apiPath,
  baseURL,
  createAndStartRealGame,
  nextRecordedHead,
} from './RealGameRecording.e2e-support'
import {
  recordBattedOperation,
  type BattedStep,
} from './BattedOperations.e2e-support'

test('実画面で打球群59プレイを保存し終了成績CSVを照合する', async ({
  page,
}) => {
  page.setDefaultTimeout(30_000)
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    let saved: { input: RequestInfo | URL; init: RequestInit } | null = null
    window.fetch = async (input, init) => {
      const path = new URL(
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url,
        location.href,
      ).pathname
      if (
        init?.method === 'POST' &&
        /\/games\/[^/]+\/sync\/events$/.test(path) &&
        typeof init.body === 'string'
      )
        saved = {
          input,
          init: {
            ...init,
            headers: new Headers(init.headers),
            body: init.body,
          },
        }
      return original(input, init)
    }
    Object.defineProperty(window, '__replayBattedBatch', {
      value: async () => {
        if (!saved) throw new Error('原要求がない')
        const response = await original(saved.input, {
          ...saved.init,
          signal: AbortSignal.timeout(30000),
        })
        const body = await response.json()
        return { status: response.status, a5: body.eventResults?.[0]?.a5Result }
      },
    })
  })
  const selfTeam = process.env.PITCHLOG_E2E_SELF_TEAM
  if (!selfTeam) throw new Error('実fixtureの自チームIDが不足')
  const { game, head: initial } = await createAndStartRealGame(
    page,
    '打球群九回成績CSV通し',
  )
  let head = initial
  const times: number[] = []
  const recordedRows: unknown[] = []
  const steps: BattedStep[] = [
    {
      result: 'single',
      outs: '0',
      runners: 'first',
      half: 'top',
      inning: '1',
      score: { away: '0', home: '0' },
    },
    {
      result: 'batted-out',
      destinations: { '1': 'hold' },
      outs: '1',
      runners: 'first',
      half: 'top',
      inning: '1',
      score: { away: '0', home: '0' },
    },
    {
      result: 'sacrifice-bunt',
      destinations: { '1': '2' },
      outs: '2',
      runners: 'second',
      half: 'top',
      inning: '1',
      score: { away: '0', home: '0' },
    },
    {
      result: 'single',
      destinations: { '2': '4' },
      causes: { '2': 'stopped-and-restarted' },
      outs: '2',
      runners: 'first',
      half: 'top',
      inning: '1',
      score: { away: '1', home: '0' },
    },
    {
      result: 'batted-out',
      destinations: { '1': 'hold' },
      outs: '0',
      runners: 'empty',
      half: 'bottom',
      inning: '1',
      score: { away: '1', home: '0' },
    },
    {
      result: 'single',
      outs: '0',
      runners: 'first',
      half: 'bottom',
      inning: '1',
      score: { away: '1', home: '0' },
    },
    {
      result: 'double-play',
      outs: '2',
      runners: 'empty',
      half: 'bottom',
      inning: '1',
      score: { away: '1', home: '0' },
    },
    {
      result: 'batted-out',
      outs: '0',
      runners: 'empty',
      half: 'top',
      inning: '2',
      score: { away: '1', home: '0' },
    },
    {
      result: 'single',
      outs: '0',
      runners: 'first',
      half: 'top',
      inning: '2',
      score: { away: '1', home: '0' },
    },
    {
      result: 'fielders-choice',
      destinations: { '1': '2' },
      outs: '0',
      runners: 'first-second',
      half: 'top',
      inning: '2',
      score: { away: '1', home: '0' },
    },
    {
      result: 'error',
      destinations: { '1': '2', '2': '3' },
      outs: '0',
      runners: 'first-second-third',
      half: 'top',
      inning: '2',
      score: { away: '1', home: '0' },
    },
    {
      result: 'sacrifice-fly',
      destinations: { '1': 'hold', '2': 'hold', '3': '4' },
      causes: { '3': 'ordinary-play' },
      outs: '1',
      runners: 'first-second',
      half: 'top',
      inning: '2',
      score: { away: '2', home: '0' },
    },
    {
      result: 'sacrifice-bunt',
      destinations: { '1': '2', '2': '3' },
      outs: '2',
      runners: 'second-third',
      half: 'top',
      inning: '2',
      score: { away: '2', home: '0' },
    },
    {
      result: 'batted-out',
      destinations: { '2': 'hold', '3': 'hold' },
      outs: '0',
      runners: 'empty',
      half: 'bottom',
      inning: '2',
      score: { away: '2', home: '0' },
    },
  ]
  for (let count = 1; count <= 59; count += 1) {
    let step = steps[count - 1]
    if (!step) {
      const completed = 9 + count - 14
      const isThird = completed % 3 === 0
      const halves = Math.floor(completed / 3)
      step = {
        result: 'batted-out',
        outs: String(completed % 3),
        runners: 'empty',
        half: isThird && halves === 18 ? null : halves % 2 ? 'bottom' : 'top',
        inning:
          isThird && halves === 18 ? null : String(Math.floor(halves / 2) + 1),
        score: { away: '2', home: '0' },
      }
    }
    const result = await recordBattedOperation(
      page,
      head,
      { ...step, result: 'batting-result.' + step.result },
      count,
    )
    head = result.head
    times.push(result.elapsedMs)
    const item = head.page.items.find(
      (item) => item.play_row.play_number === count,
    )
    if (!item) throw new Error('保存済み当該playの実DTOがない')
    recordedRows.push(item)
    if (count === 2) {
      const before = head
      const duplicate = await page.evaluate(async () => {
        const replay = (
          window as unknown as {
            __replayBattedBatch: () => Promise<{ status: number; a5: string }>
          }
        ).__replayBattedBatch
        return replay()
      })
      expect(duplicate).toEqual({ status: 200, a5: '重複' })
      const restored = await page.request.get(
        new URL(
          `/api/games/${game.id}/started?projection=play-prefix-v3`,
          baseURL,
        ).href,
      )
      expect(restored.status()).toBe(200)
      const value = await restored.json()
      expect(value.prefix_ref).toEqual(before.prefix_ref)
      expect(value.after).toEqual(before.after)
      expect(value.page.items).toEqual(before.page.items)
    }
    if (count === 14) {
      const after = head.after
      const read = nextRecordedHead(page, game.id, count)
      await page.reload()
      const restored = (await (await read).json()) as typeof head
      expect(restored.after).toEqual(after)
      expect(restored.runners).toEqual(head.runners)
      head = restored
    }
  }
  expect(head.prefix_ref.length).toBe('59')
  expect(head.t2?.decision.outcome).toBe('normal-end')
  expect(head.after.scoreboard.hits).toBe('4')
  expect(head.after.scoreboard.errors).toBe('1')
  const lifecycle = page.getByTestId('lifecycle-product')
  await lifecycle.getByTestId('lifecycle-refresh').click()
  for (const box of await lifecycle.locator('input[type=checkbox]').all())
    await box.check()
  await expect(lifecycle.getByTestId('lifecycle-confirmed-status')).toHaveText(
    '進行中',
  )
  const ended = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${game.id}/sync/events`,
  )
  await lifecycle.getByTestId('lifecycle-end').click()
  const response = await ended
  expect(response.status()).toBe(200)
  const ack = await response.json()
  expect(ack.eventResults?.[0]?.a5Result).toBe('受理')
  await expect(lifecycle.getByTestId('lifecycle-confirmed-status')).toHaveText(
    '終了',
  )
  await expect(lifecycle.getByTestId('lifecycle-last-version')).toHaveText('v1')
  await page.reload()
  await expect(lifecycle.getByTestId('lifecycle-confirmed-status')).toHaveText(
    '終了',
  )
  await expect(lifecycle.getByTestId('lifecycle-last-version')).toHaveText('v1')
  // 記録は全てUIから行う。終了後の値は実Cookieの実APIだけを使う。
  const evidence = process.env.PITCHLOG_FULLGAME_EVIDENCE_DIR
  if (
    !evidence ||
    !isAbsolute(evidence) ||
    !basename(evidence).startsWith('full-game-batted-')
  )
    throw new Error('自分専用の実証出力先がない')
  const stat = lstatSync(evidence)
  if (
    !stat.isDirectory() ||
    stat.uid !== process.getuid?.() ||
    (stat.mode & 0o777) !== 0o700
  )
    throw new Error('実証出力先の所有/権限が不正')
  async function fetchJson(path: string, filename: string) {
    const response = await page.request.get(new URL(path, baseURL).href)
    expect(response.status()).toBe(200)
    const value = await response.json()
    expect(value.next_cursor).toBeNull()
    writeFileSync(resolve(evidence!, filename), JSON.stringify(value), {
      flag: 'wx',
      mode: 0o600,
    })
    return value
  }
  async function finalHead() {
    const response = await page.request.get(
      new URL(
        '/api/games/' +
          game.id +
          '/started?projection=lifecycle-prefix-v1&limit=25',
        baseURL,
      ).href,
    )
    expect(response.status()).toBe(200)
    const value = await response.json()
    expect(value.status).toBe('finished')
    expect(value.lifecycle.lastVersion).toBe('1')
    expect(value.checkpoint.content.d3).toBe('60')
    return value
  }
  writeFileSync(
    resolve(evidence, 'recorded-rows.json'),
    JSON.stringify(recordedRows),
    { flag: 'wx', mode: 0o600 },
  )
  const finalBeforeExports = await finalHead()
  writeFileSync(
    resolve(evidence, 'final-head.json'),
    JSON.stringify(finalBeforeExports),
    { flag: 'wx', mode: 0o600 },
  )
  const gameStats = await fetchJson(
    '/api/games/' + game.id + '/stats?mode=official&limit=200',
    'game-stats.json',
  )
  expect(gameStats.game_id).toBe(game.id)
  expect(gameStats.mode).toBe('official')
  expect(gameStats.players.length).toBeGreaterThan(0)
  const season = await fetchJson(
    '/api/stats/seasons/2026?category=practice&limit=200',
    'season-stats.json',
  )
  expect(season.year).toBe(2026)
  expect(season.category).toBe('practice')
  const all = await fetchJson(
    '/api/stats/seasons/2026?category=all&limit=200',
    'season-all.json',
  )
  const official = await fetchJson(
    '/api/stats/seasons/2026?category=official&limit=200',
    'season-official.json',
  )
  expect(official.players).toEqual([]) // 作成区分game_otherは既D02の練習。
  function sorted(players: Array<{ player_id: string }>) {
    return [...players].sort((a, b) => a.player_id.localeCompare(b.player_id))
  }
  const selfPlayers = gameStats.players.filter(
    (p: { team_record_id: string }) => p.team_record_id === selfTeam,
  )
  expect(selfPlayers.length).toBeGreaterThan(0)
  expect(sorted(season.players)).toEqual(sorted(selfPlayers))
  expect(sorted(all.players)).toEqual(sorted(selfPlayers))
  for (const [path, filename] of [
    ['/api/games/' + game.id + '/stats.csv?mode=official', 'game-stats.csv'],
    ['/api/stats/seasons/2026/stats.csv?category=practice', 'season-stats.csv'],
    ['/api/games/' + game.id + '/exports/plays.zip', 'plays.zip'],
  ]) {
    const response = await page.request.get(new URL(path!, baseURL).href)
    expect(response.status()).toBe(200)
    const data = await response.body()
    expect(data.length).toBeGreaterThan(0)
    if (filename === 'plays.zip') {
      expect(response.headers()['content-length']).toBe(String(data.length))
      expect(response.headers()['x-pitchlog-archive-sha256']).toBe(
        createHash('sha256').update(data).digest('hex'),
      )
    } else expect([...data.subarray(0, 3)]).toEqual([239, 187, 191])
    writeFileSync(resolve(evidence, filename!), data, {
      flag: 'wx',
      mode: 0o600,
    })
  }
  const finalAfterExports = await finalHead()
  expect(finalAfterExports.checkpoint).toEqual(finalBeforeExports.checkpoint)
  expect(finalAfterExports.lifecycle).toEqual(finalBeforeExports.lifecycle)
  expect(finalAfterExports.after).toEqual(finalBeforeExports.after)
  console.log(
    'PITCHLOG_BATTED_BATCH_FINAL=' +
      JSON.stringify({
        gameId: game.id,
        plays: 59,
        completedHalves: 18,
        score: { away: '2', home: '0' },
        finalVersion: 1,
        performance: {
          thresholdMs: 5000,
          maximumMs: Math.max(...times),
          overThresholdCount: times.filter((ms) => ms > 5000).length,
        },
        scope: 'nine-inning-59play-batted-family-candidate',
      }),
  )
})
