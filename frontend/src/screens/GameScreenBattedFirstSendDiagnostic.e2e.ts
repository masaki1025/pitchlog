/** 最初の送信前閉拒否だけを観測する。例外の内容・資格・要求本文は保存しない。 */
import { expect, test } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createAndStartRealGame } from './RealGameRecording.e2e-support'
import { recordBattedOperation } from './BattedOperations.e2e-support'

test('最初の単打の送信前状態を安全に採取する', async ({ page }) => {
  const dir = process.env.PITCHLOG_FULLGAME_EVIDENCE_DIR
  if (!dir) throw new Error('診断の所有出力先が不足')
  const network: Array<{ method: string; endpoint: string; status: number }> =
    []
  const exceptions: Array<{
    kind: string
    sites: Array<{ file: string; line: number }>
  }> = []
  const consoleKinds: string[] = []
  const phases: string[] = []
  const cdp = await page.context().newCDPSession(page)
  const scripts = new Map<string, string>()
  cdp.on('Debugger.scriptParsed', ({ scriptId, url }) => {
    const match = /\/src\/([A-Za-z0-9_./-]+\.ts|[A-Za-z0-9_./-]+\.vue)/.exec(
      url,
    )
    if (match) scripts.set(scriptId, match[0])
  })
  cdp.on('Debugger.paused', (event) => {
    if (event.reason === 'exception' || event.reason === 'promiseRejection') {
      const sites = event.callFrames
        .flatMap((frame) => {
          const file = scripts.get(frame.location.scriptId)
          return file ? [{ file, line: frame.location.lineNumber + 1 }] : []
        })
        .slice(0, 6)
      if (sites.length && exceptions.length < 32) {
        const raw = event.data?.className
        const kind =
          typeof raw === 'string' && /^[A-Za-z]+Error$/.test(raw)
            ? raw
            : 'other-exception'
        exceptions.push({ kind, sites })
      }
    }
    void cdp.send('Debugger.resume')
  })
  await cdp.send('Debugger.enable')
  page.on('console', (message) => {
    if (message.type() === 'error' && consoleKinds.length < 16)
      consoleKinds.push('console-error')
  })
  page.on('pageerror', (error) => {
    const kind = /^[A-Za-z]+Error$/.test(error.name)
      ? error.name
      : 'other-exception'
    if (consoleKinds.length < 16) consoleKinds.push(kind)
  })
  page.on('response', (response) => {
    const path = new URL(response.url()).pathname
    if (!path.startsWith('/api/')) return
    const endpoint = path.replace(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi,
      ':id',
    )
    if (/^\/api\/[A-Za-z0-9_/:.-]+$/.test(endpoint) && network.length < 128)
      network.push({
        method: response.request().method(),
        endpoint,
        status: response.status(),
      })
  })
  let outcome = 'not-started'
  try {
    const { head } = await createAndStartRealGame(page, 'first-send-diagnostic')
    phases.push('created-started-real-head')
    await cdp.send('Debugger.setPauseOnExceptions', { state: 'all' })
    outcome = 'single-not-confirmed'
    await recordBattedOperation(
      page,
      head,
      {
        result: 'batting-result.single',
        outs: '0',
        runners: 'first',
        half: 'top',
        inning: '1',
        score: { away: '0', home: '0' },
      },
      1,
    )
    outcome = 'single-accepted-and-read'
    phases.push(outcome)
    await expect(page.getByTestId('restore-history')).toHaveText('1件')
  } finally {
    await cdp.send('Debugger.setPauseOnExceptions', { state: 'none' })
    const text = await page
      .getByTestId('first-ball-status')
      .textContent()
      .catch(() => null)
    const status =
      text ===
      'この入力を確定できません。結果・打者と最新の記録を確認してください'
        ? 'blocked'
        : text === '記録要求の保存・送信結果を確認しています'
          ? 'busy'
          : text === '投球を記録できます'
            ? 'ready'
            : text === '保存応答を受け取りました。サーバーから再取得しています'
              ? 'saved-refreshing'
              : 'other-or-missing'
    writeFileSync(
      resolve(dir, 'first-send-safe.json'),
      JSON.stringify(
        { outcome, phases, status, exceptions, consoleKinds, network },
        null,
        2,
      ),
      { mode: 0o600 },
    )
    await cdp.detach()
  }
})
