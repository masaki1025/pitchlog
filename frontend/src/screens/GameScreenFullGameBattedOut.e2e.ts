/** 9回55プレイと終了版の成績/CSV通し。性能未達・他操作未実装をMVP完成へ読み替えない。 */
import { expect, test } from '@playwright/test'
import { lstatSync, writeFileSync } from 'node:fs'
import { isAbsolute, resolve, basename } from 'node:path'
import { createHash } from 'node:crypto'
import {
  apiPath,
  baseURL,
  createAndStartRealGame,
  recordRealPitch,
} from './RealGameRecording.e2e-support'

test('実画面で9回・55プレイを保存し終了確定版をreloadする', async ({
  page,
}) => {
  page.setDefaultTimeout(30_000)
  const selfTeam = process.env.PITCHLOG_E2E_SELF_TEAM
  if (!selfTeam) throw new Error('実fixtureの自チームIDが不足')
  const { game, head: initial } = await createAndStartRealGame(
    page,
    '九回凡打成績CSV通し',
  )
  let head = initial
  const times: number[] = []
  const opening = await recordRealPitch(
    page,
    head,
    'batting-result.home-run',
    1,
  )
  head = opening.head
  times.push(opening.elapsedMs)
  expect(head.after.stateFields['state.score']).toEqual({
    away: '1',
    home: '0',
  })
  expect(head.after.stateFields['state.runners']).toBe('empty')
  expect(head.after.scoreboard.hits).toBe('1')
  for (let pitch = 1; pitch <= 54; pitch += 1) {
    const result = await recordRealPitch(
      page,
      head,
      'batting-result.batted-out',
      pitch + 1,
    )
    head = result.head
    times.push(result.elapsedMs)
    expect(head.after.stateFields['state.score']).toEqual({
      away: '1',
      home: '0',
    })
    expect(head.after.stateFields['state.runners']).toBe('empty')
    if (pitch % 3 === 0) {
      const halves = pitch / 3
      console.log(
        'PITCHLOG_FULL_GAME_HALF=' +
          JSON.stringify({
            completedHalves: halves,
            recordedPitches: pitch + 1,
            afterInning: head.after.stateFields['state.inning'],
            afterHalf: head.after.stateFields['state.half'],
            t2: head.t2?.decision.outcome,
          }),
      )
      expect(head.after.stateFields['state.outs']).toBe('0')
      if (halves < 18) {
        expect(head.after.stateFields['state.half']).toBe(
          halves % 2 ? 'bottom' : 'top',
        )
        expect(head.after.stateFields['state.inning']).toBe(
          String(Math.floor(halves / 2) + 1),
        )
      }
    }
    if (pitch === 27) {
      await page.reload()
      await expect(page.getByTestId('restore-history')).toHaveText('28件')
      await expect(page.getByTestId('ordinary-state-source')).toHaveText(
        'サーバー確認済みの状態',
      )
    }
  }
  expect(head.prefix_ref.length).toBe('55')
  expect(head.t2?.decision.outcome).toBe('normal-end')
  expect(head.after.scoreboard.strikeouts).toBe('0')
  expect(head.after.scoreboard.hits).toBe('1')
  expect(head.after.scoreboard.walks).toBe('0')
  expect(head.after.battingOrderBySide).toEqual({ away: '2', home: '1' })
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
    expect(value.checkpoint.content.d3).toBe('56')
    return value
  }
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
    'PITCHLOG_FULL_GAME_BATTED_FINAL=' +
      JSON.stringify({
        gameId: game.id,
        plays: 55,
        completedHalves: 18,
        score: { away: '1', home: '0' },
        finalVersion: 1,
        performance: {
          thresholdMs: 5000,
          maximumMs: Math.max(...times),
          overThresholdCount: times.filter((ms) => ms > 5000).length,
        },
        scope: 'nine-inning-55play-stats-csv-candidate',
      }),
  )
})
