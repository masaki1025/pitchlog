import {
  AUTH_INTENT_LOCK,
  AuthEnvironmentError,
  canonicalUuid,
  readAuthIntent,
  readAuthUncertainty,
} from '../api/authIntent'

/** 保存済み記録との相関条件。サーバーsessionの証明ではない。 */
export type LocalIntentCorrelation = Readonly<{
  intentId: string
  tenantId: string
  uncertaintyNotice: string | null
}>

export class LocalRecordingIntentChanged extends Error {
  constructor() {
    super('記録を継続できる認証意図を確認できません')
    this.name = 'LocalRecordingIntentChanged'
  }
}

/** 認証を成功へ更新せず、既expected意図/通知との一致だけを確認する。 */
export function localIntentMatches(expected: LocalIntentCorrelation): boolean {
  try {
    if (
      !canonicalUuid.test(expected.intentId) ||
      !canonicalUuid.test(expected.tenantId)
    )
      return false
    const marker = readAuthIntent(),
      uncertainty = readAuthUncertainty()
    return (
      marker?.phase === 'expected' &&
      marker.intentId === expected.intentId &&
      marker.tenantId === expected.tenantId &&
      uncertainty.confirmed &&
      uncertainty.notice === expected.uncertaintyNotice
    )
  } catch {
    return false
  }
}

/**
 * 先に取得したgame排他内で呼ぶ、読取専用の認証意図lease。
 *
 * callbackはlocal IDBだけをawaitし、通信や別lock待機を入れない。
 * 既withAuthIntentの同期採用資格を立てず、認証状態/意図を書き換えない。
 * 正常なlogout/loginとの競合は同名lockで拒否し、規約外のstorage変更も
 * callback後に拒否する。既に保存した未送信記録は呼出側が保全する。
 */
export async function withLocalRecordingIntentLease<T>(
  expected: LocalIntentCorrelation,
  operation: () => Promise<T>,
): Promise<T> {
  if (!navigator.locks?.request)
    throw new AuthEnvironmentError('lock-unavailable')
  return navigator.locks.request(
    AUTH_INTENT_LOCK,
    { mode: 'exclusive', ifAvailable: true },
    async (lock) => {
      if (!lock) throw new AuthEnvironmentError('lock-busy')
      if (!localIntentMatches(expected)) throw new LocalRecordingIntentChanged()
      const value = await operation()
      if (!localIntentMatches(expected)) throw new LocalRecordingIntentChanged()
      return value
    },
  )
}
