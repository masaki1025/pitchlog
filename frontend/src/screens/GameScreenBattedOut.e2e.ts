/** 凡打死3球で第3アウト・再掲・再読込を実画面から照合する候補。 */
import { expect, test } from '@playwright/test'
import {
  apiPath,
  createAndStartRealGame,
  recordRealPitch,
} from './RealGameRecording.e2e-support'

test('無走者の凡打死3球で攻守交代し、同D5再掲と再読込は加算しない', async ({
  page,
}) => {
  page.setDefaultTimeout(30_000)
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window)
    let first: { url: string; init: RequestInit } | undefined
    window.fetch = async (input, init) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url
      if (
        first === undefined &&
        init?.method === 'POST' &&
        /\/games\/[^/]+\/sync\/events$/.test(
          new URL(url, location.href).pathname,
        )
      ) {
        if (typeof init.body !== 'string') throw new Error('原要求本文が不足')
        first = {
          url,
          init: {
            ...init,
            headers: new Headers(init.headers),
            body: init.body,
          },
        }
      }
      return nativeFetch(input, init)
    }
    Object.defineProperty(window, '__repeatBattedOutForTest', {
      value: async () => {
        if (!first) throw new Error('原要求が未取得')
        const response = await nativeFetch(first.url, {
          ...first.init,
          signal: AbortSignal.timeout(30_000),
        })
        const body = await response.json()
        return {
          status: response.status,
          result: body?.eventResults?.[0]?.a5Result,
        }
      },
    })
  })
  const { game, head: initial } = await createAndStartRealGame(
    page,
    '凡打死第3アウト検証',
  )
  let head = initial
  for (let index = 1; index <= 3; index += 1) {
    const saved = await recordRealPitch(
      page,
      head,
      'batting-result.batted-out',
      index,
    )
    head = saved.head
    expect(head.prefix_ref.length).toBe(String(index))
    expect(head.after.stateFields['state.runners']).toBe('empty')
    expect(head.after.stateFields['state.outs']).toBe(
      index === 3 ? '0' : String(index),
    )
    expect(head.after.stateFields['state.half']).toBe(
      index === 3 ? 'bottom' : 'top',
    )
    expect(head.after.stateFields['state.inning']).toBe('1')
    expect(head.after.scoreboard.hits).toBe('0')
    expect(head.after.scoreboard.errors).toBe('0')
  }
  const repeat = await page.evaluate(() =>
    (
      window as unknown as Window & {
        __repeatBattedOutForTest: () => Promise<{
          status: number
          result: string
        }>
      }
    ).__repeatBattedOutForTest(),
  )
  expect(repeat).toEqual({ status: 200, result: '重複' })
  const restoredPromise = page.waitForResponse(
    async (response) =>
      response.request().method() === 'GET' &&
      apiPath(response.url()) === `/api/games/${game.id}/started` &&
      response.status() === 200 &&
      (await response.json()).prefix_ref?.length === '3',
  )
  await page.reload()
  await expect(page.getByTestId('restore-history')).toHaveText('3件')
  const body = await (await restoredPromise).json()
  expect(body.after).toEqual(head.after)
  expect(body.prefix_ref).toEqual(head.prefix_ref)
  console.log(
    'PITCHLOG_BATTED_OUT_SCREEN=' +
      JSON.stringify({
        gameId: game.id,
        accepted: 3,
        prefixLength: body.prefix_ref.length,
        half: body.after.stateFields['state.half'],
        outs: body.after.stateFields['state.outs'],
      }),
  )
})
