import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import {
  lineupContextFromRead,
  type RecordingContext,
} from '../screens/GameScreenOrdinaryPitchProvider'
import { openDurableQueue } from './sync/durableQueue'
import { queueStateId } from './sync/queueState'
import {
  singleWriterLockName,
  type SingleWriterRevalidationContext,
} from './sync/singleWriter'
import {
  localIntentMatches,
  withLocalRecordingIntentLease,
} from './localRecordingIntentLease'
import {
  localQueueMetadata,
  readLocalPermission,
  revalidateLocalPermission,
  type LocalPermissionRow,
} from './localRecordingPermissionPersistence'
import type { LocalAcceptanceBoundary } from './localRecordingScope'

let localEpoch = 0
function epoch(): number {
  localEpoch += 1
  if (!Number.isSafeInteger(localEpoch))
    throw new Error('端末内記録scopeが尽きました')
  return localEpoch
}
const sessions = new WeakSet<object>()
/** 真正保存原本からだけ作る端末内入力scope。HTTP認証済みにはしない。 */
export class LocalRecordingSession implements LocalAcceptanceBoundary {
  readonly #row: LocalPermissionRow
  readonly #context: RecordingContext
  #epoch = epoch()
  #active = true
  private constructor(row: LocalPermissionRow, context: RecordingContext) {
    this.#row = structuredClone(row)
    this.#context = structuredClone(context)
    sessions.add(this)
  }
  static async restore(gameId: string): Promise<LocalRecordingSession | null> {
    const row = await readLocalPermission(gameId)
    if (!row) return null
    const context = await lineupContextFromRead(row.head, row.tenantId)
    if (!(await revalidateLocalPermission(row))) return null
    return new LocalRecordingSession(row, context)
  }
  get gameId() {
    return this.#row.gameId
  }
  get context() {
    return structuredClone(this.#context)
  }
  get current() {
    if (this.#active && !localIntentMatches(this.#row.correlation))
      this.dispose()
    return this.#active
  }
  /** verified:falseのまま。これはサーバーsessionの成功ではない。 */
  identity() {
    return {
      tenantId: this.current ? this.#row.tenantId : null,
      epoch: this.#epoch,
      verified: false,
    }
  }
  page(cursor: string | null) {
    if (!this.current) throw new Error('端末内記録の資格が変わりました')
    const page = this.#row.pages.find((p) => p.cursor === cursor)
    if (!page) throw new Error('この選択肢ページは保存されていません')
    return structuredClone(page.value)
  }
  dispose() {
    if (this.#active) {
      this.#active = false
      this.#epoch = epoch()
    }
  }
  async withinAcceptance<T>(
    held: SingleWriterRevalidationContext,
    operation: () => Promise<T>,
  ): Promise<T> {
    if (
      !this.current ||
      held.gameIdentifier !== this.gameId ||
      held.lockName !== singleWriterLockName(this.gameId) ||
      held.lock === null ||
      typeof held.lock !== 'object'
    )
      throw new Error('実ゲーム排他が必要です')
    try {
      return await withLocalRecordingIntentLease(
        this.#row.correlation,
        async () => {
          if (!(await revalidateLocalPermission(this.#row)))
            throw new Error('保存資格が変更されました')
          const queue = await openDurableQueue({
            databaseName: 'pitchlog-first-ball-queue-' + this.#row.tenantId,
          })
          try {
            const before = await localQueueMetadata(queue, this.#row)
            const result = await operation()
            const after = await localQueueMetadata(queue, this.#row)
            if (after.next !== before.next && after.next !== before.next + 1)
              throw new Error('キュー位置が不正です')
            if (
              !sameOrdinaryWire(
                before.slots,
                after.slots.filter((slot) => slot.d1 < before.next),
              )
            )
              throw new Error('既存要求が変更されました')
            if (after.next === before.next + 1) {
              const slot = await queue.readSlot(
                { game: this.gameId, d4: this.#row.d4 },
                before.next,
              )
              if (
                !slot ||
                slot.d1 !== before.next ||
                slot.state !== queueStateId('未送信')
              )
                throw new Error('追記原本を確認できません')
            }
            if (!(await revalidateLocalPermission(this.#row)) || !this.current)
              throw new Error('保存資格が変わりました')
            return result
          } finally {
            queue.close()
          }
        },
      )
    } catch (error) {
      this.dispose()
      throw error
    }
  }
}
export function isLocalRecordingSession(
  value: unknown,
): value is LocalRecordingSession {
  return value !== null && typeof value === 'object' && sessions.has(value)
}

/** 認証変更を起こさないpublic到達確認。成功応答の代替には使わない。 */
export async function recordingBackendReachability(): Promise<
  'available' | 'unavailable' | 'unknown'
> {
  if (navigator.onLine === false) return 'unavailable'
  const abort = new AbortController()
  const timeout = setTimeout(() => abort.abort(), 2000)
  try {
    const result = await fetch('/api/health', {
      method: 'GET',
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'manual',
      signal: abort.signal,
    })
    if (
      result.type === 'opaqueredirect' ||
      result.redirected ||
      result.status < 200 ||
      (result.status >= 300 && result.status < 400)
    )
      return 'unknown'
    return result.status === 503 ? 'unavailable' : 'available'
  } catch (error) {
    return error instanceof TypeError ||
      (error instanceof DOMException && error.name === 'AbortError')
      ? 'unavailable'
      : 'unknown'
  } finally {
    clearTimeout(timeout)
  }
}
