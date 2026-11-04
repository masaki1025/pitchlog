"""通常3球の実画面試験専用Playwright資産をowned一時領域へ生成する。"""

from __future__ import annotations

import json
from pathlib import Path

# test専用のTLS trustであり実機・運用TLSの検証ではない。trace等に資格を残さない。
_SPEC = r"""
import { expect, test, type Page } from '__PLAYWRIGHT_MODULE__'
import { startOrdinaryStageMonitor } from './ordinary-stage-monitor.mjs'

const baseURL = process.env.PITCHLOG_E2E_BASE_URL
const team = process.env.PITCHLOG_E2E_TEAM_NAME
const password = process.env.PITCHLOG_E2E_PASSWORD
const away = process.env.PITCHLOG_E2E_AWAY_TEAM
const home = process.env.PITCHLOG_E2E_HOME_TEAM
if (!baseURL || !team || !password || !away || !home)
  throw new Error('E2Eの実app資格がenvにない')

function apiPath(url: string): string {
  return new URL(url).pathname
}
async function login(page: Page): Promise<string> {
  await page.goto(`${baseURL}/login?redirect=/games`)
  await expect(page.locator('form[aria-busy]')).toHaveAttribute(
    'aria-busy',
    'false',
  )
  await page.getByRole('textbox', { name: 'チーム名' }).fill(team!)
  await page.getByLabel('パスワード').fill(password!)
  const posted = page
    .waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === '/api/auth/login',
    )
    .catch(() => null)
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
  const response = await posted
  if (!response || response.status() !== 200)
    throw new Error('実login POSTが成功しない')
  const body = (await response.json()) as { tenant_id?: string }
  if (typeof body.tenant_id !== 'string')
    throw new Error('login応答のtenantがない')
  return body.tenant_id
}

/** 失敗時にも利用者入力・原要求・資格・自由textを返さない。 */
async function safeUi(page: Page, index: number, resultId: string) {
  const allowed = ['batting-result.ball','batting-result.called-pitch',
    'batting-result.swinging-strike','batting-result.foul',
    'batting-result.walk','batting-result.hit-by-pitch']
  return page.evaluate(({index,resultId}) => {
    const button=document.querySelector('[data-testid="first-ball-save"]')
    type Component={parent?:Component;type?:{__name?:string};uid?:number;
      setupState?:Record<string,unknown>}
    let owner=(button as (Element & {__vueParentComponent?:Component})|null)
      ?.__vueParentComponent
    while(owner && owner.type?.__name!=='GameScreenOrdinaryPitch') owner=owner.parent
    const setup=owner?.setupState??{}
    const read=(key:string):unknown=>{
      const v=setup[key]
      return v!==null&&typeof v==='object'&&'value' in v
        ?(v as {value:unknown}).value:v
    }
    const bool=(key:string)=>typeof read(key)==='boolean'?read(key):null
    const field=(id:string)=>document.querySelector(`[data-testid="${id}"]`)
    const checked=(id:string)=>{
      const v=field(`first-ball-env-${id}`)
      return v instanceof HTMLInputElement?v.checked:null
    }
    const selected=(id:string)=>{
      const v=field(id)
      return v instanceof HTMLSelectElement?v.value.length>0:null
    }
    const stamp=read('watchedInput') as {
      identity?:{epoch?:unknown;tenantId?:unknown}
    }|null
    const auth=read('auth') as {authEpoch?:unknown;teamId?:unknown}|null
    const raw=(window as unknown as {__ordinarySafeDiagnostic?:Record<string,unknown>})
      .__ordinarySafeDiagnostic
    const status=read('status')
    const marker=field('first-ball-course')?.querySelector('svg')
      ?.getAttribute('aria-label')
    return {index,resultId,ownerPresent:!!owner,
      ownerUid:Number.isSafeInteger(owner?.uid)&&owner!.uid!>=0&&owner!.uid!<=1000000
        ?owner!.uid:null,
      disabled:button instanceof HTMLButtonElement?button.disabled:null,
      busy:bool('busy'),confirmed:bool('confirmed'),loading:bool('loading'),
      failed:bool('failed'),terminal:bool('terminal'),
      nextBatterSelected:selected('terminal-next-batter'),
      pitchTypeSelected:selected('first-ball-pitch-type'),
      pointPresent:typeof marker==='string'?!marker.includes('未入力'):null,
      checkboxProfile:checked('profile'),checkboxMode:checked('mode'),
      checkboxBucket:checked('bucket'),checkboxLockdown:checked('lockdown'),
      httpsTopLevel:window.isSecureContext&&location.protocol==='https:'&&window.top===window,
      status:typeof status==='string'
        &&['ready','saved','pending','blocked'].includes(status)
        ?status:'unavailable',
      tenantMatches:stamp?.identity&&auth
        ?stamp.identity.tenantId===auth.teamId:null,
      epochMatches:stamp?.identity&&auth?stamp.identity.epoch===auth.authEpoch:null,
      observerPresent:!!raw,bodyReadStarted:raw?.bodyReadStarted===true,
      bodyReadSucceeded:raw?.bodyReadSucceeded===true,
      disposedDuringSubmit:raw?.disposedDuringSubmit===true}
  },{index:Number.isInteger(index)&&index>=0&&index<=4?index:-1,
    resultId:allowed.includes(resultId)?resultId:'other'})
}

test('実HTTPSの新規試合で通常3球を保存・同要求再送・reloadする', async ({
  page,
}) => {
  if (new URL(baseURL!).protocol !== 'https:')
    throw new Error('HTTPSが必要です')
  const stageMonitor = await startOrdinaryStageMonitor(page)
  const prefixReads: {
    source: string
    status: number
    kind: string
    atExpected: boolean
  }[] = []
  let expectedPrefixLength = '0'
  const observeRead = async (
    response: import('__PLAYWRIGHT_MODULE__').Response,
  ) => {
    const url = new URL(response.url())
    if (
      response.request().method() !== 'GET' ||
      !/\/games\/[^/]+\/started$/.test(url.pathname)
    )
      return
    const read = {
      source:
        url.searchParams.get('projection') === 'ordinary-prefix-v1'
          ? 'ordinary'
          : 'legacy',
      status: response.status(),
      kind: 'unread',
      atExpected: false,
    }
    prefixReads.push(read)
    if (prefixReads.length > 10) prefixReads.shift()
    try {
      const value = await response.json()
      read.kind = ['recorded-prefix', 'initial', 'recorded'].includes(
        value.read_kind,
      )
        ? value.read_kind
        : 'other'
      read.atExpected = value.prefix_ref?.length === expectedPrefixLength
    } catch {
      read.kind = 'unreadable'
    }
  }
  page.on('response', observeRead)
  try {
    await page.addInitScript(() => {
      const nativeFetch = window.fetch.bind(window)
      const originals: { url: string; init: RequestInit }[] = []
      window.fetch = async (input, init) => {
        const url =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.href
              : input.url
        if (
          init?.method === 'POST' &&
          /\/games\/[^/]+\/sync\/events$/.test(
            new URL(url, location.href).pathname,
          )
        ) {
          if (typeof init.body !== 'string')
            throw new Error('同期本文がありません')
          originals.push({
            url,
            init: {
              ...init,
              headers: new Headers(init.headers),
              body: init.body,
            },
          })
        }
        const response = await nativeFetch(input, init)
        if (
          init?.method === 'POST' &&
          /\/games\/[^/]+\/sync\/events$/.test(
            new URL(url, location.href).pathname,
          )
        ) {
          const diag = (
            window as unknown as {
              __ordinarySafeDiagnostic: Record<string, string | boolean>
            }
          ).__ordinarySafeDiagnostic ?? {}
          diag.contentTypeJson = (
            response.headers.get('content-type') ?? ''
          )
            .toLowerCase()
            .includes('json')
          const originalText = response.text.bind(response)
          Object.defineProperty(response, 'text', {
            value: async () => {
              diag.bodyReadStarted = true
              diag.bodyUsedBefore = response.bodyUsed
              try {
                const text = await originalText()
                diag.bodyReadSucceeded = true
                diag.bodyNonempty = text.length > 0
                try {
                  JSON.parse(text)
                  diag.bodyJsonValid = true
                } catch {
                  diag.bodyJsonValid = false
                }
                return text
              } catch (error) {
                const name = error instanceof Error ? error.name : 'other'
                diag.bodyReadError = [
                  'TypeError',
                  'AbortError',
                  'QuotaExceededError',
                  'Error',
                ].includes(name)
                  ? name
                  : 'other'
                throw error
              }
            },
          })
        }
        return response
      }
      // 原要求・資格・attemptはブラウザclosureだけに保持し、外部へ返さない。
      Object.defineProperty(window, '__ordinaryReplayFirst', {
        value: async () => {
          if (originals.length !== 3) throw new Error('3要求が必要です')
          const original = originals[0]!
          const event = JSON.parse(original.init.body as string).events[0]
          const response = await nativeFetch(original.url, original.init)
          const ack = await response.json()
          const item = ack.eventResults?.[0]
          return {
            status: response.status,
            count: originals.length,
            sameSlot:
              ack.eventResults?.length === 1 &&
              item?.d1 === event.d1 &&
              item?.d4 === event.d4 &&
              item?.d5 === event.d5,
            advanced: ack.advancedD3 === 3,
            duplicate: item?.a5Result === '重複',
          }
        },
      })
    })
    await login(page)
    await page.evaluate(async () => {
      // 試験だけの観測。元関数を必ず実行し、状態・成功応答・認可を変更しない。
      const { DurableQueue } = await import('/src/lib/sync/durableQueue.ts')
      const { GameScreenOrdinaryPitchController } =
        await import('/src/screens/GameScreenOrdinaryPitchController.ts')
      const { GameStartPersistence } =
        await import('/src/lib/gameStartPersistence.ts')
      const { useAuthStore } = await import('/src/stores/authStore.ts')
      const diag: Record<string, string | boolean> = {}
      Object.defineProperty(window, '__ordinarySafeDiagnostic', {
        value: diag,
      })
      const exception = (error: unknown) => {
        const name = error instanceof Error ? error.name : 'other'
        return [
          'DataCloneError',
          'TransactionInactiveError',
          'AbortError',
          'QuotaExceededError',
          'TypeError',
          'Error',
        ].includes(name)
          ? name
          : 'other'
      }
      for (const name of [
        'prepareA5Transition',
        'persistA5Transition',
      ] as const) {
        const original = DurableQueue.prototype[name]
        DurableQueue.prototype[name] = async function (...args: never[]) {
          try {
            const result = await original.apply(this, args)
            diag[name] = result ? 'provided' : 'absent'
            return result
          } catch (error) {
            diag[name] = exception(error)
            throw error
          }
        } as never
      }
      const originalDispose =
        GameScreenOrdinaryPitchController.prototype.dispose
      GameScreenOrdinaryPitchController.prototype.dispose = function () {
        if (diag.done === false) diag.disposedDuringSubmit = true
        return originalDispose.call(this)
      }
      const original = GameScreenOrdinaryPitchController.prototype.submit
      GameScreenOrdinaryPitchController.prototype.submit = async function (
        ...args
      ) {
        for (const key of Object.keys(diag)) delete diag[key]
        diag.done = false
        const auth = useAuthStore(),
          epoch = auth.authEpoch
        diag.authVerifiedBefore = auth.isAuthenticated
        const context = this.context
        const store = await GameStartPersistence.open()
        try {
          const saved = await store.readStart(
            context.prefixRef.tenantId,
            context.game.id,
          )
          diag.grantMatches =
            saved?.status === 'received' &&
            saved.grant?.d4 === context.game.current_d4 &&
            saved.grant?.recovery_generation ===
              context.serverStamp?.recoveryGeneration
        } finally {
          store.close()
        }
        try {
          const result = await original.apply(this, args)
          diag.submitOutcome = result
          return result
        } catch (error) {
          diag.submitOutcome = 'threw'
          diag.exception = exception(error)
          throw error
        } finally {
          diag.authEpochStable = epoch === auth.authEpoch
          diag.authVerifiedAfter = auth.isAuthenticated
          diag.canAppendAfter = this.canAppend
          diag.retryEvidenceUnavailable = this.retryEvidenceUnavailable
          diag.done = true
        }
      }
    })
    await page
      .getByRole('button', { name: '新規作成', exact: true })
      .click()
    const form = page.getByRole('region', {
      name: '試合の新規作成',
      exact: true,
    })
    await expect(form.getByLabel('日時（日本時間）')).toBeEnabled()
    await form.getByLabel('日時（日本時間）').fill('2026-10-31T10:00')
    await form.getByTestId('game-type').selectOption('game_other')
    await form.getByTestId('away').selectOption(away!)
    await form.getByTestId('home').selectOption(home!)
    await form.getByTestId('tournament-kind').selectOption('new')
    await form
      .getByLabel('新しい大会名', { exact: true })
      .fill('画面作成大会')
    const created = page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === '/api/games',
    )
    await form
      .getByRole('button', { name: '準備中の試合を作成', exact: true })
      .click()
    const createdResponse = await created
    expect(createdResponse.status()).toBe(201)
    const saved = (await createdResponse.json()) as {
      id: string
      status: string
      applied_rules: { dh: boolean }
    }
    expect(saved.status).toBe('preparing')
    // 作成した試合の保存値を確認すると記録画面へ遷移する。
    await form
      .getByRole('button', {
        name: '作成した試合IDの保存値を確認',
        exact: true,
      })
      .click()
    await expect(page).toHaveURL(`${baseURL}/games/${saved.id}/record`)
    await page.evaluate(async () => {
      const { router } = await import('/src/router.ts')
      await router.replace({query:{recording:'ordinary-prefix-v1'}})
    })
    await expect(
      page.getByRole('heading', { name: 'スタメンと試合開始' }),
    ).toBeVisible()
    await page.getByRole('button', { name: 'この端末を登録' }).click()
    await expect(page.getByText('開始入力を確認できます')).toBeVisible()
    const dh = saved.applied_rules.dh === true
    for (const side of ['away', 'home'] as const) {
      const rows = dh ? 10 : 9
      for (let index = 0; index < rows; index += 1) {
        await page
          .locator(`#start-${side}-${index}-player`)
          .selectOption({ index: index + 1 })
        const position =
          index === 9
            ? '1'
            : dh
              ? index === 8
                ? 'DH'
                : String(index + 2)
              : String(index + 1)
        await page
          .locator(`#start-${side}-${index}-position`)
          .selectOption(position)
      }
    }
    const started = page.waitForResponse(
      (res) =>
        res.request().method() === 'POST' &&
        apiPath(res.url()) === `/api/games/${saved.id}/start`,
    )
    await page
      .getByRole('button', { name: '試合を開始', exact: true })
      .click()
    const startedResponse = await started
    expect(startedResponse.status()).toBe(200)
    // 開始後の実サーバー再取得で復元入口が出たら、実UIから再取得する。
    const isPrefix = (res: import('__PLAYWRIGHT_MODULE__').Response) => {
      const url = new URL(res.url())
      return (
        res.request().method() === 'GET' &&
        url.pathname === `/api/games/${saved.id}/started` &&
        url.searchParams.get('projection') === 'ordinary-prefix-v1' &&
        res.status() === 200
      )
    }
    const initialRead = page.waitForResponse(isPrefix)
    await page
      .getByRole('button', { name: /^サーバーから(?:復元|再取得)$/ })
      .click()
    const initial = await (await initialRead).json()
    expect(initial.read_kind).toBe('recorded-prefix')
    expect(initial.prefix_ref.length).toBe('0')
    await expect(page.getByTestId('ordinary-pitch-result')).toBeVisible()
    expect(
      await page.evaluate(
        () =>
          window.isSecureContext &&
          window.top === window &&
          location.protocol === 'https:',
      ),
    ).toBe(true)
    await stageMonitor.ready()
    let latest = initial
    const results = [
      'batting-result.ball',
      'batting-result.called-pitch',
      'batting-result.ball',
    ]
    const balls = ['1', '1', '2'],
      strikes = ['0', '1', '1']
    for (let index = 0; index < results.length; index++) {
      expectedPrefixLength = String(index + 1)
      prefixReads.length = 0
      const inputStart=await safeUi(page,index,results[index]!)
      for (const id of ['profile', 'mode', 'bucket', 'lockdown'])
        await page.getByTestId(`first-ball-env-${id}`).check()
      await page
        .getByTestId('ordinary-pitch-result')
        .selectOption(results[index]!)
      const pitchType = page.getByTestId('first-ball-pitch-type')
      await expect(pitchType).toBeEnabled()
      await expect(pitchType.locator('option')).not.toHaveCount(1)
      await pitchType.selectOption({ index: 1 })
      await page.getByTestId('first-ball-course').locator('svg').click()
      const synchronized = page.waitForResponse(
        (res) =>
          res.request().method() === 'POST' &&
          apiPath(res.url()) === `/api/games/${saved.id}/sync/events`,
      )
      const restored = page.waitForResponse(
        async (res) =>
          isPrefix(res) &&
          (await res.json()).prefix_ref.length === String(index + 1),
        { timeout: 30000 },
      )
      // 診断による早期fail後も待機Promiseの二次unhandledを出さない。
      void restored.catch(() => undefined)
      try {
        await expect(page.getByTestId('first-ball-save')).toBeEnabled()
      } catch {
        throw new Error(JSON.stringify({stage:'save-disabled',inputStart,
          current:await safeUi(page,index,results[index]!),
          cdpStages:stageMonitor.snapshot()}))
      }
      await page.getByTestId('first-ball-save').click()
      const acknowledged = await synchronized
      expect(acknowledged.status()).toBe(200)
      let ack: Awaited<ReturnType<typeof acknowledged.json>>
      try {
        ack = await Promise.race([
          acknowledged.json(),
          new Promise<never>((_resolve,reject)=>setTimeout(
            ()=>reject(new Error('ack-body-not-finished')),10000)),
        ])
      }catch{
        throw new Error(JSON.stringify({stage:'ack-body-read-failed',inputStart,
          current:await safeUi(page,index,results[index]!),
          cdpStages:stageMonitor.snapshot()}))
      }
      const sent = acknowledged.request().postDataJSON().events[0]
      // 失敗時も原本文や資格をexpect差分へ表示しない。
      expect(
        ack.eventResults?.length === 1 &&
          ack.eventResults[0].a5Result === '受理' &&
          ack.eventResults[0].d1 === sent.d1 &&
          ack.eventResults[0].d4 === sent.d4 &&
          ack.eventResults[0].d5 === sent.d5 &&
          ack.advancedD3 === index + 1,
      ).toBe(true)
      await page.waitForFunction(
        () =>
          (
            window as unknown as {
              __ordinarySafeDiagnostic?: { done?: boolean }
            }
          ).__ordinarySafeDiagnostic?.done === true,
        null,
        { timeout: 20000 },
      )
      const diagnostic = await page.evaluate(
        async ({ value, key }) => {
          const { readOrdinaryPitchAck } =
            await import('/src/api/ordinaryPitchAck.ts')
          const actual = readOrdinaryPitchAck(value, key)
          const { createAckAdapterInjections } =
            await import('/src/lib/sync/ackAdapter.ts')
          let adapterAccepts = false,
            adapterResolvesSlot = false
          try {
            const adapter = createAckAdapterInjections({ d1: actual })
            adapterAccepts = true
            adapterResolvesSlot =
              adapter.resolveA5?.(key)?.result.id === '受理'
          } catch {
            /* 成否だけ返し、例外本文は出力しない。 */
          }
          return {
            ...(
              window as unknown as {
                __ordinarySafeDiagnostic: Record<string, string | boolean>
              }
            ).__ordinarySafeDiagnostic,
            ackParserAccepts: !!actual,
            adapterAccepts,
            adapterResolvesSlot,
          }
        },
        { value: ack, key: { d4: sent.d4, d1: sent.d1, d5: sent.d5 } },
      )
      // 失敗出力は列挙済みのenum/booleanのみ。原要求・資格・ACK原値は出力しない。
      expect(
        diagnostic.submitOutcome,
        JSON.stringify({
          ...diagnostic,
          cdpStages: stageMonitor.snapshot(),
        }),
      ).toBe('saved')
      try {
        latest = await (await restored).json()
      } catch {
        throw new Error(
          JSON.stringify({
            stage: 'prefix-read-timeout',
            reads: prefixReads,
            cdpStages: stageMonitor.snapshot(),
          }),
        )
      }
      expect(latest.read_kind).toBe('recorded-prefix')
      expect(latest.page.items).toHaveLength(index + 1)
      expect(latest.after.stateFields).toStrictEqual({
        ...initial.after.stateFields,
        'state.count.balls': balls[index],
        'state.count.strikes': strikes[index],
      })
      expect(latest.after.scoreboard).toStrictEqual(
        initial.after.scoreboard,
      )
      await expect(page.getByTestId('restore-balls')).toHaveText(
        balls[index]!,
      )
      await expect(page.getByTestId('restore-strikes')).toHaveText(
        strikes[index]!,
      )
      await expect(page.getByTestId('restore-history')).toHaveText(
        `${index + 1}件`,
      )
    }
    const replay = await page.evaluate(async () =>
      (
        window as unknown as {
          __ordinaryReplayFirst: () => Promise<{
            status: number
            count: number
            sameSlot: boolean
            advanced: boolean
            duplicate: boolean
          }>
        }
      ).__ordinaryReplayFirst(),
    )
    expect(replay).toStrictEqual({
      status: 200,
      count: 3,
      sameSlot: true,
      advanced: true,
      duplicate: true,
    })
    const reloadedRead = page.waitForResponse(isPrefix)
    await page.reload()
    const reloaded = await (await reloadedRead).json()
    expect(reloaded.read_kind).toBe('recorded-prefix')
    expect(reloaded.prefix_ref).toStrictEqual(latest.prefix_ref)
    expect(reloaded.after).toStrictEqual(latest.after)
    expect(reloaded.page).toStrictEqual(latest.page)
    expect(reloaded.last_entry).toStrictEqual(latest.last_entry)
    await expect(page.getByTestId('restore-balls')).toHaveText('2')
    await expect(page.getByTestId('restore-strikes')).toHaveText('1')
    await expect(page.getByTestId('restore-history')).toHaveText('3件')
    await expect(page.getByTestId('restore-plays')).toHaveText('3件')
    console.log(`PITCHLOG_ORDINARY_GAME_ID=${saved.id}`)
  } finally {
    page.off('response', observeRead)
    await stageMonitor.close()
  }
})

"""


