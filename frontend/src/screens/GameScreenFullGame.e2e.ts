/** 通常9回の機能通し。性能未達・他操作未実装をMVP完成へ読み替えない。 */
import { expect, test } from '@playwright/test'
import {
  apiPath,
  createAndStartRealGame,
  recordRealPitch,
} from './RealGameRecording.e2e-support'

test('実画面で9回・163球を保存し終了確定版をreloadする', async ({ page }) => {
  page.setDefaultTimeout(30_000)
  const { game, head: initial } = await createAndStartRealGame(
    page,
    '通常9回通し検証',
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
  for (let pitch = 1; pitch <= 162; pitch += 1) {
    const result = await recordRealPitch(
      page,
      head,
      pitch % 3 === 0
        ? 'batting-result.called-strikeout'
        : 'batting-result.called-pitch',
      pitch + 1,
    )
    head = result.head
    times.push(result.elapsedMs)
    expect(head.after.stateFields['state.score']).toEqual({
      away: '1',
      home: '0',
    })
    expect(head.after.stateFields['state.runners']).toBe('empty')
    if (pitch % 9 === 0) {
      const halves = pitch / 9
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
    if (pitch === 81) {
      await page.reload()
      await expect(page.getByTestId('restore-history')).toHaveText('82件')
      await expect(page.getByTestId('ordinary-state-source')).toHaveText(
        'サーバー確認済み',
      )
    }
  }
  expect(head.prefix_ref.length).toBe('163')
  expect(head.t2?.decision.outcome).toBe('normal-end')
  expect(head.after.scoreboard.strikeouts).toBe('54')
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
  console.log(
    'PITCHLOG_FULL_GAME_FINAL=' +
      JSON.stringify({
        gameId: game.id,
        plays: 163,
        completedHalves: 18,
        score: { away: '1', home: '0' },
        finalVersion: 1,
        performance: {
          thresholdMs: 5000,
          maximumMs: Math.max(...times),
          overThresholdCount: times.filter((ms) => ms > 5000).length,
        },
        scope: 'normal-nine-inning-functional-only',
      }),
  )
})
