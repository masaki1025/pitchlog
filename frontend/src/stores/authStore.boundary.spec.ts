import 'fake-indexeddb/auto'

import { VueQueryPlugin, useQuery } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { defineComponent, h, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { queryClient } from '../lib/queryClient'
import { AUTH_STORAGE_KEY, useAuthStore } from './authStore'

type QueueRecord = {
  id: string
  ownerTeamId: string
  payload: { kind: string; count: number }
}

const queueRecord: QueueRecord = {
  id: 'q1',
  ownerTeamId: 'team-a',
  payload: { kind: 'pitch', count: 3 },
}
const otherStorageValues = {
  'bb.sync': '{"pending":1}',
  'bb.input-settings': '{"zone":"left"}',
}

let pinia: Pinia
let databaseSequence = 0
const mountedWrappers: Array<{ unmount(): void }> = []
const openedDatabases: IDBDatabase[] = []
const databaseNames: string[] = []

function mountQueryView(keyed: boolean): ReturnType<typeof mount> {
  // 試験用の親子部品をこの spec 内で定義する。
  // eslint-disable-next-line vue/one-component-per-file
  const QueryChild = defineComponent({
    setup() {
      const store = useAuthStore()
      const { data } = useQuery({
        queryKey: ['games', 4],
        queryFn: async () => `${store.teamName} のデータ`,
      })
      return () => h('p', data.value ?? '')
    },
  })
  // eslint-disable-next-line vue/one-component-per-file
  const QueryParent = defineComponent({
    setup() {
      const store = useAuthStore()
      return () =>
        h(
          QueryChild,
          keyed
            ? { key: store.authEpoch }
            : { 'data-auth-epoch': store.authEpoch },
        )
    },
  })
  const wrapper = mount(QueryParent, {
    global: { plugins: [pinia, [VueQueryPlugin, { queryClient }]] },
  })
  mountedWrappers.push(wrapper)
  return wrapper
}

async function showTeamA(keyed: boolean): Promise<ReturnType<typeof mount>> {
  const store = useAuthStore()
  store.signIn({ teamName: 'チーム A', teamId: 'team-a' })
  const wrapper = mountQueryView(keyed)
  await flushPromises()
  expect(wrapper.text()).toContain('チーム A のデータ')
  return wrapper
}

function switchOtherTabToB(): void {
  localStorage.setItem(
    AUTH_STORAGE_KEY,
    JSON.stringify({
      version: 1,
      sessionId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
      teamName: 'チーム B',
      teamId: 'team-b',
    }),
  )
  window.dispatchEvent(new StorageEvent('storage', { key: AUTH_STORAGE_KEY }))
}

function openTestDatabase(name: string): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(name, 1)
    request.onupgradeneeded = () => {
      request.result.createObjectStore('queue', { keyPath: 'id' })
    }
    request.onsuccess = () => {
      openedDatabases.push(request.result)
      resolve(request.result)
    }
    request.onerror = () => reject(request.error)
  })
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onabort = () => reject(transaction.error)
  })
}

async function writeQueueRecord(database: IDBDatabase): Promise<void> {
  const transaction = database.transaction('queue', 'readwrite')
  const completion = transactionDone(transaction)
  transaction.objectStore('queue').put(queueRecord)
  await completion
}

function readQueueRecord(
  database: IDBDatabase,
): Promise<QueueRecord | undefined> {
  return new Promise((resolve, reject) => {
    const request = database
      .transaction('queue', 'readonly')
      .objectStore('queue')
      .get('q1')
    request.onsuccess = () => resolve(request.result as QueueRecord | undefined)
    request.onerror = () => reject(request.error)
  })
}

async function prepareQueueFixture(): Promise<string> {
  databaseSequence += 1
  const name = `bb-sync-test-${databaseSequence}`
  databaseNames.push(name)
  const database = await openTestDatabase(name)
  await writeQueueRecord(database)
  database.close()
  for (const [key, value] of Object.entries(otherStorageValues)) {
    localStorage.setItem(key, value)
  }
  return name
}

