/** 9回消化後のタイブレーク開始・生還・投手交代・次半回再配置を実画面で通す。 */
import { expect, test, type Page } from '@playwright/test'
import type { LineupPrefixGame } from '../api/lineupPrefixGame'
import {
  apiPath,
  createAndStartRealGame,
  recordRealPitch,
} from './RealGameRecording.e2e-support'

const benchPitcher = process.env.PITCHLOG_E2E_BENCH_PITCHER
if (!benchPitcher) throw new Error('タイブレークE2Eの控え投手IDがない')

async function recordOuts(
  page: Page,
  head: LineupPrefixGame,
  count: number,
  outs: number,
) {
  let current = head
  let nextCount = count
  for (let out = 0; out < outs; out += 1) {
    const result = await recordRealPitch(
      page,
      current,
      'batting-result.batted-out',
      nextCount,
    )
    current = result.head
    nextCount += 1
  }
  return { head: current, count: nextCount }
}

async function scorelessInning(
  page: Page,
  head: LineupPrefixGame,
  count: number,
) {
  const top = await recordOuts(page, head, count, 3)
  const bottom = await recordOuts(page, top.head, top.count, 3)
  return { head: bottom.head, count: bottom.count }
}

async function startTiebreak(page: Page, gameId: string) {
  const panel = page.getByTestId('tiebreak-start-panel')
  await expect(panel).toBeVisible()
  await panel.getByTestId('tiebreak-first-runner').selectOption({ index: 1 })
  await panel.getByTestId('tiebreak-second-runner').selectOption({ index: 2 })
  await expect(panel.getByTestId('tiebreak-start-apply')).toBeEnabled()
  const posted = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${gameId}/sync/events`,
  )
  await panel.getByTestId('tiebreak-start-apply').click()
  const response = await posted
  expect(response.status()).toBe(200)
  expect((await response.json()).eventResults?.[0]?.a5Result).toBe('受理')
  await expect(panel).toHaveCount(0)
}

async function currentRead(page: Page, gameId: string, tenant: string) {
  return page.evaluate(
    async ({ id, tenantId }) => {
      const response = await fetch(
        `/api/games/${id}/started?projection=play-prefix-v3&limit=100`,
        {
          credentials: 'same-origin',
          headers: {
            'X-Pitchlog-Expected-Tenant': tenantId,
            'X-Pitchlog-Tenant-Challenge': crypto.randomUUID(),
          },
        },
      )
      if (response.status !== 200) return { status: response.status }
      return { status: 200, body: await response.json() }
    },
    { id: gameId, tenantId: tenant },
  )
}

test('9回消化後からタイブレークを開始し、次半回も再配置する', async ({
  page,
}) => {
  page.setDefaultTimeout(40_000)
  const {
    game,
    head: initial,
    tenantId: tenant,
  } = await createAndStartRealGame(
    page,
    'タイブレーク画面試験',
    9,
    'game_official',
    [benchPitcher],
  )
  let head = initial
  let count = 1
  for (let inning = 1; inning <= 9; inning += 1) {
    const result = await scorelessInning(page, head, count)
    head = result.head
    count = result.count
  }
  expect(head.after.stateFields['state.inning']).toBe('10')
  expect(head.after.stateFields['state.half']).toBe('top')
  expect(head.t2?.tiebreakStartRequired).toBe(true)
  console.log(
    'PITCHLOG_TIEBREAK_HEAD=' +
      JSON.stringify({
        checkpoint: head.prefix_ref?.checkpoint,
        next: head.next_position,
        d4: head.current_d4,
      }),
  )
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      apiPath(request.url()) === `/api/games/${game.id}/sync/events` &&
      request.postData()?.includes('tiebreak_start')
    )
      console.log('PITCHLOG_TIEBREAK_REQ=' + request.postData())
  })

  await startTiebreak(page, game.id)
  const afterStart = await currentRead(page, game.id, tenant)
  expect(afterStart.status).toBe(200)
  const startRestored = (
    afterStart.body as {
      checkpoint?: { content?: { restored?: Record<string, unknown> } }
    }
  ).checkpoint?.content?.restored as {
    current: { stateFields: Record<string, unknown> }
    runners: Array<{ runnerId: string; responsiblePitcherId: string }>
    participants: { pitcherId: string }
  }
  expect(startRestored.current.stateFields['state.runners']).toBe(
    'first-second',
  )
  expect(startRestored.current.stateFields['state.tiebreakActive']).toBe(true)
  const oldPitcher = startRestored.participants.pitcherId
  const responsible = startRestored.runners.map(
    (runner) => runner.responsiblePitcherId,
  )
  expect(new Set(responsible)).toEqual(new Set([oldPitcher]))

  const scored = await recordRealPitch(
    page,
    head,
    'batting-result.home-run',
    count,
  )
  head = scored.head
  count += 1
  expect(head.after.stateFields['state.score']).toEqual({
    away: '2',
    home: '0',
  })

  const outs = await recordOuts(page, head, count, 3)
  head = outs.head
  count = outs.count
  expect(head.after.stateFields['state.inning']).toBe('10')
  expect(head.after.stateFields['state.half']).toBe('bottom')
  expect(head.t2?.tiebreakStartRequired).toBe(true)

  await page.goto(
    `${process.env.PITCHLOG_E2E_BASE_URL}/games/${game.id}/lineup`,
  )
  const panel = page.getByTestId('substitution-product-panel')
  await panel.getByRole('button', { name: '現在の交代原本を再取得' }).click()
  for (const checkbox of await panel.locator('input[type=checkbox]').all())
    await checkbox.check()
  await panel.getByTestId('substitution-kind').selectOption('pitcher')
  await panel.getByTestId('substitution-outgoing').selectOption(oldPitcher)
  await panel.getByTestId('substitution-incoming-mode').selectOption('existing')
  await panel.getByTestId('substitution-incoming').selectOption(benchPitcher)
  const dh = panel.locator('[data-normal-question="dh"]')
  if ((await dh.count()) > 0) await dh.selectOption({ index: 0 })
  await expect(panel.getByTestId('substitution-apply')).toBeEnabled()
  const substituted = page.waitForResponse(
    (res) =>
      res.request().method() === 'POST' &&
      apiPath(res.url()) === `/api/games/${game.id}/sync/events`,
  )
  await panel.getByTestId('substitution-apply').click()
  const response = await substituted
  expect(response.status()).toBe(200)
  expect((await response.json()).eventResults?.[0]?.a5Result).toBe('受理')

  await page.goto(
    `${process.env.PITCHLOG_E2E_BASE_URL}/games/${game.id}/record?recording=play-prefix-v3`,
  )
  await expect(page.getByTestId('tiebreak-start-panel')).toBeVisible()
  await startTiebreak(page, game.id)
  const afterReplacement = await currentRead(page, game.id, tenant)
  expect(afterReplacement.status).toBe(200)
  const replacementRestored = (
    afterReplacement.body as {
      checkpoint?: { content?: { restored?: Record<string, unknown> } }
    }
  ).checkpoint?.content?.restored as {
    current: { stateFields: Record<string, unknown> }
    runners: Array<{ responsiblePitcherId: string }>
    participants: { pitcherId: string }
  }
  expect(replacementRestored.current.stateFields['state.runners']).toBe(
    'first-second',
  )
  expect(replacementRestored.current.stateFields['state.half']).toBe('bottom')
  expect(replacementRestored.participants.pitcherId).toBe(benchPitcher)
  expect(
    new Set(
      replacementRestored.runners.map((runner) => runner.responsiblePitcherId),
    ),
  ).toEqual(new Set([benchPitcher]))

  await page.reload()
  await expect(page.getByTestId('tiebreak-start-panel')).toHaveCount(0)
  console.log(
    'PITCHLOG_TIEBREAK_FINAL=' +
      JSON.stringify({
        gameId: game.id,
        plays: count - 1,
        oldPitcher,
        newPitcher: benchPitcher,
        tiebreakStarts: 2,
        rePlacementHalf: 'bottom',
      }),
  )
})
