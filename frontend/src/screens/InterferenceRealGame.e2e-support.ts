/** 妨害裁定の実UI入力。状態・授与・アウトを補完せず試験指定値だけ入れる。 */
import {
  expect,
  type Page,
  type Request,
  type Response,
} from '@playwright/test'
import type { LineupPrefixGame } from '../api/lineupPrefixGame'
import { apiPath, nextRecordedHead } from './RealGameRecording.e2e-support'

export type InterferenceStep =
  | { kind: 'penalty'; thirdAttempt?: 'none' | 'squeeze' | 'steal-home' }
  | { kind: 'adopted'; result: 'single' | 'batted-out'; runnerHold?: boolean }
  | {
      kind: 'obstruction'
      play: 'play-on-obstructed-runner' | 'no-play-on-obstructed-runner'
      beforeFirst: boolean
      awards: Readonly<
        Record<string, 'none' | 'first' | 'second' | 'third' | 'home'>
      >
    }
  | { kind: 'offensive'; out: 'batter' | '1' }
  | { kind: 'ordinary-hit'; result: 'single' | 'triple' }

async function commonPitch(page: Page, result: string) {
  await expect(page.getByTestId('ordinary-state-source')).toHaveText(
    'サーバー確認済みの状態',
  )
  for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
    await page.getByTestId(`first-ball-env-${name}`).check()
  const pitch = page.getByTestId('first-ball-pitch-type')
  await expect(pitch.locator('option')).not.toHaveCount(1)
  await pitch.selectOption({ index: 1 })
  await page.getByTestId('ordinary-pitch-result').selectOption(result)
  await page.getByTestId('first-ball-course').locator('svg').click()
}

async function battedObservation(
  page: Page,
  head: LineupPrefixGame,
  result: 'single' | 'triple' | 'batted-out',
  adopt: boolean,
  runnerHold: boolean,
) {
  await commonPitch(page, `batting-result.${result}`)
  if (adopt) await page.getByTestId('adopt-batting-interference-play').check()
  const panel = page.getByTestId('batted-hit-observation')
  await expect(panel).toBeVisible()
  for (const key of [
    'typeKey',
    'strengthKey',
    'hitX',
    'hitY',
    'rawFielderPosition',
    'resolvedFielderId',
  ])
    await page.getByTestId(`batted-mode-${key}`).selectOption('unobserved')
  if (head.runners.length) {
    if (
      !runnerHold ||
      head.runners.length !== 1 ||
      head.runners[0]?.base !== '1'
    )
      throw new Error('明示された一塁走者hold以外の観測が不足')
    await page.getByTestId('batted-runner-1-destination').selectOption('hold')
    await page.getByTestId('batted-runner-confirmed').check()
  }
  for (const question of await panel
    .locator('[data-question-key] select')
    .all())
    await question.selectOption('confirmed')
}

async function interferenceObservation(page: Page, step: InterferenceStep) {
  if (step.kind === 'penalty') {
    await commonPitch(page, 'secondary-result.batting-interference')
    if (step.thirdAttempt !== undefined)
      await page
        .getByTestId('interference-third-attempt')
        .selectOption(step.thirdAttempt)
  } else if (step.kind === 'obstruction') {
    await commonPitch(page, 'secondary-result.obstruction')
    await page.getByTestId('obstruction-play-kind').selectOption(step.play)
    await page.getByTestId('obstruction-person').selectOption('batter')
    await page
      .getByTestId('obstruction-before-first')
      .selectOption(step.beforeFirst ? 'yes' : 'no')
    for (const [person, award] of Object.entries(step.awards))
      await page.getByTestId(`obstruction-award-${person}`).selectOption(award)
  } else if (step.kind === 'offensive') {
    await commonPitch(page, 'secondary-result.offensive-interference')
    const group = page.getByRole('group', { name: '審判の妨害裁定を記録' })
    await group
      .locator('input[type="checkbox"]')
      .nth(step.out === 'batter' ? 0 : 1)
      .check()
  } else throw new Error('妨害裁定の入力種別が不正')
  await page.getByTestId('interference-confirm').check()
  await expect(page.getByTestId('interference-observation-ready')).toBeVisible()
}

