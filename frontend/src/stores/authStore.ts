import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
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

function parseStoredAuth(raw: string): StoredAuth | null {
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
    value.sessionId.length === 0 ||
    typeof value.teamName !== 'string' ||
    value.teamName.length === 0 ||
    (typeof value.teamId !== 'string' && value.teamId !== null)
  ) {
    return null
  }

  return value as StoredAuth
}

function removeStoredAuth(): void {
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY)
  } catch {
    console.warn(storageWarning)
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
    } catch {
      // 前のチームの保存値が残ることを避ける。
      try {
        localStorage.removeItem(AUTH_STORAGE_KEY)
      } catch {
        // 警告は値や例外を含めず、まとめて一度だけ出す。
      }
      console.warn(storageWarning)
    }
  }

  function clearAuth(expired: boolean): void {
    teamName.value = null
    teamId.value = null
    sessionId = null
    sessionExpired.value = expired
    removeStoredAuth()
  }

  function signOut(): void {
    beginAuthChange()
    clearAuth(false)
  }

  function expireSession(): void {
    beginAuthChange()
    clearAuth(true)
  }

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
  }
})
