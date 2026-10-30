import { IDBFactory } from 'fake-indexeddb'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { setActivePinia } from 'pinia'
import { defineComponent, h, shallowRef } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import type { GameStartRequest } from '../api/gameStart'
import type { PreparingGame } from '../api/games'
import { installAppProviders, pinia } from '../appProviders'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { queryClient } from '../lib/queryClient'
import { createAppRouter } from '../router'
import { useAuthStore } from '../stores/authStore'
import { useGameStartProvider } from './GameScreenStartProvider'
import type { EntrySupply, PreparingReadDetail } from './GameScreenEntryTypes'

const tenant = '10000000-0000-4000-8000-000000000001'
const game = '10000000-0000-4000-8000-000000000002'
const requestId = '10000000-0000-4000-8000-000000000003'
const device = '10000000-0000-4000-8000-000000000004'
const other = '20000000-0000-4000-8000-000000000001'
const credential = 'public-test-device-credential'
const proof = 'public-test-right-proof'
const pair = {
  tenant_id: tenant,
  device_id: device,
  device_credential: credential,
}
const path = `/games/${game}/record`
const preparingGame: PreparingGame = {
  id: game,
  scheduled_at: '2026-10-26T10:00:00+09:00',
  game_type_key: 'game_other',
  tournament_key: 'none',
  away_team_record_id: other,
  home_team_record_id: tenant,
  plate_umpire: null,
  section_label: null,
  week_label: null,
  day_label: null,
  game_number_label: null,
  status: 'preparing',
  applied_rules: { dh: false },
}
const rows = Array.from({ length: 9 }, (_, index) => ({
  player_id: `30000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
  batting_order: index + 1,
  fielding_position: { kind: 'fielding', position: String(index + 1) },
}))
const lineups = { away: rows, home: structuredClone(rows) }
const original = {
  start_request_id: requestId,
  device_id: device,
  device_credential: credential,
  ...lineups,
}
const owner = {
  tenant_id: tenant,
  game_id: game,
  start_request_id: requestId,
  device_id: device,
}
const wrappers: VueWrapper[] = []
const stores: GameStartPersistence[] = []
type Provider = ReturnType<typeof useGameStartProvider>

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
function grant(request: GameStartRequest = original) {
  return {
    ...owner,
    start_request_id: request.start_request_id,
    d4: 'opaque-reference',
    recovery_generation: '1',
    recording_right_proof: proof,
    started_at: '2026-10-26T12:34:56Z',
    away_lineup_id: other,
    home_lineup_id: game,
  }
}
function response(value: unknown, init?: RequestInit, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'X-Pitchlog-Tenant-Match': '1',
      'X-Pitchlog-Tenant-Challenge':
        new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge') ?? '',
    },
  })
}
async function store() {
  const value = await GameStartPersistence.open()
  stores.push(value)
  return value
}
async function view() {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  const preparing = shallowRef<EntrySupply<PreparingReadDetail> | null>({
    tenantId: tenant,
    authEpoch: useAuthStore(pinia).authEpoch,
    path,
    requestKey: game,
    status: 'ready',
    data: {
      tenantId: tenant,
      gameId: game,
      label: '試合',
      saved: preparingGame,
    },
  })
  let provider!: Provider
  const probe = defineComponent({
    setup() {
      provider = useGameStartProvider(preparing)
      return () => h('p', provider.state.value.message)
    },
  })
  const wrapper = mount(probe, {
    global: { plugins: [{ install: installAppProviders }, router] },
  })
  wrappers.push(wrapper)
  await vi.waitFor(() => expect(provider.state.value.phase).not.toBe('loading'))
  return { provider, wrapper, router, preparing }
}
function nonSecret(provider: Provider) {
  const value = JSON.stringify(provider.state.value)
  expect(value).not.toContain(credential)
  expect(value).not.toContain(proof)
  expect(value).not.toContain('opaque-reference')
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(pinia)
  vi.stubGlobal('navigator', {
    onLine: true,
    locks: {
      request: vi.fn(async (_n, _o, action) => action({ name: 'start-unit' })),
    },
  })
  vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('indexedDB', new IDBFactory())
  setVerifiedAuthForTest(useAuthStore(pinia), {
    teamName: '試験',
    teamId: tenant,
  })
  vi.stubGlobal(
    'fetch',
    vi
      .fn<typeof fetch>()
      .mockImplementation(async (url, init) =>
        response(
          String(url).endsWith('/devices/enroll')
            ? pair
            : grant(JSON.parse(init?.body as string)),
          init,
        ),
      ),
  )
})
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
  for (const handle of stores.splice(0)) handle.close()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  queryClient.clear()
})

it('実IDBへ端末資格を保存してからだけ開始を許す', async () => {
  const release = deferred<void>()
  const committed = deferred<void>()
  const actual = GameStartPersistence.prototype.rememberDevice
  vi.spyOn(GameStartPersistence.prototype, 'rememberDevice').mockImplementation(
    async function (this: GameStartPersistence, ...args) {
      await actual.apply(this, args)
      committed.resolve()
      await release.promise
    },
  )
  const { provider } = await view()
  expect(provider.canEnroll.value).toBe(true)
  const pending = provider.enroll()
  await committed.promise
  expect(provider.canStart.value).toBe(false)
  expect(await (await store()).readDevice(tenant)).toEqual(pair)
  expect(fetch).toHaveBeenCalledTimes(1)
  release.resolve()
  await pending
  expect(provider.canStart.value).toBe(true)
  nonSecret(provider)
})

it('要求の保存完了前はHTTP0、応答の保存完了前は受領表示0', async () => {
  await (await store()).rememberDevice(pair, tenant)
  const prepareRelease = deferred<void>()
  const prepared = deferred<void>()
  const grantRelease = deferred<void>()
  const granted = deferred<void>()
  const prepare = GameStartPersistence.prototype.prepareStart
  const remember = GameStartPersistence.prototype.rememberGrant
  vi.spyOn(GameStartPersistence.prototype, 'prepareStart').mockImplementation(
    async function (this: GameStartPersistence, ...args) {
      const value = await prepare.apply(this, args)
      prepared.resolve()
      await prepareRelease.promise
      return value
    },
  )
  vi.spyOn(GameStartPersistence.prototype, 'rememberGrant').mockImplementation(
    async function (this: GameStartPersistence, ...args) {
      const value = await remember.apply(this, args)
      granted.resolve()
      await grantRelease.promise
      return value
    },
  )
  const { provider } = await view()
  const pending = provider.start(lineups)
  await prepared.promise
  expect(fetch).not.toHaveBeenCalled()
  const saved = await (await store()).readStart(tenant, game)
  expect(saved?.status).toBe('pending')
  prepareRelease.resolve()
  await granted.promise
  expect(provider.state.value.phase).toBe('sending')
  expect(provider.state.value.startedAt).toBeNull()
  expect((await (await store()).readStart(tenant, game))?.status).toBe(
    'received',
  )
  grantRelease.resolve()
  await pending
  expect(provider.state.value.phase).toBe('received')
  expect(
    JSON.parse(vi.mocked(fetch).mock.calls[0]![1]?.body as string),
  ).toEqual(saved?.request)
  expect(fetch).toHaveBeenCalledTimes(1)
  nonSecret(provider)
})

it('保存拒否時は送信せず、下書きを成功にしない', async () => {
  await (await store()).rememberDevice(pair, tenant)
  vi.spyOn(GameStartPersistence.prototype, 'prepareStart').mockRejectedValue(
    new Error(credential),
  )
  const { provider } = await view()
  await provider.start(lineups)
  expect(fetch).not.toHaveBeenCalled()
  expect(provider.state.value.phase).toBe('failed')
  expect(await (await store()).readStart(tenant, game)).toBeNull()
  nonSecret(provider)
})

it('復元したpendingは自動送信せず、元IDと全payloadの明示照会だけ行う', async () => {
  const storage = await store()
  await storage.rememberDevice(pair, tenant)
  await storage.prepareStart(tenant, game, original)
  const { provider } = await view()
  expect(provider.state.value.phase).toBe('unknown')
  expect(provider.canStart.value).toBe(false)
  expect(fetch).not.toHaveBeenCalled()
  await provider.start(lineups)
  expect(fetch).not.toHaveBeenCalled()
  await provider.resolve()
  expect(vi.mocked(fetch).mock.calls[0]![0]).toBe(
    `/api/games/${game}/start/resolve`,
  )
  expect(
    JSON.parse(vi.mocked(fetch).mock.calls[0]![1]?.body as string),
  ).toEqual(original)
  expect(provider.state.value.phase).toBe('received')
  nonSecret(provider)
})

it('503で元要求をunknownに保持し、明示照会は同要求を再利用する', async () => {
  await (await store()).rememberDevice(pair, tenant)
  vi.mocked(fetch).mockImplementationOnce(async (_url, init) =>
    response({ error: { message: credential } }, init, 503),
  )
  const { provider } = await view()
  await provider.start(lineups)
  const previous = await (await store()).readStart(tenant, game)
  expect(previous?.status).toBe('unknown')
  expect(provider.canStart.value).toBe(false)
  expect(provider.canResolve.value).toBe(true)
  expect(fetch).toHaveBeenCalledTimes(1)
  await provider.resolve()
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(
    JSON.parse(vi.mocked(fetch).mock.calls[1]![1]?.body as string),
  ).toEqual(previous?.request)
  expect((await (await store()).readStart(tenant, game))?.owner).toEqual(
    previous?.owner,
  )
  nonSecret(provider)
})

it('receivedの復元を現在の記録権へ昇格せず自動再確認もしない', async () => {
  const storage = await store()
  await storage.rememberDevice(pair, tenant)
  await storage.prepareStart(tenant, game, original)
  await storage.rememberGrant(owner, grant())
  const { provider } = await view()
  expect(provider.state.value.phase).toBe('received')
  expect(provider.state.value.message).toContain('現在の記録権は未確認')
  expect(provider.canStart.value).toBe(false)
  expect(provider.canResolve.value).toBe(false)
  expect(fetch).not.toHaveBeenCalled()
  nonSecret(provider)
})

it('別tabのpendingを検出すると新IDによる送信を行わない', async () => {
  const storage = await store()
  await storage.rememberDevice(pair, tenant)
  const first = await view()
  const second = await view()
  const pending = deferred<Response>()
  vi.mocked(fetch).mockReturnValueOnce(pending.promise)
  const sending = first.provider.start(lineups)
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  await second.provider.start(lineups)
  expect(second.provider.state.value.phase).toBe('unknown')
  expect(fetch).toHaveBeenCalledTimes(1)
  const init = vi.mocked(fetch).mock.calls[0]![1]
  pending.resolve(response(grant(JSON.parse(init?.body as string)), init))
  await sending
  expect(first.provider.state.value.phase).toBe('received')
})

it('認証切替後の遅延応答は表示せず旧要求を消さない', async () => {
  await (await store()).rememberDevice(pair, tenant)
  const pending = deferred<Response>()
  vi.mocked(fetch).mockReturnValueOnce(pending.promise)
  const { provider } = await view()
  const sending = provider.start(lineups)
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  const init = vi.mocked(fetch).mock.calls[0]![1]
  setVerifiedAuthForTest(useAuthStore(pinia), { teamName: '別', teamId: other })
  pending.resolve(response(grant(JSON.parse(init?.body as string)), init))
  await sending
  await flushPromises()
  expect(provider.state.value.startedAt).toBeNull()
  expect(provider.state.value.phase).not.toBe('received')
  expect((await (await store()).readStart(tenant, game))?.status).toBe(
    'pending',
  )
  expect(await (await store()).readStart(other, game)).toBeNull()
  nonSecret(provider)
})

it('準備中の別scope供給やofflineから開始しない', async () => {
  await (await store()).rememberDevice(pair, tenant)
  const { provider, preparing } = await view()
  preparing.value = { ...preparing.value!, tenantId: other }
  await provider.start(lineups)
  expect(fetch).not.toHaveBeenCalled()
  preparing.value = { ...preparing.value!, tenantId: tenant }
  Object.assign(navigator, { onLine: false })
  window.dispatchEvent(new Event('offline'))
  await provider.start(lineups)
  expect(fetch).not.toHaveBeenCalled()
  expect(provider.canStart.value).toBe(false)
})

it('安全なstorageが利用できなければ輸送を開かない', async () => {
  vi.stubGlobal('isSecureContext', false)
  const { provider } = await view()
  expect(provider.state.value.phase).toBe('failed')
  expect(provider.canEnroll.value).toBe(false)
  expect(provider.canStart.value).toBe(false)
  await provider.enroll()
  await provider.start(lineups)
  expect(fetch).not.toHaveBeenCalled()
})
