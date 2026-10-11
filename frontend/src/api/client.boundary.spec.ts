import 'fake-indexeddb/auto'

import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../lib/queryClient'
import { AUTH_STORAGE_KEY, useAuthStore } from '../stores/authStore'
import { ApiError, ApiStaleAuthError, apiRequest } from './client'

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
const openedDatabases: IDBDatabase[] = []
const databaseNames: string[] = []

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function writeOtherTabAuth(teamName: string): string {
  const raw = JSON.stringify({
    version: 1,
    sessionId: crypto.randomUUID(),
    teamName,
    teamId: null,
  })
  localStorage.setItem(AUTH_STORAGE_KEY, raw)
  return raw
}

function deferredResponse(): {
  promise: Promise<Response>
  resolve: (response: Response) => void
} {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((done) => {
    resolve = done
  })
  return { promise, resolve }
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
      .get(queueRecord.id)
    request.onsuccess = () => resolve(request.result as QueueRecord | undefined)
    request.onerror = () => reject(request.error)
  })
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
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(async () => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
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

describe('apiRequest の認証越境', () => {
  it('401 はセッションとキャッシュを失効させ、未同期キューと他の bb.* キーを保つ', async () => {
    const databaseName = `bb-api-boundary-${crypto.randomUUID()}`
    databaseNames.push(databaseName)
    const firstConnection = await openTestDatabase(databaseName)
    await writeQueueRecord(firstConnection)
    firstConnection.close()
    for (const [key, value] of Object.entries(otherStorageValues)) {
      localStorage.setItem(key, value)
    }

    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A', teamId: 'team-a' })
    queryClient.setQueryData(['games', 4], 'A のデータ')
    expect(queryClient.getQueryCache().getAll()).toHaveLength(1)
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ error: { message: '期限切れ' } }, 401),
    )

    await expect(apiRequest('GET', '/games/4')).rejects.toBeInstanceOf(ApiError)

    expect(auth.sessionExpired).toBe(true)
    expect(queryClient.getQueryCache().getAll()).toEqual([])
    const reopened = await openTestDatabase(databaseName)
    try {
      expect(await readQueueRecord(reopened)).toStrictEqual(queueRecord)
    } finally {
      reopened.close()
    }
    for (const [key, value] of Object.entries(otherStorageValues)) {
      expect(localStorage.getItem(key)).toBe(value)
    }
  })

  it('送信前に別タブの B へ切り替え、A のキャッシュを消してから送る', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A', teamId: 'team-a' })
    queryClient.setQueryData(['games', 4], 'A のデータ')
    const previousEpoch = auth.authEpoch
    const savedB = writeOtherTabAuth('B')
    expect(auth.teamName).toBe('A')

    let stateAtFetch:
      | {
          teamName: string | null
          authEpoch: number
          cacheSize: number
        }
      | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(() => {
        stateAtFetch = {
          teamName: auth.teamName,
          authEpoch: auth.authEpoch,
          cacheSize: queryClient.getQueryCache().getAll().length,
        }
        return Promise.resolve(jsonResponse({ id: 4 }))
      }),
    )

    await expect(apiRequest('GET', '/games/4')).resolves.toStrictEqual({
      id: 4,
    })

    expect(stateAtFetch).toStrictEqual({
      teamName: 'B',
      authEpoch: previousEpoch + 1,
      cacheSize: 0,
    })
    expect(auth.teamName).toBe('B')
    expect(auth.authEpoch).toBe(previousEpoch + 1)
    expect(queryClient.getQueryCache().getAll()).toEqual([])
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBe(savedB)
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.credentials).toBe('include')
  })

  it('noAuthExpiry の 401 は認証とキャッシュを失効させない', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A', teamId: 'team-a' })
    const savedA = localStorage.getItem(AUTH_STORAGE_KEY)
    queryClient.setQueryData(['games', 4], 'A のデータ')
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ error: { message: '認証失敗' } }, 401),
    )

    await expect(
      apiRequest('POST', '/login', { noAuthExpiry: true }),
    ).rejects.toBeInstanceOf(ApiError)

    expect(auth.sessionExpired).toBe(false)
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.teamName).toBe('A')
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBe(savedA)
    expect(queryClient.getQueryData(['games', 4])).toBe('A のデータ')
  })

  it('往復中の認証切り替えでは A の応答を破棄し、呼び出し側は A のキャッシュへ入れない', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A', teamId: 'team-a' })
    const pending = deferredResponse()
    vi.mocked(fetch).mockReturnValue(pending.promise)
    const setQueryData = vi.spyOn(queryClient, 'setQueryData')
    const request = apiRequest<{ id: number }>('GET', '/games/4').then(
      (data) => {
        queryClient.setQueryData(['games', 4], data)
        return data
      },
    )
    writeOtherTabAuth('B')
    pending.resolve(jsonResponse({ id: 4 }))

    await expect(request).rejects.toBeInstanceOf(ApiStaleAuthError)

    expect(setQueryData).not.toHaveBeenCalled()
    expect(queryClient.getQueryData(['games', 4])).toBeUndefined()
    expect(auth.teamName).toBe('B')
  })

  it('往復中の切り替え後に古い 401 が届いても B の認証とキャッシュを保つ', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A', teamId: 'team-a' })
    const expireSession = vi.spyOn(auth, 'expireSession')
    const pending = deferredResponse()
    vi.mocked(fetch).mockReturnValue(pending.promise)
    const request = apiRequest('GET', '/games/4')
    const savedB = writeOtherTabAuth('B')
    window.dispatchEvent(new StorageEvent('storage', { key: AUTH_STORAGE_KEY }))
    expect(auth.teamName).toBe('B')
    queryClient.setQueryData(['team', 'B'], 'B のデータ')
    const response = jsonResponse({ error: { message: '古い認証' } }, 401)
    const readBody = vi.spyOn(response, 'text')
    pending.resolve(response)

    await expect(request).rejects.toMatchObject({
      name: 'ApiStaleAuthError',
      method: 'GET',
      path: '/games/4',
      status: 401,
    })

    expect(readBody).not.toHaveBeenCalled()
    expect(expireSession).not.toHaveBeenCalled()
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.teamName).toBe('B')
    expect(auth.sessionExpired).toBe(false)
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBe(savedB)
    expect(queryClient.getQueryData(['team', 'B'])).toBe('B のデータ')
    expect(queryClient.getQueryCache().getAll()).toHaveLength(1)
  })
})
