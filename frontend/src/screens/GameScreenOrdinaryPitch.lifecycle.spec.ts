// @vitest-environment-options {"url":"https://pitchlog.test"}
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { IDBFactory, IDBKeyRange } from 'fake-indexeddb'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { useAuthStore } from '../stores/authStore'
import { ordinaryContextFromRead } from '../api/recordedPrefixGame'
import * as options from '../api/pitchTypeOptions'
import * as transport from '../api/client.syncEvents'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { GameScreenOrdinaryPitchController } from './GameScreenOrdinaryPitchController'
import GameScreenOrdinaryPitch from './GameScreenOrdinaryPitch.vue'
import StrikeZone from '../components/zone/StrikeZone.vue'

const raw = JSON.parse(
  readFileSync(resolve('src/api/fixtures/recordedPrefixGame.v1.json'), 'utf8'),
).positive[0].value
const tenant = raw.prefix_ref.tenantId
const context = () => ({
  ...ordinaryContextFromRead(raw, tenant),
  serverStamp: {
    recoveryGeneration: raw.recovery_generation,
    checkpointAnchor: raw.checkpoint_anchor,
    lastSavedAt: raw.last_saved_at,
  },
})
let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('IDBKeyRange', IDBKeyRange)
  vi.stubGlobal('isSecureContext', true)
  const domain = createContext({})
  new Script(
    readFileSync(resolve('public/domain/pitchlog-domain.js'), 'utf8'),
  ).runInContext(domain)
  vi.stubGlobal(
    'PitchlogDomain',
    Object.getOwnPropertyDescriptor(domain, 'PitchlogDomain')!.value,
  )
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: tenant,
    teamName: '公開単体fixture',
  })
  vi.spyOn(options, 'readPitchTypeOptions').mockResolvedValue({
    items: [{ key: 'tenant.pitch.straight', display_name: '直球' }],
    next_cursor: null,
  })
  vi.spyOn(GameStartPersistence, 'open').mockResolvedValue({
    readDevice: async () => ({
      tenant_id: tenant,
      device_id: tenant,
      device_credential: 'unit-only-credential',
    }),
    readStart: async () => ({
      status: 'received',
      grant: {
        device_id: tenant,
        d4: raw.current_d4,
        away_lineup_id: raw.lineups.away.lineup_id,
        home_lineup_id: raw.lineups.home.lineup_id,
        recording_right_proof: 'unit-only-proof',
        recovery_generation: raw.recovery_generation,
      },
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
})
afterEach(() => {
  disposePinia(pinia)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

async function pendingScreen() {
  let respond!: () => void
  const gate = new Promise<void>((r) => {
    respond = r
  })
  const post = vi
    .spyOn(transport, 'postSyncEvents')
    .mockImplementation(async (request) => {
      await gate
      const body = transport.buildSyncEventRequestBody(request)
      if (!('events' in body)) throw new Error('単体要求形式不成立')
      const slot = request.slots[0]!
      return {
        sent: true,
        requestBody: body,
        response: {
          advancedD3: slot.d1,
          eventResults: [
            { d4: slot.d4, d1: slot.d1, d5: slot.d5, a5Result: '受理' },
          ],
        },
      }
    })
  const disposed = vi.spyOn(
    GameScreenOrdinaryPitchController.prototype,
    'dispose',
  )
  const wrapper = mount(GameScreenOrdinaryPitch, {
    props: { context: reactive(context()) },
    global: { plugins: [pinia] },
  })
  await vi.waitFor(() =>
    expect(wrapper.find('[data-testid="first-ball-pitch-type"]').exists()).toBe(
      true,
    ),
  )
  expect(window.location.protocol).toBe('https:')
  for (const name of ['profile', 'mode', 'bucket', 'lockdown'])
    await wrapper.get(`[data-testid="first-ball-env-${name}"]`).setValue(true)
  await wrapper
    .get('[data-testid="first-ball-pitch-type"]')
    .setValue('tenant.pitch.straight')
  wrapper.getComponent(StrikeZone).vm.$emit('tap', 131.5, 124)
  await flushPromises()
  await wrapper.get('[data-testid="first-ball-save"]').trigger('click')
  await vi.waitFor(() => expect(post).toHaveBeenCalledOnce())
  return { wrapper, post, disposed, respond }
}

it('送信中に全値同一DTOを再供給しても所有者を破棄せず実A5適用後savedを通知する', async () => {
  const { wrapper, disposed, respond } = await pendingScreen()
  try {
    await wrapper.setProps({ context: structuredClone(context()) })
    expect(disposed).not.toHaveBeenCalled()
    respond()
    await vi.waitFor(() => expect(wrapper.emitted('saved')).toHaveLength(1))
  } finally {
    respond()
    wrapper.unmount()
  }
})

it.each([
  'game',
  'd4',
  'recovery',
  'checkpoint',
  'rules',
  'state',
  'position',
  'auth',
] as const)(
  '送信中でも実%s変更は旧所有者を破棄し旧ACKからsavedを通知しない',
  async (axis) => {
    const { wrapper, disposed, respond } = await pendingScreen()
    try {
      const next = structuredClone(context())
      if (axis === 'game') next.game.id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
      if (axis === 'd4') next.game.current_d4 = 'new-recording-generation'
      if (axis === 'recovery') next.serverStamp.recoveryGeneration = '2'
      if (axis === 'checkpoint')
        next.serverStamp.checkpointAnchor = {
          id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
          revision: '1',
          history_version: '1',
        }
      if (axis === 'rules')
        next.rules = { ...next.rules, regulationInnings: '9' }
      if (axis === 'state')
        next.after = {
          ...next.after,
          stateFields: { ...next.after.stateFields, 'state.count.balls': '1' },
        }
      if (axis === 'position')
        next.nextPosition = { ...next.nextPosition, d1: '2' }
      if (axis === 'auth') useAuthStore().expireSession()
      else await wrapper.setProps({ context: next })
      await vi.waitFor(() => expect(disposed).toHaveBeenCalled())
      respond()
      await flushPromises()
      expect(wrapper.emitted('saved')).toBeUndefined()
    } finally {
      respond()
      wrapper.unmount()
    }
  },
)

it('同じDTO参照のrecovery世代が変わった場合も旧送信を失効させる', async () => {
  const { wrapper, disposed, respond } = await pendingScreen()
  try {
    Object.assign(wrapper.props('context').serverStamp!, {
      recoveryGeneration: '2',
    })
    await vi.waitFor(() => expect(disposed).toHaveBeenCalled())
    respond()
    await flushPromises()
    expect(wrapper.emitted('saved')).toBeUndefined()
  } finally {
    respond()
    wrapper.unmount()
  }
})
