import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'
import { queryClient } from '../lib/queryClient'
import {
  AUTH_INTENT_KEY,
  readAuthIntent,
  type AuthEnvironmentReason,
} from '../api/authIntent'

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
  // 新しいstoreは未検証。前providerのメモリcacheも認証の証拠にしない。
  queryClient.clear()
  const teamName = ref<string | null>(null)
  const teamId = ref<string | null>(null)
  const sessionExpired = ref(false)
  const hasHydrated = ref(false)
  const authEpoch = ref(0)
  const sessionVerified = ref(false)
  const isAuthenticated = computed(
    () => sessionVerified.value && teamName.value !== null,
  )
  // 相関モードでは別タブの確認だけで共有意図を書き換えない。
  let correlated = false
  let observedIntentId: string | null = null
  let correlatedTenantId: string | null = null
  const explicitLoginRequired = ref(false)
  const environmentReason = ref<AuthEnvironmentReason | null>(null)
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
        // 保存値は認証の証拠にせず、変更検出用の識別値だけを保持する。
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
    sessionVerified.value = true
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
    sessionVerified.value = false
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

  function beginSessionVerification(): number {
    beginAuthChange()
    clearAuth(false)
    return authEpoch.value
  }

  function signOut(): void {
    beginAuthChange()
    clearAuth(false)
  }

  function expireSession(): void {
    beginAuthChange()
    clearAuth(true)
  }

  function beginCorrelatedVerification(intentId: string | null): number {
    correlated = true
    observedIntentId = intentId
    environmentReason.value = null
    const marker = intentId === null ? null : readAuthIntent()
    if (marker?.intentId === intentId && marker?.tenantId)
      correlatedTenantId = marker.tenantId
    beginAuthChange()
    setUnauthenticated(false)
    return authEpoch.value
  }

  function observeUnconfirmedIntent(intentId: string): void {
    // 世代相違の検出で破棄済みなら、同じ旧応答でcacheを二重破棄しない。
    if (isAuthenticated.value) beginCorrelatedVerification(intentId)
    else {
      correlated = true
      observedIntentId = intentId
    }
  }

  function adoptCorrelatedSession(
    intentId: string,
    tenantId: string,
    name: string,
  ): void {
    // 呼出元はlock内でintent/tenant/世代を検査済み。保存値から名前を採らない。
    correlated = true
    observedIntentId = intentId
    correlatedTenantId = tenantId
    teamId.value = tenantId
    teamName.value = name
    sessionVerified.value = true
    sessionExpired.value = false
    explicitLoginRequired.value = false
  }

  function requireExplicitLogin(): void {
    explicitLoginRequired.value = true
  }

  function failAuthEnvironment(reason: AuthEnvironmentReason): void {
    beginCorrelatedVerification(null)
    environmentReason.value = reason
    explicitLoginRequired.value = true
  }

  function syncFromStorage(): void {
    if (correlated) {
      let intent
      try {
        intent = readAuthIntent()
      } catch {
        if (isAuthenticated.value) {
          beginAuthChange()
          setUnauthenticated(false)
        }
        environmentReason.value = 'storage-unavailable'
        explicitLoginRequired.value = true
        return
      }
      if (
        (intent?.intentId ?? null) !== observedIntentId ||
        (isAuthenticated.value &&
          (intent?.phase !== 'expected' || intent?.tenantId !== teamId.value))
      ) {
        beginAuthChange()
        setUnauthenticated(false)
        observedIntentId = intent?.intentId ?? null
        // 旧タブから新しいtenantへの自動切替を禁止する。
        explicitLoginRequired.value = !(
          intent?.phase === 'verification-required' &&
          intent.tenantId !== null &&
          intent.tenantId === correlatedTenantId
        )
      }
      return
    }

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
    // 別タブの保存値もサーバー確認までは採用しない。
    setUnauthenticated(false)
    sessionId = saved?.sessionId ?? null
  }

  function onStorage(event: StorageEvent): void {
    if (
      event.key !== AUTH_STORAGE_KEY &&
      event.key !== AUTH_INTENT_KEY &&
      event.key !== null
    ) {
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
    beginSessionVerification,
    signOut,
    expireSession,
    syncFromStorage,
    beginCorrelatedVerification,
    adoptCorrelatedSession,
    observeUnconfirmedIntent,
    requireExplicitLogin,
    failAuthEnvironment,
    explicitLoginRequired,
    environmentReason,
  }
})
