import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'
import { queryClient } from '../lib/queryClient'

export const AUTH_STORAGE_KEY = 'bb.auth'

type StoredAuth = {
  version: 1
  sessionId: string
  teamName: string
  teamId: string | null
}

const storageWarning = 'bb.auth の保存に失敗しました'
const storedAuthKeys = ['version', 'sessionId', 'teamName', 'teamId']
const sessionIdPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

function parseStoredAuth(raw: string): StoredAuth | null {
  if (raw.length > 4096) {
    return null
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }

  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return null
  }

  const value = parsed as Record<string, unknown>
  if (
    Object.keys(value).length !== storedAuthKeys.length ||
    !storedAuthKeys.every((key) => Object.hasOwn(value, key)) ||
    value.version !== 1 ||
    typeof value.sessionId !== 'string' ||
    !sessionIdPattern.test(value.sessionId) ||
    typeof value.teamName !== 'string' ||
    value.teamName.length === 0 ||
    (typeof value.teamId !== 'string' && value.teamId !== null)
  ) {
    return null
  }

  return value as StoredAuth
}

function removeStoredAuth(): boolean {
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY)
    return true
  } catch {
    console.warn(storageWarning)
    return false
  }
}

export const useAuthStore = defineStore('auth', () => {
  const teamName = ref<string | null>(null)
  const teamId = ref<string | null>(null)
  const sessionExpired = ref(false)
  const hasHydrated = ref(false)
  const authEpoch = ref(0)
  const isAuthenticated = computed(() => teamName.value !== null)
  let sessionId: string | null = null
  let detached = false
  let detachedRaw: string | null = null

  // 保存値は厳密に検査し、旧形式や壊れた値を認証状態へ取り込まない。
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY)
    if (raw !== null) {
      const saved = parseStoredAuth(raw)
      if (saved === null) {
        removeStoredAuth()
      } else {
        sessionId = saved.sessionId
        teamName.value = saved.teamName
        teamId.value = saved.teamId
      }
    }
  } catch {
    // ストレージを読めない場合は、未認証の初期状態を維持する。
  } finally {
    hasHydrated.value = true
  }

  function beginAuthChange(): void {
    queryClient.clear()
    authEpoch.value += 1
  }

  function enterDetachedState(): void {
    detached = true
    try {
      detachedRaw = localStorage.getItem(AUTH_STORAGE_KEY)
    } catch {
      detachedRaw = null
    }
  }

  function leaveDetachedState(): void {
    detached = false
    detachedRaw = null
  }

  function signIn(team: { teamName: string; teamId?: string | null }): void {
    beginAuthChange()
    sessionId = crypto.randomUUID()
    teamName.value = team.teamName
    teamId.value = team.teamId ?? null
    sessionExpired.value = false

    try {
      localStorage.setItem(
        AUTH_STORAGE_KEY,
        JSON.stringify({
          version: 1,
          sessionId,
          teamName: teamName.value,
          teamId: teamId.value,
        }),
      )
      leaveDetachedState()
    } catch {
      // 前のチームの保存値が残ることを避ける。
      try {
        localStorage.removeItem(AUTH_STORAGE_KEY)
      } catch {
        // 警告は値や例外を含めず、まとめて一度だけ出す。
      }
      console.warn(storageWarning)
      enterDetachedState()
    }
  }

  function setUnauthenticated(expired: boolean): void {
    teamName.value = null
    teamId.value = null
    sessionId = null
    sessionExpired.value = expired
  }

  function clearAuth(expired: boolean): void {
    setUnauthenticated(expired)
    if (removeStoredAuth()) {
      leaveDetachedState()
    } else {
      enterDetachedState()
    }
  }

  function signOut(): void {
    beginAuthChange()
    clearAuth(false)
  }

  function expireSession(): void {
    beginAuthChange()
    clearAuth(true)
  }

  function syncFromStorage(): void {
    let raw: string | null
    try {
      raw = localStorage.getItem(AUTH_STORAGE_KEY)
    } catch {
      if (!detached && isAuthenticated.value) {
        // 認証済みで保存値を照合できないときは、保存値を触らず失効させる。
        beginAuthChange()
        setUnauthenticated(true)
      }
      return
    }

    if (detached) {
      if (raw === detachedRaw) {
        return
      }
      // 別タブの新しい保存値は採らず、認証状態だけを失効させる。
      beginAuthChange()
      setUnauthenticated(true)
      detachedRaw = raw
      return
    }

    const saved = raw === null ? null : parseStoredAuth(raw)
    if (raw !== null && saved === null) {
      removeStoredAuth()
    }
    if ((saved?.sessionId ?? null) === sessionId) {
      return
    }

    beginAuthChange()
    sessionId = saved?.sessionId ?? null
    teamName.value = saved?.teamName ?? null
    teamId.value = saved?.teamId ?? null
    sessionExpired.value = false
  }

  function onStorage(event: StorageEvent): void {
    if (event.key !== AUTH_STORAGE_KEY && event.key !== null) {
      return
    }
    try {
      if (event.storageArea !== null && event.storageArea !== localStorage) {
        return
      }
    } catch {
      return
    }
    syncFromStorage()
  }

  window.addEventListener('storage', onStorage)
  onScopeDispose(() => window.removeEventListener('storage', onStorage))

  return {
    teamName,
    teamId,
    sessionExpired,
    hasHydrated,
    authEpoch,
    isAuthenticated,
    signIn,
    signOut,
    expireSession,
    syncFromStorage,
  }
})