# Chromium CDPで実commitのscalarだけを観測する試験専用monitor。
_MONITOR = r"""
// 試験専用。製品の値・関数・返値を変更せず、3地点のscalarだけを読む。
export function findStageLines(source) {
  const lines = source.split('\n')
  const send = lines.findIndex((line) => /if\s*\(!send\.sent\)/.test(line))
  const ack = lines.findIndex((line) =>
    /const ackApplication\s*=\s*await applyAckToSlot\(/.test(line),
  )
  const result = lines.findIndex(
    (line, index) => index > ack && /^\s*return\s*\{/.test(line),
  )
  if (send < 0 || ack <= send || result <= ack || result - ack > 12)
    throw new Error('stage-markers-invalid')
  return { send, ack, result }
}
const sendReasons = [
  'empty-request',
  'mixed-scope',
  'duplicate-d1',
  'game-id-mismatch',
  'd4-mismatch',
  'd5-mismatch',
  'invalid-d1',
  'undefined-slot-value',
  'invalid-event',
  'no-response',
  'response-not-interpreted',
]
const ackReasons = [
  'no-ack-received',
  'ack-not-interpretable',
  'no-target-slot',
  'preparation-failed',
  'not-transitioned',
  'persistence-failed',
]
const errorNames = [
  'ApiError',
  'ApiNetworkError',
  'ApiStaleAuthError',
  'ApiTenantVerificationError',
  'ApiSessionUnverifiedError',
  'DataCloneError',
  'TransactionInactiveError',
  'AbortError',
  'QuotaExceededError',
  'TypeError',
  'Error',
]
function expression(stage) {
  if (stage === 'send') return `JSON.stringify({
    sent:send.sent===true,
    reason:${JSON.stringify(sendReasons)}.includes(send.reason)
      ?send.reason:'none-or-other',
    errorName:${JSON.stringify(errorNames)}.includes(send.error?.name)
      ?send.error.name:'none-or-other',
    status:Number.isSafeInteger(send.status)
      &&send.status>=100&&send.status<=599?send.status:null
  })`
  if (stage === 'ack')
    return 'JSON.stringify({ackPresent:ack!==undefined&&ack!==null})'
  return `JSON.stringify({
    outcome:['applied','not-applied'].includes(ackApplication.outcome)
      ?ackApplication.outcome:'other',
    reason:${JSON.stringify(ackReasons)}.includes(ackApplication.reason)
      ?ackApplication.reason:'none-or-other'
  })`
}

export async function startOrdinaryStageMonitor(page) {
  const session = await page.context().newCDPSession(page)
  const packet = { ready: false, markerCount: 0, stages: [], fault: null }
  const owned = new Map()
  const pending = new Set()
  let closed = false
  let resolveReady
  const readyPromise = new Promise((resolve) => {
    resolveReady = resolve
  })
  const track = (job) => {
    pending.add(job)
    void job.finally(() => pending.delete(job))
  }
  const parsed = (event) => {
    if (
      closed ||
      !/\/src\/screens\/GameScreenPitchCommit\.ts(?:\?|$)/.test(event.url)
    )
      return
    track(
      (async () => {
        try {
          const { scriptSource } = await session.send(
            'Debugger.getScriptSource',
            { scriptId: event.scriptId },
          )
          const markers = findStageLines(scriptSource)
          for (const [stage, lineNumber] of Object.entries(markers)) {
            const result = await session.send('Debugger.setBreakpoint', {
              location: {
                scriptId: event.scriptId,
                lineNumber,
                columnNumber: 0,
              },
            })
            owned.set(result.breakpointId, stage)
          }
          packet.ready = true
          packet.markerCount = 3
          resolveReady(true)
        } catch {
          packet.fault = 'marker-or-install-failed'
          resolveReady(false)
        }
      })(),
    )
  }
  const paused = (event) => {
    track(
      (async () => {
        try {
          const stage = event.hitBreakpoints
            ?.map((id) => owned.get(id))
            .find(Boolean)
          if (stage && event.callFrames?.[0]) {
            const result = await session.send(
              'Debugger.evaluateOnCallFrame',
              {
                callFrameId: event.callFrames[0].callFrameId,
                expression: expression(stage),
                returnByValue: true,
                silent: true,
              },
            )
            if (
              !result.exceptionDetails &&
              typeof result.result?.value === 'string'
            ) {
              packet.stages.push({
                stage,
                ...JSON.parse(result.result.value),
              })
            } else packet.fault = 'scalar-evaluation-failed'
          }
        } catch {
          packet.fault = 'monitor-failed'
        } finally {
          try {
            await session.send('Debugger.resume')
          } catch {
            /* 既に再開済み */
          }
        }
      })(),
    )
  }
  session.on('Debugger.scriptParsed', parsed)
  session.on('Debugger.paused', paused)
  await session.send('Debugger.enable')
  return {
    async ready() {
      let timer
      const result = await Promise.race([
        readyPromise,
        new Promise((resolve) => {
          timer = setTimeout(() => resolve(false), 10000)
        }),
      ])
      clearTimeout(timer)
      if (!result) throw new Error('cdp-stage-monitor-not-ready')
    },
    snapshot() {
      return structuredClone(packet)
    },
    async close() {
      closed = true
      await Promise.allSettled([...pending])
      for (const breakpointId of owned.keys()) {
        try {
          await session.send('Debugger.removeBreakpoint', { breakpointId })
        } catch {
          /* 終了済み */
        }
      }
      session.off('Debugger.scriptParsed', parsed)
      session.off('Debugger.paused', paused)
      try { await session.send('Debugger.disable') }
      catch { /* 終了済みtargetでも元の試験失敗を覆わない。 */ }
      try { await session.detach() }
      catch { /* browser終了後のcleanupは元の失敗を維持する。 */ }
    },
  }
}

"""


