/** 打球群の実入力専用driver。既共通helperと製品計算には変更を加えない。 */
import { expect, type Page } from '@playwright/test'
import type { LineupPrefixGame } from '../api/lineupPrefixGame'
import { apiPath, nextRecordedHead } from './RealGameRecording.e2e-support'

export type BattedStep = Readonly<{
  result: string
  destinations?: Readonly<Record<string, string>>
  causes?: Readonly<Record<string, string>>
  outs: string
  runners: string
  half: 'top' | 'bottom' | null
  inning: string | null
  score: Readonly<{ away: string; home: string }>
}>

export async function recordBattedOperation(
  page: Page,
  head: LineupPrefixGame,
  step: BattedStep,
  count: number,
) {
  await expect(page.getByTestId('ordinary-state-source')).toHaveText(
    'サーバー確認済みの状態',
  )
  for (const key of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${key}`).check()
  await page.getByTestId('first-ball-pitch-type').selectOption({ index: 1 })
  await page.getByTestId('ordinary-pitch-result').selectOption(step.result)
  await page.getByTestId('first-ball-course').locator('svg').click()
  const panel = page.getByTestId('batted-hit-observation')
  await expect(panel).toBeVisible()
  // 未観測は未観測として明示する。実野手の失策帰属だけは下で別途確認する。
  for (const key of [
    'typeKey',
    'strengthKey',
    'hitX',
    'hitY',
    'rawFielderPosition',
    'resolvedFielderId',
  ])
    await page.getByTestId(`batted-mode-${key}`).selectOption('unobserved')
  if (
    step.result === 'batting-result.error' ||
    step.result === 'batting-result.sacrifice-bunt-error'
  ) {
    const half = head.after.stateFields['state.half']
    if (half !== 'top' && half !== 'bottom') throw new Error('実守備半回が不正')
    const side = half === 'top' ? 'home' : 'away'
    const fielder = head.roster.teams
      .find((t) => t.side === side)
      ?.participants.find((p) =>
        p.roles.some(
          (role) => role.kind === 'fielding' && role.position === '6',
        ),
      )
    if (!fielder) throw new Error('実守備側の遊撃手が不足')
    await page
      .getByTestId('batted-error-fielder')
      .selectOption(fielder.player.player_id)
  }
  if (head.runners.length) {
    if (step.result !== 'batting-result.double-play') {
      expect(Object.keys(step.destinations ?? {}).sort()).toEqual(
        head.runners.map((r) => r.base).sort(),
      )
      for (const runner of head.runners) {
        const destination = step.destinations?.[runner.base]
        if (!destination) throw new Error('走者の実到達が不足')
        await page
          .getByTestId(`batted-runner-${runner.base}-destination`)
          .selectOption(destination)
        if (destination === '4') {
          const cause = step.causes?.[runner.base]
          if (!cause) throw new Error('生還走者の因果が不足')
          await page
            .getByTestId(`batted-runner-${runner.base}-rbi-cause`)
            .selectOption(cause)
        }
      }
    }
    await page.getByTestId('batted-runner-confirmed').check()
  }
  for (const question of await panel
    .locator('[data-question-key] select')
    .all())
    await question.selectOption('confirmed')
  await expect(page.getByTestId('first-ball-save')).toBeEnabled()
  const read = nextRecordedHead(page, head.id, count)
  const post = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      apiPath(r.url()) === `/api/games/${head.id}/sync/events`,
  )
  const started = Date.now()
  await page.getByTestId('first-ball-save').click()
  const response = await post
  expect(response.status()).toBe(200)
  expect((await response.json()).eventResults?.[0]?.a5Result).toBe('受理')
  const next = (await (await read).json()) as LineupPrefixGame
  expect(next.after.stateFields['state.outs']).toBe(step.outs)
  expect(next.after.stateFields['state.runners']).toBe(step.runners)
  if (step.half !== null)
    expect(next.after.stateFields['state.half']).toBe(step.half)
  if (step.inning !== null)
    expect(next.after.stateFields['state.inning']).toBe(step.inning)
  expect(next.after.stateFields['state.score']).toEqual(step.score)
  await expect(page.getByTestId('restore-history')).toHaveText(`${count}件`)
  return { head: next, elapsedMs: Date.now() - started }
}
