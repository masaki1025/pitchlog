/** 真正readの端末内再利用。HTTP認証や現在の記録権を成立させるstoreではない。 */
import { getActivePinia } from 'pinia'
import identity from '../../public/domain/pitchlog-domain.json'
import { useAuthStore } from '../stores/authStore'
import {
  readAuthIntent,
  readAuthUncertainty,
  canonicalUuid,
} from '../api/authIntent'
import {
  isLineupPrefixGame,
  type LineupPrefixGame,
} from '../api/lineupPrefixGame'
import { parsePitchTypePage, type PitchTypePage } from '../api/pitchTypeOptions'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import { playHash } from '../api/terminalPitchWire'
import { lineupContextFromRead } from '../screens/GameScreenOrdinaryPitchProvider'
import { GameStartPersistence } from './gameStartPersistence'
import { openDurableQueue, type DurableQueue } from './sync/durableQueue'
import { queueStateId } from './sync/queueState'
import { singleWriterLockName } from './sync/singleWriter'
import {
  withLocalRecordingIntentLease,
  localIntentMatches,
  type LocalIntentCorrelation,
} from './localRecordingIntentLease'

const DB = 'pitchlog-local-recording-permission-v1'
const STORE = 'permissions'
const KEY_PATH = ['tenantId', 'gameId', 'd4']
export type LocalPermissionRow = Readonly<{
  schemaVersion: 1
  tenantId: string
  gameId: string
  d4: string
  recoveryGeneration: string
  grantDigest: string
  deviceDigest: string
  artifactSha256: string
  correlation: LocalIntentCorrelation
  head: LineupPrefixGame
  pages: readonly Readonly<{ cursor: string | null; value: PitchTypePage }>[]
}>
function unavailable(): never {
  throw new Error('端末内記録の保存資格を確認できません')
}
function exact(
  value: unknown,
  fields: string[],
): value is Record<string, unknown> {
  return (
    value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    Object.keys(value).sort().join(',') === [...fields].sort().join(',')
  )
}
export function isLocalPermissionRow(
  value: unknown,
): value is LocalPermissionRow {
  if (
    !exact(value, [
      'schemaVersion',
      'tenantId',
      'gameId',
      'd4',
      'recoveryGeneration',
      'grantDigest',
      'deviceDigest',
      'artifactSha256',
      'correlation',
      'head',
      'pages',
    ]) ||
    value.schemaVersion !== 1 ||
    typeof value.tenantId !== 'string' ||
    !canonicalUuid.test(value.tenantId) ||
    typeof value.gameId !== 'string' ||
    !canonicalUuid.test(value.gameId) ||
    typeof value.grantDigest !== 'string' ||
    !/^[0-9a-f]{64}$/.test(value.grantDigest) ||
    typeof value.deviceDigest !== 'string' ||
    !/^[0-9a-f]{64}$/.test(value.deviceDigest) ||
    value.artifactSha256 !== identity.sha256 ||
    !isLineupPrefixGame(value.head) ||
    !exact(value.correlation, ['intentId', 'tenantId', 'uncertaintyNotice']) ||
    typeof value.correlation.intentId !== 'string' ||
    !canonicalUuid.test(value.correlation.intentId) ||
    value.correlation.tenantId !== value.tenantId ||
    (value.correlation.uncertaintyNotice !== null &&
      (typeof value.correlation.uncertaintyNotice !== 'string' ||
        !canonicalUuid.test(value.correlation.uncertaintyNotice))) ||
    !Array.isArray(value.pages)
  )
    return false
  if (
    value.head.id !== value.gameId ||
    value.head.current_d4 !== value.d4 ||
    value.head.recovery_generation !== value.recoveryGeneration ||
    value.head.prefix_ref.tenantId !== value.tenantId
  )
    return false
  const seen = new Set<string | null>()
  try {
    for (const page of value.pages) {
      if (
        !exact(page, ['cursor', 'value']) ||
        (page.cursor !== null && typeof page.cursor !== 'string') ||
        seen.has(page.cursor)
      )
        return false
      parsePitchTypePage(page.value, page.cursor)
      seen.add(page.cursor)
    }
  } catch {
    return false
  }
  return true
}
async function open(): Promise<IDBDatabase> {
  if (!globalThis.isSecureContext || typeof indexedDB?.open !== 'function')
    unavailable()
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB, 1)
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE, { keyPath: KEY_PATH })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = request.onblocked = () =>
      reject(new Error('端末内記録の保存域を開けません'))
  })
  try {
    if (
      [...db.objectStoreNames].join(',') !== STORE ||
      !sameOrdinaryWire(
        db.transaction(STORE).objectStore(STORE).keyPath,
        KEY_PATH,
      )
    )
      unavailable()
    return db
  } catch (error) {
    db.close()
    throw error
  }
}
async function rowAt(
  tenant: string,
  game: string,
  d4: string,
): Promise<LocalPermissionRow | null> {
  const db = await open()
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      let value: unknown
      tx.objectStore(STORE).get([tenant, game, d4]).onsuccess = (event) => {
        value = (event.target as IDBRequest).result
      }
      tx.oncomplete = () =>
        value === undefined
          ? resolve(null)
          : isLocalPermissionRow(value)
            ? resolve(value)
            : reject(new Error('端末内記録の保存原本が不正です'))
      tx.onabort = tx.onerror = () =>
        reject(new Error('端末内記録の保存原本を読めません'))
    })
  } finally {
    db.close()
  }
}
async function replaceRow(
  row: LocalPermissionRow,
  expected: LocalPermissionRow | null,
): Promise<void> {
  if (!isLocalPermissionRow(row)) unavailable()
  const db = await open()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite', { durability: 'strict' })
      if (tx.durability !== 'strict') {
        tx.abort()
        reject(new Error('strict保存が必要です'))
        return
      }
      const store = tx.objectStore(STORE)
      const request = store.get([row.tenantId, row.gameId, row.d4])
      request.onsuccess = () => {
        if (!sameOrdinaryWire(request.result ?? null, expected)) {
          tx.abort()
          return
        }
        store.put(structuredClone(row))
      }
      tx.oncomplete = () => resolve()
      tx.onabort = () => reject(new Error('保存資格が競合しました'))
      tx.onerror = () => {
        /* abortを終結にする。 */
      }
    })
  } finally {
    db.close()
  }
}
export async function currentLocalStartBinding(tenant: string, game: string) {
  const store = await GameStartPersistence.open()
  try {
    const start = await store.readStart(tenant, game),
      device = await store.readDevice(tenant)
    if (
      start?.status !== 'received' ||
      !start.grant ||
      !device ||
      device.device_id !== start.grant.device_id ||
      start.grant.tenant_id !== tenant ||
      start.grant.game_id !== game
    )
      unavailable()
    return {
      grant: start.grant,
      grantDigest: await playHash(start.grant),
      deviceDigest: await playHash(device),
    }
  } finally {
    store.close()
  }
}
export function localHeadD3(row: LocalPermissionRow): number {
  const next = Number(row.head.next_position.d1)
  if (!Number.isSafeInteger(next) || next < 1) unavailable()
  return next - 1
}
export async function localQueueMetadata(
  queue: DurableQueue,
  row: LocalPermissionRow,
) {
  const scope = { game: row.gameId, d4: row.d4 }
  const next = await queue.readNextD1(scope)
  if (!Number.isSafeInteger(next) || next < localHeadD3(row) + 1) unavailable()
  const slots: Array<{ d1: number; digest: string }> = []
  let pending = false,
    cursor: number | null = null
  do {
    const page = await queue.readSlotsPage(scope, cursor, 100)
    for (const slot of page.items) {
      if (slot.state !== queueStateId('同期済み')) pending = true
      slots.push({
        d1: slot.d1,
        digest: await playHash({
          d1: slot.d1,
          d5: slot.d5,
          state: slot.state,
          version: slot.version,
          event: slot.event,
        }),
      })
    }
    cursor = page.nextCursorD1
  } while (cursor !== null)
  return { next, pending, slots }
}
function verifiedCorrelation(epoch: number): LocalIntentCorrelation {
  if (!getActivePinia()) unavailable()
  const auth = useAuthStore(),
    marker = readAuthIntent(),
    uncertainty = readAuthUncertainty()
  if (
    !auth.hasHydrated ||
    !auth.isAuthenticated ||
    auth.authEpoch !== epoch ||
    !auth.teamId ||
    marker?.phase !== 'expected' ||
    marker.tenantId !== auth.teamId ||
    !uncertainty.confirmed
  )
    unavailable()
  return {
    intentId: marker.intentId,
    tenantId: auth.teamId,
    uncertaintyNotice: uncertainty.notice,
  }
}
async function underGame<T>(
  game: string,
  operation: () => Promise<T>,
): Promise<T> {
  if (!navigator.locks?.request) unavailable()
  return navigator.locks.request(
    singleWriterLockName(game),
    { mode: 'exclusive', ifAvailable: true },
    async (lock) => {
      if (!lock) unavailable()
      return operation()
    },
  )
}
/** 実C2 readの呼出元が渡したsourceを、同認証epochのまま耐久確定する。 */
export async function captureLocalRecordingSource(
  head: LineupPrefixGame,
  epoch: number,
): Promise<'captured' | 'pending'> {
  const correlation = verifiedCorrelation(epoch)
  if (
    !isLineupPrefixGame(head) ||
    head.prefix_ref.tenantId !== correlation.tenantId
  )
    unavailable()
  await lineupContextFromRead(head, correlation.tenantId)
  return underGame(head.id, () =>
    withLocalRecordingIntentLease(correlation, async () => {
      verifiedCorrelation(epoch)
      const binding = await currentLocalStartBinding(
        correlation.tenantId,
        head.id,
      )
      if (
        head.prefix_ref.origin.kind !== 'started-game' ||
        head.prefix_ref.origin.eventId !== binding.grant.start_request_id ||
        binding.grant.d4 !== head.current_d4 ||
        binding.grant.recovery_generation !== head.recovery_generation ||
        binding.grant.away_lineup_id !== head.lineups.away.lineup_id ||
        binding.grant.home_lineup_id !== head.lineups.home.lineup_id
      )
        unavailable()
      const previous = await rowAt(
        correlation.tenantId,
        head.id,
        head.current_d4,
      )
      const queue = await openDurableQueue({
        databaseName: 'pitchlog-first-ball-queue-' + correlation.tenantId,
      })
      try {
        if (previous && (await localQueueMetadata(queue, previous)).pending)
          return 'pending'
        if (
          previous &&
          (BigInt(head.next_position.d1) <
            BigInt(previous.head.next_position.d1) ||
            (head.next_position.d1 === previous.head.next_position.d1 &&
              !sameOrdinaryWire(head.prefix_ref, previous.head.prefix_ref)))
        )
          unavailable()
        const row: LocalPermissionRow = {
          schemaVersion: 1,
          tenantId: correlation.tenantId,
          gameId: head.id,
          d4: head.current_d4,
          recoveryGeneration: head.recovery_generation,
          grantDigest: binding.grantDigest,
          deviceDigest: binding.deviceDigest,
          artifactSha256: identity.sha256,
          correlation,
          head: structuredClone(head),
          pages:
            previous?.correlation.intentId === correlation.intentId
              ? previous.pages
              : [],
        }
        verifiedCorrelation(epoch)
        await replaceRow(row, previous)
        verifiedCorrelation(epoch)
        return 'captured'
      } finally {
        queue.close()
      }
    }),
  )
}
/** 初回readと同scopeで受け取った閉ページを保存し、語彙を補完しない。 */
export async function captureLocalPitchPage(
  game: string,
  d4: string,
  cursor: string | null,
  value: PitchTypePage,
  epoch: number,
): Promise<void> {
  const correlation = verifiedCorrelation(epoch)
  const page = parsePitchTypePage(value, cursor)
  await underGame(game, () =>
    withLocalRecordingIntentLease(correlation, async () => {
      const row = await rowAt(correlation.tenantId, game, d4)
      if (!row || !sameOrdinaryWire(row.correlation, correlation)) unavailable()
      const binding = await currentLocalStartBinding(correlation.tenantId, game)
      if (
        binding.grantDigest !== row.grantDigest ||
        binding.deviceDigest !== row.deviceDigest
      )
        unavailable()
      verifiedCorrelation(epoch)
      await replaceRow(
        {
          ...row,
          pages: [
            ...row.pages.filter((p) => p.cursor !== cursor),
            { cursor, value: page },
          ],
        },
        row,
      )
      verifiedCorrelation(epoch)
    }),
  )
}
/** 保存grant/intentに一致する端末内sourceだけを返す。HTTP認証は更新しない。 */
export async function readLocalPermission(
  game: string,
): Promise<LocalPermissionRow | null> {
  const marker = readAuthIntent(),
    uncertainty = readAuthUncertainty()
  if (
    !canonicalUuid.test(game) ||
    marker?.phase !== 'expected' ||
    !marker.tenantId ||
    !uncertainty.confirmed
  )
    return null
  const binding = await currentLocalStartBinding(marker.tenantId, game)
  const row = await rowAt(marker.tenantId, game, binding.grant.d4)
  if (
    !row ||
    !localIntentMatches(row.correlation) ||
    row.grantDigest !== binding.grantDigest ||
    row.deviceDigest !== binding.deviceDigest ||
    !row.pages.some((p) => p.cursor === null)
  )
    return null
  await lineupContextFromRead(row.head, row.tenantId)
  if (!localIntentMatches(row.correlation)) return null
  return row
}
export async function revalidateLocalPermission(
  row: LocalPermissionRow,
): Promise<boolean> {
  if (!localIntentMatches(row.correlation)) return false
  const binding = await currentLocalStartBinding(row.tenantId, row.gameId)
  const actual = await rowAt(row.tenantId, row.gameId, row.d4)
  return (
    binding.grantDigest === row.grantDigest &&
    binding.deviceDigest === row.deviceDigest &&
    sameOrdinaryWire(actual, row) &&
    localIntentMatches(row.correlation)
  )
}
