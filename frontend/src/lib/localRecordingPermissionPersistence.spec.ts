import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { LocalRecordingSession } from './localRecordingSession'
import { GameScreenOrdinaryPitchController } from '../screens/GameScreenOrdinaryPitchController'
import * as transport from '../api/client.syncEvents'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { IDBFactory, IDBKeyRange } from 'fake-indexeddb'
import fixture from '../api/fixtures/lineupPrefixGame.v3.json'
import { isLineupPrefixGame } from '../api/lineupPrefixGame'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { useAuthStore } from '../stores/authStore'
import {
  readAuthIntent,
  withAuthIntent,
  writeAuthIntent,
} from '../api/authIntent'
import { GameStartPersistence } from './gameStartPersistence'
import {
  captureLocalRecordingSource,
  captureLocalPitchPage,
  readLocalPermission,
} from './localRecordingPermissionPersistence'

const head = structuredClone(fixture.value)
if (!isLineupPrefixGame(head)) throw new Error('fixture invalid')
const tenant = head.prefix_ref.tenantId
let pinia: Pinia
const grant = {
  tenant_id: tenant,
  game_id: head.id,
  device_id: tenant,
  start_request_id: head.prefix_ref.origin.eventId,
  d4: head.current_d4,
  away_lineup_id: head.lineups.away.lineup_id,
  home_lineup_id: head.lineups.home.lineup_id,
  recovery_generation: head.recovery_generation,
  recording_right_proof: 'unit-only-proof',
}
let currentGrant = { ...grant }
const page = {
  items: [{ key: 'pitch.fastball', display_name: '直球' }],
  next_cursor: null,
}
beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('IDBKeyRange', IDBKeyRange)
  vi.stubGlobal('isSecureContext', true)
  const held = new Set<string>()
  vi.stubGlobal('navigator', {
    locks: {
      request: (
        name: string,
        _options: unknown,
        callback: (lock: unknown) => unknown,
      ) => {
        if (held.has(name)) return Promise.resolve(callback(null))
        held.add(name)
        try {
          return Promise.resolve(callback({ name, mode: 'exclusive' })).finally(
            () => held.delete(name),
          )
        } catch (error) {
          held.delete(name)
          return Promise.reject(error)
        }
      },
    },
  })
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: tenant,
    teamName: 'test-team',
  })
  currentGrant = { ...grant }
  vi.spyOn(GameStartPersistence, 'open').mockResolvedValue({
    readStart: async () => ({ status: 'received', grant: currentGrant }),
    readDevice: async () => ({
      tenant_id: tenant,
      device_id: tenant,
      device_credential: 'unit-only-device',
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
})
afterEach(() => {
  disposePinia(pinia)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('真正readと語彙がそろうまで復帰資格を返さず、HTTP認証にはしない', async () => {
  await captureLocalRecordingSource(head, useAuthStore().authEpoch)
  expect(await readLocalPermission(head.id)).toBeNull()
  await captureLocalPitchPage(
    head.id,
    head.current_d4,
    null,
    page,
    useAuthStore().authEpoch,
  )
  const row = await readLocalPermission(head.id)
  expect(row?.head).toEqual(head)
  expect(row?.correlation.intentId).toBe(readAuthIntent()?.intentId)
  // cold Piniaを模した未検証状態でも、戻すのはlocal資格だけ。
  useAuthStore().signOut()
  expect(useAuthStore().isAuthenticated).toBe(false)
  expect((await readLocalPermission(head.id))?.head).toEqual(head)
  expect(useAuthStore().isAuthenticated).toBe(false)
})
it('古いauth epochや未検証状態からcapを書けない', async () => {
  const auth = useAuthStore()
  await expect(
    captureLocalRecordingSource(head, auth.authEpoch + 1),
  ).rejects.toThrow()
  auth.signOut()
  await expect(
    captureLocalRecordingSource(head, auth.authEpoch),
  ).rejects.toThrow()
})
it('新nonceは旧capを使わず、実確認後の新capは再確定できる', async () => {
  await captureLocalRecordingSource(head, useAuthStore().authEpoch)
  await captureLocalPitchPage(
    head.id,
    head.current_d4,
    null,
    page,
    useAuthStore().authEpoch,
  )
  const old = (await readLocalPermission(head.id))!
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: tenant,
    teamName: 'same-team-new-login',
  })
  expect(await readLocalPermission(head.id)).toBeNull()
  await captureLocalRecordingSource(head, useAuthStore().authEpoch)
  expect(await readLocalPermission(head.id)).toBeNull()
  await captureLocalPitchPage(
    head.id,
    head.current_d4,
    null,
    page,
    useAuthStore().authEpoch,
  )
  expect((await readLocalPermission(head.id))?.correlation.intentId).not.toBe(
    old.correlation.intentId,
  )
})
it('logoutと別の開始grantを旧資格へ補完しない', async () => {
  await captureLocalRecordingSource(head, useAuthStore().authEpoch)
  await captureLocalPitchPage(
    head.id,
    head.current_d4,
    null,
    page,
    useAuthStore().authEpoch,
  )
  currentGrant = { ...grant, recording_right_proof: 'different-proof' }
  expect(await readLocalPermission(head.id)).toBeNull()
  currentGrant = { ...grant }
  await withAuthIntent(() => writeAuthIntent('signed-out', null))
  expect(await readLocalPermission(head.id)).toBeNull()
})

it('実local境界と単一artifactで未検証sessionの2球を保存しcold復元する', async () => {
  const guest = createContext({})
  new Script(
    readFileSync(resolve('public/domain/pitchlog-domain.js'), 'utf8'),
  ).runInContext(guest)
  vi.stubGlobal(
    'PitchlogDomain',
    Object.getOwnPropertyDescriptor(guest, 'PitchlogDomain')!.value,
  )
  await captureLocalRecordingSource(head, useAuthStore().authEpoch)
  await captureLocalPitchPage(
    head.id,
    head.current_d4,
    null,
    page,
    useAuthStore().authEpoch,
  )
  useAuthStore().signOut()
  const scope = await LocalRecordingSession.restore(head.id)
  expect(scope).not.toBeNull()
  expect(scope!.identity().verified).toBe(false)
  const post = vi.spyOn(transport, 'postSyncEvents')
  const writer = {
    resolvePreconditions: () => ({
      topLevelHttps: true,
      sameBrowserProfile: true,
      sameBrowsingMode: true,
      sameStorageBucket: true,
      siteStorageAvailable: true,
      lockdownModeNotApplied: true,
    }),
    revalidateSingleWriter: () => scope!.current,
    lockManager: {
      request: async <T>(
        name: string,
        operation: (lock: unknown) => T | PromiseLike<T>,
      ) =>
        navigator.locks.request(
          name,
          { mode: 'exclusive', ifAvailable: true },
          async (lock) => await operation(lock),
        ),
    },
  }
  const local = new GameScreenOrdinaryPitchController(
    scope!.context,
    () => scope!.identity(),
    writer,
    scope!,
  )
  const observation = {
    resultId: 'batting-result.ball' as const,
    pitchTypeKey: 'pitch.fastball',
    screenX: 131.5,
    screenY: 124,
    view: 'catcher' as const,
    pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
    stance: null,
    battingSide: null,
  }
  try {
    expect(await local.inspectLocal()).toBe('ready')
    expect(
      await local.localEnqueue(observation, {
        tenantId: tenant,
        pitchTypeKeys: ['pitch.fastball'],
      }),
    ).toBe('queued-local')
    expect(
      await local.localEnqueue(observation, {
        tenantId: tenant,
        pitchTypeKeys: ['pitch.fastball'],
      }),
    ).toBe('queued-local')
    expect(local.context.after.stateFields['state.count.balls']).toBe('2')
  } finally {
    local.dispose()
  }
  const restarted = await LocalRecordingSession.restore(head.id)
  expect(restarted).not.toBeNull()
  const restored = new GameScreenOrdinaryPitchController(
    restarted!.context,
    () => restarted!.identity(),
    writer,
    restarted!,
  )
  try {
    expect(await restored.inspectLocal()).toBe('pending')
    expect(restored.context.after.stateFields['state.count.balls']).toBe('2')
    expect(post).not.toHaveBeenCalled()
    expect(useAuthStore().isAuthenticated).toBe(false)
  } finally {
    restored.dispose()
    scope!.dispose()
    restarted!.dispose()
  }
})