async function expectQueueAndOtherKeysUntouched(name: string): Promise<void> {
  const database = await openTestDatabase(name)
  try {
    expect(await readQueueRecord(database)).toStrictEqual(queueRecord)
  } finally {
    database.close()
  }
  for (const [key, value] of Object.entries(otherStorageValues)) {
    expect(localStorage.getItem(key)).toBe(value)
  }
}

function deleteDatabase(name: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name)
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('試験用 DB を削除できません'))
  })
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  localStorage.clear()
  queryClient.clear()
})

afterEach(async () => {
  for (const wrapper of mountedWrappers) {
    wrapper.unmount()
  }
  mountedWrappers.length = 0
  disposePinia(pinia)
  queryClient.clear()
  for (const database of openedDatabases) {
    database.close()
  }
  openedDatabases.length = 0
  for (const name of databaseNames) {
    await deleteDatabase(name)
  }
  databaseNames.length = 0
})

describe('authStore の越境', () => {
  it('signOut を経た A から B への切り替えで A のキャッシュを消す', () => {
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A', teamId: 'team-a' })
    queryClient.setQueryData(['games', 4], 'A のデータ')

    store.signOut()
    store.signIn({ teamName: 'チーム B', teamId: 'team-b' })

    expect(queryClient.getQueryData(['games', 4])).toBeUndefined()
    expect(queryClient.getQueryCache().getAll()).toEqual([])
  })

  it('直接 signIn する A から B への切り替えで A のキャッシュを消す', () => {
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A', teamId: 'team-a' })
    queryClient.setQueryData(['games', 4], 'A のデータ')

    store.signIn({ teamName: 'チーム B', teamId: 'team-b' })

    expect(queryClient.getQueryData(['games', 4])).toBeUndefined()
    expect(queryClient.getQueryCache().getAll()).toEqual([])
  })

  it('authEpoch で鍵付けした画面は直接 signIn 後に A の表示を残さない', async () => {
    const wrapper = await showTeamA(true)
    const store = useAuthStore()

    store.signIn({ teamName: 'チーム B', teamId: 'team-b' })
    await nextTick()
    await flushPromises()

    expect(wrapper.text()).not.toContain('チーム A のデータ')
    expect(wrapper.text()).toContain('チーム B のデータ')
  })

  it('authEpoch で鍵付けした画面は別タブ切り替え後に A の表示を残さない', async () => {
    const wrapper = await showTeamA(true)

    switchOtherTabToB()
    await nextTick()
    await flushPromises()

    expect(wrapper.text()).not.toContain('チーム A のデータ')
    expect(wrapper.text()).toContain('チーム B のデータ')
  })

  it('authEpoch の鍵がない画面はキャッシュ消去後も A の表示が残る', async () => {
    const wrapper = await showTeamA(false)
    const store = useAuthStore()

    store.signIn({ teamName: 'チーム B', teamId: 'team-b' })
    await nextTick()
    await flushPromises()

    expect(queryClient.getQueryCache().getAll()).toEqual([])
    expect(wrapper.text()).toContain('チーム A のデータ')
  })

  it('失効後に A へ再ログインしても未同期キューと他のキーを保つ', async () => {
    const databaseName = await prepareQueueFixture()
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A', teamId: 'team-a' })

    store.expireSession()
    store.signIn({ teamName: 'チーム A', teamId: 'team-a' })

    await expectQueueAndOtherKeysUntouched(databaseName)
  })

  it('signOut 後に B へログインしても未同期キューと他のキーを保つ', async () => {
    const databaseName = await prepareQueueFixture()
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A', teamId: 'team-a' })

    store.signOut()
    store.signIn({ teamName: 'チーム B', teamId: 'team-b' })

    await expectQueueAndOtherKeysUntouched(databaseName)
  })
})
