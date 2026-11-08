/** 妨害 INT01〜07 の実入力を、真正UI作成試合で記録・再掲・再読込する。 */
import { expect, test } from '@playwright/test'
import {
  baseURL,
  createAndStartRealGame,
  nextRecordedHead,
} from './RealGameRecording.e2e-support'
import {
  recordInterferenceStep,
  type InterferenceStep,
} from './InterferenceRealGame.e2e-support'

type Scenario = Readonly<{
  name: string
  steps: readonly Readonly<{
    branch: string
    input: InterferenceStep
    outs: string
    runners: string
  }>[]
}>

const scenarios: readonly Scenario[] = [
  {
    name: 'INT02 罰則採用',
    steps: [
      {
        branch: 'INT-02',
        input: { kind: 'penalty' },
        outs: '0',
        runners: 'first',
      },
    ],
  },
  {
    name: 'INT01 自動成立と INT03 実プレイ選択',
    steps: [
      {
        branch: 'INT-01',
        input: { kind: 'adopted', result: 'single' },
        outs: '0',
        runners: 'first',
      },
      {
        branch: 'INT-03',
        input: { kind: 'adopted', result: 'batted-out', runnerHold: true },
        outs: '1',
        runners: 'first',
      },
    ],
  },
  {
    name: 'INT02 本盗企図と授与後の盗塁未成立区別',
    steps: [
      {
        branch: 'ordinary-triple',
        input: { kind: 'ordinary-hit', result: 'triple' },
        outs: '0',
        runners: 'third',
      },
      {
        branch: 'INT-02-steal-home',
        input: { kind: 'penalty', thirdAttempt: 'steal-home' },
        outs: '0',
        runners: 'first',
      },
    ],
  },
  {
    name: 'INT04 到達前と INT05 プレイ後裁定',
    steps: [
      {
        branch: 'INT-04',
        input: {
          kind: 'obstruction',
          play: 'no-play-on-obstructed-runner',
          beforeFirst: true,
          awards: { batter: 'first' },
        },
        outs: '0',
        runners: 'first',
      },
      {
        branch: 'INT-05',
        input: {
          kind: 'obstruction',
          play: 'no-play-on-obstructed-runner',
          beforeFirst: false,
          awards: { batter: 'first', '1': 'second' },
        },
        outs: '0',
        runners: 'first-second',
      },
    ],
  },
  {
    name: 'INT06 打者アウトと INT07 走者だけアウト',
    steps: [
      {
        branch: 'INT-06',
        input: { kind: 'offensive', out: 'batter' },
        outs: '1',
        runners: 'empty',
      },
      {
        branch: 'ordinary-single',
        input: { kind: 'ordinary-hit', result: 'single' },
        outs: '1',
        runners: 'first',
      },
      {
        branch: 'INT-07',
        input: { kind: 'offensive', out: '1' },
        outs: '2',
        runners: 'empty',
      },
    ],
  },
]

test('妨害7分岐を実画面から保存し原本再掲とreloadを確認する', async ({
  browser,
}) => {
  if (!baseURL) throw new Error('隔離HTTPSのbase URLがない')
  const evidence: Array<{ gameId: string; branches: string[]; plays: number }> =
    []
  for (const scenario of scenarios) {
    const context = await browser.newContext({ ignoreHTTPSErrors: true })
    try {
      const page = await context.newPage()
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
        Object.defineProperty(window, '__replayInterferenceOriginal', {
          value: async () => {
            if (!saved) throw new Error('元要求がない')
            const response = await original(saved.input, {
              ...saved.init,
              signal: AbortSignal.timeout(30000),
            })
            const body = await response.json()
            return {
              status: response.status,
              a5: body.eventResults?.[0]?.a5Result,
            }
          },
        })
      })
      const { game, head: initial } = await createAndStartRealGame(
        page,
        scenario.name,
      )
      let head = initial
      for (const [index, step] of scenario.steps.entries()) {
        head = await recordInterferenceStep(page, head, step.input, index + 1)
        expect(head.after.stateFields['state.outs']).toBe(step.outs)
        expect(head.after.stateFields['state.runners']).toBe(step.runners)
        const actual = head.page.items.find(
          (item) => item.play_row.play_number === index + 1,
        )
        if (!actual) throw new Error('保存した当該playが実GETから欠落')
        const duplicate = await page.evaluate(async () =>
          (
            window as unknown as {
              __replayInterferenceOriginal: () => Promise<{
                status: number
                a5: string
              }>
            }
          ).__replayInterferenceOriginal(),
        )
        expect(duplicate).toEqual({ status: 200, a5: '重複' })
        const fresh = await page.request.get(
          new URL(
            `/api/games/${game.id}/started?projection=play-prefix-v3`,
            baseURL,
          ).href,
        )
        expect(fresh.status()).toBe(200)
        const restored = await fresh.json()
        expect(restored.prefix_ref).toEqual(head.prefix_ref)
        expect(restored.after).toEqual(head.after)
        expect(restored.page.items).toEqual(head.page.items)
      }
      const beforeReload = head
      const read = nextRecordedHead(page, game.id, scenario.steps.length)
      await page.reload()
      const afterReload = await (await read).json()
      expect(afterReload.prefix_ref).toEqual(beforeReload.prefix_ref)
      expect(afterReload.after).toEqual(beforeReload.after)
      expect(afterReload.page.items).toEqual(beforeReload.page.items)
      await expect(page.getByTestId('restore-history')).toHaveText(
        `${scenario.steps.length}件`,
      )
      evidence.push({
        gameId: game.id,
        branches: scenario.steps.map((step) => step.branch),
        plays: scenario.steps.length,
      })
    } finally {
      await context.close()
    }
  }
  expect(evidence.flatMap((item) => item.branches)).toEqual([
    'INT-02',
    'INT-01',
    'INT-03',
    'ordinary-triple',
    'INT-02-steal-home',
    'INT-04',
    'INT-05',
    'INT-06',
    'ordinary-single',
    'INT-07',
  ])
  console.log('PITCHLOG_INTERFERENCE_SCREEN=' + JSON.stringify(evidence))
})
