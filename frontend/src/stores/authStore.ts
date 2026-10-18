import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'
import {
  AUTH_INTENT_KEY,
  AUTH_UNCERTAIN_KEY,
  AUTH_UNCERTAIN_ACK_KEY,
  readAuthUncertainty,
  publishAuthUncertainty,
  acknowledgeAuthUncertainty,
  AuthEnvironmentError,
  assertAuthIntentLockHeld,
  readAuthIntent,
  withAuthIntent,
  writeAuthIntent,
  type AuthEnvironmentReason,
} from '../api/authIntent'
import { queryClient } from '../lib/queryClient'

/** 旧形式は移行時に破棄し、認証情報として復元しない。 */
export const AUTH_STORAGE_KEY = 'bb.auth'

export const useAuthStore = defineStore('auth', () => {
  queryClient.clear()
  const teamName = ref<string | null>(null)
  const teamId = ref<string | null>(null)
  const sessionExpired = ref(false)
  const hasHydrated = ref(false)
  const authEpoch = ref(0)
  const sessionVerified = ref(false)
  const explicitLoginRequired = ref(false)
  const automaticVerificationBlocked = ref(false)
  const environmentReason = ref<AuthEnvironmentReason | null>(null)
  const isAuthenticated = computed(() => sessionVerified.value)
  let observedIntentId: string | null = null
  let expectedTenantId: string | null = null
  let observedLegacy: string | null = null
  let observedNotice: string | null = null
  let observedAck: string | null = null

  try {
    localStorage.removeItem(AUTH_STORAGE_KEY)
    observedIntentId = readAuthIntent()?.intentId ?? null
    const uncertainty = readAuthUncertainty()
    observedNotice = uncertainty.notice
    observedAck = uncertainty.ack
    if (!uncertainty.confirmed) automaticVerificationBlocked.value = true
  } catch {
    // 復元はしない。具体的な環境失敗は認証操作で表示する。
  } finally {
    hasHydrated.value = true
  }

  const canReverify = computed(() => {
    void authEpoch.value
    if (explicitLoginRequired.value) return false
    try {
      const marker = readAuthIntent()
      return (
        marker?.tenantId !== null &&
        marker?.tenantId !== undefined &&
        (marker.phase === 'expected' ||
          marker.phase === 'verification-required')
      )
    } catch {
      return false
    }
  })

  function discard(expired = false): void {
    queryClient.clear()
    authEpoch.value += 1
    sessionVerified.value = false
    teamName.value = null
    teamId.value = null
    sessionExpired.value = expired
  }

  function beginCorrelatedVerification(intentId: string | null): number {
    discard()
    observedIntentId = intentId
    environmentReason.value = null
    const marker = intentId === null ? null : readAuthIntent()
    if (marker?.intentId === intentId && marker?.tenantId)
      expectedTenantId = marker.tenantId
    if (marker?.intentId === intentId && marker?.phase === 'pending')
      explicitLoginRequired.value = false
    try {
      localStorage.removeItem(AUTH_STORAGE_KEY)
      observedLegacy = null
    } catch {
      /* 旧形式は認証へ採用しない。 */
    }
    return authEpoch.value
  }

  function adoptCorrelatedSession(
    intentId: string,
    tenantId: string,
    name: string,
    notice: string | null,
  ): void {
    // 公開旧signInを廃止。相関検査を行った同期lock内だけから採用する。
    assertAuthIntentLockHeld()
    const marker = readAuthIntent()
    if (
      marker?.intentId !== intentId ||
      marker.phase !== 'expected' ||
      marker.tenantId !== tenantId ||
      name.length === 0 ||
      observedIntentId !== intentId
    )
      throw new Error('認証意図とsessionを照合できません')
    acknowledgeAuthUncertainty(notice)
    observedNotice = notice
    observedAck = notice
    expectedTenantId = tenantId
    teamId.value = tenantId
    teamName.value = name
    sessionVerified.value = true
    sessionExpired.value = false
    explicitLoginRequired.value = false
    automaticVerificationBlocked.value = false
    environmentReason.value = null
  }

  function observeUnconfirmedIntent(intentId: string): void {
    if (isAuthenticated.value) beginCorrelatedVerification(intentId)
    else if (observedIntentId !== intentId) {
      // cacheは既に破棄済みでも、確認待ちの旧要求と入力は新しい意図へ持ち越さない。
      authEpoch.value += 1
      observedIntentId = intentId
    }
  }

  async function invalidateUncertainCookie(): Promise<void> {
    try {
      // Cookieはlockに従わない。競合中でも他タブへ拒否だけを通知する。
      publishAuthUncertainty()
      syncFromStorage()
      await withAuthIntent((marker) => {
        syncFromStorage()
        // 1要求から1回だけ呼ぶ。異なる旧Cookie応答は未確認中でも新しい意図にする。
        const next = writeAuthIntent(
          'verification-required',
          marker?.tenantId ?? null,
        )
        observeUnconfirmedIntent(next.intentId)
        automaticVerificationBlocked.value = true
      })
    } catch (error) {
      if (error instanceof AuthEnvironmentError)
        failAuthEnvironment(error.reason)
      else {
        discard()
        requireExplicitLogin()
      }
    }
  }

  function requireExplicitLogin(): void {
    explicitLoginRequired.value = true
  }

  function failAuthEnvironment(reason: AuthEnvironmentReason): void {
    if (reason === 'lock-busy') {
      let marker = null
      try {
        marker = readAuthIntent()
      } catch {
        /* 読取不能時は採用しない。 */
      }
      const required = explicitLoginRequired.value
      const nextId = marker?.intentId ?? null
      if (sessionVerified.value) beginCorrelatedVerification(nextId)
      else if (nextId !== observedIntentId) {
        authEpoch.value += 1
        observedIntentId = nextId
      }
      explicitLoginRequired.value = required
    } else {
      discard()
      explicitLoginRequired.value = true
    }
    environmentReason.value = reason
    automaticVerificationBlocked.value = true
  }

  function syncFromStorage(): void {
    let marker, legacy, uncertainty
    try {
      marker = readAuthIntent()
      legacy = localStorage.getItem(AUTH_STORAGE_KEY)
      uncertainty = readAuthUncertainty()
    } catch {
      if (sessionVerified.value) discard()
      environmentReason.value = 'storage-unavailable'
      explicitLoginRequired.value = true
      automaticVerificationBlocked.value = true
      return
    }
    const noticeChanged = uncertainty.notice !== observedNotice
    const ackRegressed =
      uncertainty.ack !== observedAck && !uncertainty.confirmed
    if (noticeChanged || !uncertainty.confirmed) {
      if (sessionVerified.value) discard()
      else if (noticeChanged || ackRegressed) authEpoch.value += 1
      observedNotice = uncertainty.notice
      automaticVerificationBlocked.value = true
    }
    observedAck = uncertainty.ack
    if (
      sessionVerified.value &&
      typeof globalThis.crypto?.randomUUID !== 'function'
    ) {
      failAuthEnvironment('identity-unavailable')
      return
    }
    if (sessionVerified.value && !navigator.locks?.request) {
      failAuthEnvironment('lock-unavailable')
      return
    }
    if (
      (marker?.intentId ?? null) !== observedIntentId ||
      legacy !== observedLegacy ||
      (sessionVerified.value &&
        (marker?.phase !== 'expected' || marker.tenantId !== teamId.value))
    ) {
      const legacyChanged = legacy !== observedLegacy
      discard()
      observedIntentId = marker?.intentId ?? null
      observedLegacy = legacy
      automaticVerificationBlocked.value = true
      explicitLoginRequired.value =
        legacyChanged ||
        !(
          (marker?.phase === 'expected' ||
            marker?.phase === 'verification-required') &&
          marker.tenantId !== null &&
          marker.tenantId === expectedTenantId
        )
    }
  }

  // これらの既存APIは無効化だけを行い、検証済み状態を作らない。
  function beginSessionVerification(): number {
    try {
      const marker = readAuthIntent()
      return beginCorrelatedVerification(marker?.intentId ?? null)
    } catch {
      failAuthEnvironment('storage-unavailable')
      return authEpoch.value
    }
  }
  function signOut(): void {
    discard()
  }
  function expireSession(): void {
    discard(true)
  }

  function onStorage(event: StorageEvent): void {
    if (
      event.key !== AUTH_INTENT_KEY &&
      event.key !== AUTH_UNCERTAIN_KEY &&
      event.key !== AUTH_UNCERTAIN_ACK_KEY &&
      event.key !== AUTH_STORAGE_KEY &&
      event.key !== null
    )
      return
    try {
      if (event.storageArea !== null && event.storageArea !== localStorage)
        return
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
    explicitLoginRequired,
    automaticVerificationBlocked,
    environmentReason,
    canReverify,
    beginCorrelatedVerification,
    adoptCorrelatedSession,
    observeUnconfirmedIntent,
    invalidateUncertainCookie,
    requireExplicitLogin,
    failAuthEnvironment,
    beginSessionVerification,
    signOut,
    expireSession,
    syncFromStorage,
  }
})