export async function recordInterferenceStep(
  page: Page,
  head: LineupPrefixGame,
  step: InterferenceStep,
  count: number,
) {
  if (step.kind === 'adopted')
    await battedObservation(
      page,
      head,
      step.result,
      true,
      step.runnerHold ?? false,
    )
  else if (step.kind === 'ordinary-hit')
    await battedObservation(page, head, step.result, false, false)
  else await interferenceObservation(page, step)
  await expect(page.getByTestId('first-ball-save')).toBeEnabled()
  const startedReads: {
    status: number
    projection: 'v3' | 'other'
    readKind: 'lineup-prefix' | 'other' | 'unavailable'
    length: 'target' | 'other' | 'unavailable'
  }[] = []
  let startedRequests = 0
  const observeRequest = (request: Request) => {
    if (
      request.method() === 'GET' &&
      apiPath(request.url()) === `/api/games/${head.id}/started`
    )
      startedRequests++
  }
  const observeStarted = (response: Response) => {
    if (
      response.request().method() !== 'GET' ||
      apiPath(response.url()) !== `/api/games/${head.id}/started`
    )
      return
    const observed = {
      status: response.status(),
      projection:
        new URL(response.url()).searchParams.get('projection') ===
        'play-prefix-v3'
          ? ('v3' as const)
          : ('other' as const),
      readKind: 'unavailable' as 'lineup-prefix' | 'other' | 'unavailable',
      length: 'unavailable' as 'target' | 'other' | 'unavailable',
    }
    startedReads.push(observed)
    if (observed.status !== 200) return
    void response
      .json()
      .then((body: unknown) => {
        if (typeof body !== 'object' || body === null) return
        const value = body as Record<string, unknown>
        observed.readKind =
          value.read_kind === 'lineup-prefix' ? 'lineup-prefix' : 'other'
        const prefix = value.prefix_ref
        observed.length =
          typeof prefix === 'object' &&
          prefix !== null &&
          (prefix as Record<string, unknown>).length === String(count)
            ? 'target'
            : 'other'
      })
      .catch(() => undefined)
  }
  page.on('request', observeRequest)
  page.on('response', observeStarted)
  const read = nextRecordedHead(page, head.id, count)
  const post = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      apiPath(response.url()) === `/api/games/${head.id}/sync/events`,
  )
  let postStatus: number | null = null
  try {
    // 2試合目以降のcold startでも、実readが保存可能へ進むまで待つ。
    await expect(page.getByTestId('first-ball-save')).toBeEnabled({
      timeout: 30_000,
    })
    await page.getByTestId('first-ball-save').click()
    const response = await post
    postStatus = response.status()
    expect(postStatus).toBe(200)
    const ack = await response.json()
    expect(ack.eventResults?.[0]?.a5Result).toBe('受理')
    const next = (await (await read).json()) as LineupPrefixGame
    expect(next.prefix_ref.length).toBe(String(count))
    await expect(page.getByTestId('restore-history')).toHaveText(`${count}件`)
    return next
  } catch (error) {
    const message = await page
      .getByTestId('first-ball-status')
      .textContent({ timeout: 1000 })
      .catch(() => null)
    const uiStatus =
      message === '保存応答を受け取りました。サーバーから再取得しています'
        ? 'saved-awaiting-read'
        : message ===
            'サーバーの最新記録を確認しています。入力と再送を一時停止します'
          ? 'suspended'
          : message ===
              'この入力を確定できません。結果・打者と最新の記録を確認してください'
            ? 'blocked'
            : 'other-or-absent'
    console.log(
      'PITCHLOG_INTERFERENCE_READ_SAFE=' +
        JSON.stringify({ postStatus, startedRequests, startedReads, uiStatus }),
    )
    throw error
  } finally {
    page.off('request', observeRequest)
    page.off('response', observeStarted)
  }
}