def _terminal_spec(terminal: str) -> str:
    """旧3球specを保持し、同じ実UI手順の有限BB/HBP系列だけを追加する。"""
    if terminal not in {"walk", "hit-by-pitch"}:
        raise ValueError("未対応の画面系列")
    walk = terminal == "walk"
    results = (["batting-result.ball"] * 3 if walk else []) + [
        f"batting-result.{terminal}",
        "batting-result.ball",
    ]
    balls = ["1", "2", "3", "0", "1"] if walk else ["0", "1"]
    count = len(results)
    spec = _SPEC.replace("ordinary-prefix-v1", "play-prefix-v2")
    spec = spec.replace("recorded-prefix", "play-prefix")
    # v2は通常画面の既定。旧legacy query切替を新系列へ持ち込まない。
    spec = spec.replace(
        "    await page.evaluate(async () => {\n"
        "      const { router } = await import('/src/router.ts')\n"
        "      await router.replace({query:{recording:'play-prefix-v2'}})\n"
        "    })\n",
        "",
    )
    start = spec.index("    const results = [")
    end = spec.index("    for (let index = 0; index < results.length; index++)", start)
    spec = (
        spec[:start]
        + (
            f"    const results = {json.dumps(results)}\n"
            f"    const balls = {json.dumps(balls)}, "
            f"strikes = {json.dumps(['0'] * count)}\n"
        )
        + spec[end:]
    )
    spec = spec.replace(
        "        .selectOption(results[index]!)",
        "        .selectOption(results[index]!)\n"
        "      if (results[index] === 'batting-result.walk' || "
        "results[index] === 'batting-result.hit-by-pitch')\n"
        "        await page.getByTestId('terminal-next-batter')"
        ".selectOption({label:'2番の打者'})",
    )
    # 新系列は元ACKと真正GETを直接比較。旧3球のCDP診断/assertは削除しない。
    start = spec.index("      await page.waitForFunction(")
    end = spec.index("      try {\n        latest =", start)
    spec = spec[:start] + spec[end:]
    spec = spec.replace(
        ").__ordinarySafeDiagnostic\n          diag.contentTypeJson",
        ").__ordinarySafeDiagnostic ?? {}\n          diag.contentTypeJson",
    )
    spec = spec.replace(
        "        'state.count.strikes': strikes[index],",
        "        'state.count.strikes': strikes[index],\n"
        f"        'state.battingOrder': index >= {3 if walk else 0} ? '2' : '1',\n"
        f"        'state.runners': index >= {3 if walk else 0} ? 'first' : 'empty',",
    )
    spec = spec.replace(
        "        initial.after.scoreboard,",
        "        {...initial.after.scoreboard,walks: "
        + ("index >= 3 ? '1' : '0'" if walk else "'0'")
        + "},",
    )
    # 終端の確認済GETからreloadし、その実応答を次打者の通常球へ使う。
    boundary = "    }\n    const replay = await page.evaluate"
    insertion = """      if (index === results.length - 2) {
        const terminalRetry = await page.evaluate(async expected =>
          (window as unknown as {
            __ordinaryReplayFirst:(n:number)=>Promise<{
              sameSlot:boolean;duplicate:boolean;status:number
            }>
          }).__ordinaryReplayFirst(expected),index+1)
        expect(terminalRetry.status).toBe(200)
        expect(terminalRetry.sameSlot && terminalRetry.duplicate).toBe(true)
        const reloadRead=page.waitForResponse(isPrefix)
        await page.reload()
        const restored=await (await reloadRead).json()
        expect(restored.prefix_ref).toStrictEqual(latest.prefix_ref)
        expect(restored.runners).toStrictEqual(latest.runners)
        expect(restored.participants).toStrictEqual(latest.participants)
        expect(restored.after).toStrictEqual(latest.after)
        await expect(page.getByTestId('ordinary-pitch-result')).toBeVisible()
      }
    }
    const replay = await page.evaluate"""
    assert boundary in spec
    spec = spec.replace(boundary, insertion, 1)
    spec = spec.replace(
        "value: async () => {\n          if (originals.length !== 3)",
        "value: async (expected = 1) => {\n"
        "          if (originals.length !== expected)",
    )
    spec = spec.replace(
        "advanced: ack.advancedD3 === 3", "advanced: ack.advancedD3 >= event.d1"
    )
    spec = spec.replace("      count: 3,", "      count: 1,")
    spec = spec.replace("toHaveText('2')", "toHaveText('1')")
    spec = spec.replace(
        "toHaveText('1')\n    await expect(page.getByTestId('restore-history'))",
        "toHaveText('0')\n    await expect(page.getByTestId('restore-history'))",
    )
    spec = spec.replace("toHaveText('3件')", f"toHaveText('{count}件')")
    spec = spec.replace(
        "    let latest = initial",
        "    let latest = initial\n    let terminalRunners: unknown = null",
    )
    spec = spec.replace(
        "    expect(initial.prefix_ref.length).toBe('0')",
        "    expect(initial.prefix_ref.length).toBe('0')\n"
        "    expect(initial.last_source).toBeNull()",
    )
    terminal_index = 3 if walk else 0
    spec = spec.replace(
        "      await expect(page.getByTestId('restore-balls')).toHaveText(",
        f"      if(index === {terminal_index}) {{\n"
        "        const people=sent.payload.participants\n"
        "        terminalRunners=[{runnerId:people.batterId,\n"
        "          responsiblePitcherId:people.pitcherId,base:'1',\n"
        "          status:'継続',statusSource:'auto'}]\n"
        "        expect(latest.runners).toStrictEqual(terminalRunners)\n"
        "      }\n"
        f"      if(index >= {terminal_index}) {{\n"
        "        expect(latest.runners).toStrictEqual(terminalRunners)\n"
        "        const current=latest.page.items.find((item: {\n"
        "          play_row:{play_number:number}\n"
        "        })=>item.play_row.play_number===index+1)\n"
        "        expect(!!current).toBe(true)\n"
        "        expect(current.play_runners.length)"
        f".toBe(index==={terminal_index}?0:1)\n"
        "      }\n"
        "      await expect(page.getByTestId('restore-balls')).toHaveText(",
    )
    # 新terminal系列だけは終端自身を選ぶ。旧_SPECの初球再送は不変。
    spec = spec.replace(
        "const original = originals[0]!",
        "const original = originals[expected - 1]!",
    )
    spec = spec.replace(
        "count: originals.length,",
        "count: originals.length,\n"
        "            selectedD1: Number.isSafeInteger(event.d1)\n"
        "              && event.d1 >= 1 && event.d1 <= 5 ? event.d1 : null,\n"
        "            selectedResult: [\n"
        "              'batting-result.ball','batting-result.walk',\n"
        "              'batting-result.hit-by-pitch'\n"
        "            ].includes(event.payload?.calculation?.request?.t1?.resultId)\n"
        "              ? event.payload.calculation.request.t1.resultId : 'other',",
    )
    spec = spec.replace(
        "sameSlot:boolean;duplicate:boolean;status:number",
        "sameSlot:boolean;duplicate:boolean;status:number;\n"
        "              selectedD1:number|null;selectedResult:string",
    )
    spec = spec.replace(
        "expect(terminalRetry.status).toBe(200)",
        "expect(terminalRetry.status).toBe(200)\n"
        f"        expect(terminalRetry.selectedD1).toBe({4 if walk else 1})\n"
        "        expect(terminalRetry.selectedResult)"
        f".toBe('batting-result.{terminal}')",
    )
    spec = spec.replace(
        "      count: 1,",
        f"      count: 1, selectedD1: {count},\n"
        "      selectedResult:'batting-result.ball',",
    )
    spec = spec.replace("通常3球を保存", f"{terminal}と次打者通常球を保存")
    return spec


def write_browser_assets(
    directory: Path, frontend: Path, *, terminal: str | None = None
) -> Path:
    """実Playwrightを使うspec/configを書き、configの絶対PATHを返す。"""
    directory.mkdir(parents=True, exist_ok=False)
    module = (frontend / "node_modules/@playwright/test/index.mjs").as_posix()
    spec = (_SPEC if terminal is None else _terminal_spec(terminal)).replace(
        "__PLAYWRIGHT_MODULE__", module
    )
    (directory / "ordinary-screen.spec.ts").write_text(spec, encoding="utf-8")
    (directory / "ordinary-stage-monitor.mjs").write_text(_MONITOR, encoding="utf-8")
    config = directory / "playwright.config.mjs"
    config.write_text(
        f"import {{defineConfig,devices}} from {json.dumps(module)};\n"
        "export default defineConfig({testDir:'.',testMatch:'ordinary-screen.spec.ts',"
        "fullyParallel:false,workers:1,timeout:300000,"
        "use:{...devices['Desktop Chrome'],ignoreHTTPSErrors:true,"
        "trace:'off',screenshot:'off',video:'off'},reporter:'list',"
        f"outputDir:{json.dumps(str(directory / 'output'))}}});\n",
        encoding="utf-8",
    )
    return config
