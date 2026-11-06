/** P1取消だけの輸送。queueの正式種別IDと既採用wire名を初回形成時に対応させる。 */
import type {
  UndoEvent,
  UndoPayload,
} from '../../../contracts/state-transition/nonplay_prefix_bridge_v1'
import { apiRequest, type SyncRequestCredentials } from './client'
import { canonicalUuid } from './authIntent'
import { canonicalPlayJson } from './terminalPitchWire'
import type { DurableQueueSlot } from '../lib/sync/durableQueue'
import { isTargetEventReference, type SyncEvent } from '../lib/sync/syncEvent'
import { EVENT_KIND_RULES } from '../lib/sync/eventKinds'
import { SYNC_EVENT_PATH } from '../lib/sync/eventFieldRules'
import { checkSyncEvent } from '../lib/sync/validateSyncEvent'
import { isNonplayDefinition } from './nonplayContract'
import { exactPlayObject } from './terminalPitchWire'
import { sameOrdinaryWire } from './ordinaryPitchWire'
export const NATIVE_UNDO_KIND = (() => {
  const kind = EVENT_KIND_RULES.find((x) => x.name === 'undo')
  if (!kind) throw new Error('正式な取消種別がありません')
  return kind
})()
export type NativeUndoBody = Readonly<{
  recording_right_proof: unknown
  events: readonly UndoEvent[]
}>
/** 生slotは変更せずD1を束縛し、余分なD2/state_diff等を必ず拒否する。 */
export function nativeUndoBody(
  slot: DurableQueueSlot,
  proof: unknown,
): NativeUndoBody {
  const fields = { ...slot.event.fields, V2: slot.d1 }
  if (
    !exactPlayObject(fields, ['V1', 'V2', 'V3', 'V4', 'V5', 'V7', 'V10']) ||
    (Object.hasOwn(slot.event.fields, 'V2') &&
      slot.event.fields.V2 !== slot.d1) ||
    fields.V1 !== slot.d5 ||
    fields.V3 !== slot.d4 ||
    !checkSyncEvent(
      { fields },
      { path: SYNC_EVENT_PATH.P1, eventKinds: [NATIVE_UNDO_KIND] },
    ).ok
  )
    throw new Error('取消slotの形式が不一致です')
  const target = fields.V10
  if (!isTargetEventReference(target))
    throw new Error('対象slotの構造が不一致です')
  const event = {
    d5: fields.V1,
    d1: slot.d1,
    d4: fields.V3,
    game_id: fields.V4,
    event_kind: 'undo',
    payload: fields.V7,
    target_reference: {
      game: target['試合'],
      d4: target['対象の D4'],
      d1: target['対象の D1'],
    },
  }
  if (!isNonplayDefinition<UndoEvent>(event, 'UndoEvent'))
    throw new Error('正式な取消wireを形成できません')
  return { recording_right_proof: proof, events: [event] }
}
/** 保存済みslotから同じbodyを読み出すだけで、再送時にpayload/targetを書き換えない。 */
export async function postNativeUndo(
  gameId: string,
  body: NativeUndoBody,
  credentials: SyncRequestCredentials,
): Promise<unknown> {
  if (
    body.events.length !== 1 ||
    body.events[0]?.game_id !== gameId ||
    !isNonplayDefinition(body.events[0], 'UndoEvent')
  )
    throw new Error('取消の送信範囲が不一致です')
  return apiRequest<unknown>('POST', `/games/${gameId}/sync/events`, {
    tenantBound: true,
    body,
    syncCredentials: credentials,
  })
}
export function nativeUndoDraft(
  gameId: string,
  d4: string,
  d5: string,
  payload: UndoPayload,
  target: UndoEvent['target_reference'],
): SyncEvent {
  if (
    target.game !== gameId ||
    !isNonplayDefinition(payload, 'UndoPayload') ||
    !isNonplayDefinition(target, 'Target')
  )
    throw new Error('取消対象を確認できません')
  return {
    fields: {
      V1: d5,
      V3: d4,
      V4: gameId,
      V5: NATIVE_UNDO_KIND.id,
      V7: structuredClone(payload),
      V10: {
        試合: target.game,
        '対象の D4': target.d4,
        '対象の D1': target.d1,
      },
    },
  }
}
/** 原本eventsの完全一致だけを判定し、再掲用の値を補修しない。 */
export function sameNativeAttempt(
  events: unknown,
  body: NativeUndoBody,
): boolean {
  return sameOrdinaryWire(events, body.events)
}

const DATABASE = 'pitchlog-native-product-envelope'
const STORE = 'attempts'
const INDEX = 'by-slot'
const KEY = ['tenantId', 'gameId', 'd4', 'd1', 'd5']
const SLOT_KEY = ['tenantId', 'gameId', 'd4', 'd1']
export type NativeEnvelopeKey = Readonly<{
  tenantId: string
  gameId: string
  d4: string
  d1: number
  d5: string
}>
export type NativeEnvelopeInput = NativeEnvelopeKey &
  Readonly<{ body: unknown; event: SyncEvent }>
export type StoredNativeEnvelope = NativeEnvelopeKey &
  Readonly<{ attemptId: string; requestJson: string; event: SyncEvent }>
/** 原要求/資格/DOMエラーを外へ持ち出さない。 */
export class NativeEnvelopePersistenceError extends Error {
  constructor() {
    super('記録要求の原封筒を保存・復元できません')
    this.name = 'NativeEnvelopePersistenceError'
  }
}
function invalid(): never {
  throw new NativeEnvelopePersistenceError()
}
function validKey(key: NativeEnvelopeKey): void {
  if (
    !key ||
    ![key.tenantId, key.gameId, key.d5].every(
      (v) => typeof v === 'string' && v.length === 36 && canonicalUuid.test(v),
    ) ||
    typeof key.d4 !== 'string' ||
    Array.from(key.d4).length < 1 ||
    Array.from(key.d4).length > 128 ||
    !Number.isSafeInteger(key.d1) ||
    key.d1 < 1
  )
    invalid()
}
function secure(): void {
  if (!globalThis.isSecureContext || !globalThis.indexedDB) invalid()
}
function readStored(
  value: unknown,
  key: NativeEnvelopeKey,
): StoredNativeEnvelope {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    return invalid()
  const row = value as Record<string, unknown>
  if (
    Object.keys(row).sort().join(',') !==
      'attemptId,d1,d4,d5,event,gameId,requestJson,tenantId' ||
    !KEY.every((k) => row[k] === key[k as keyof NativeEnvelopeKey]) ||
    typeof row.attemptId !== 'string' ||
    row.attemptId.length !== 36 ||
    !canonicalUuid.test(row.attemptId) ||
    typeof row.requestJson !== 'string'
  )
    return invalid()
  const draft = row.event as SyncEvent
  if (
    !exactPlayObject(draft, ['fields']) ||
    !draft.fields ||
    draft.fields.V1 !== key.d5 ||
    draft.fields.V3 !== key.d4 ||
    draft.fields.V4 !== key.gameId ||
    Object.hasOwn(draft.fields, 'V2')
  )
    return invalid()
  canonicalPlayJson(draft)
  const parsed: unknown = JSON.parse(row.requestJson)
  if (
    !exactPlayObject(parsed, ['recording_right_proof', 'events']) ||
    typeof parsed.recording_right_proof !== 'string' ||
    parsed.recording_right_proof.length === 0 ||
    !Array.isArray(parsed.events) ||
    parsed.events.length !== 1 ||
    canonicalPlayJson(parsed) !== row.requestJson
  )
    return invalid()
  const event = parsed.events[0] as Record<string, unknown>
  if (
    !event ||
    event.game_id !== key.gameId ||
    event.d4 !== key.d4 ||
    event.d1 !== key.d1 ||
    event.d5 !== key.d5
  )
    return invalid()
  return Object.freeze({
    tenantId: key.tenantId,
    gameId: key.gameId,
    d4: key.d4,
    d1: key.d1,
    d5: key.d5,
    attemptId: row.attemptId,
    requestJson: row.requestJson,
    event: structuredClone(draft),
  })
}
/** queue受理前に全wire封筒とattemptをstrict commitする。孤児準備行は受理/送信済みとしない。 */
export class NativeEnvelopePersistence {
  #database: IDBDatabase
  #closed = false
  private constructor(database: IDBDatabase) {
    this.#database = database
    database.onversionchange = () => this.close()
  }
  static async open(): Promise<NativeEnvelopePersistence> {
    try {
      secure()
      return await new Promise((resolve, reject) => {
        const request = indexedDB.open(DATABASE, 1)
        let failed = false
        const fail = () => {
          failed = true
          reject(new NativeEnvelopePersistenceError())
        }
        request.onerror = fail
        request.onblocked = fail
        request.onupgradeneeded = () => {
          try {
            const store = request.result.createObjectStore(STORE, {
              keyPath: KEY,
            })
            store.createIndex(INDEX, SLOT_KEY, { unique: true })
          } catch {
            request.transaction?.abort()
            fail()
          }
        }
        request.onsuccess = () => {
          const db = request.result
          if (failed) {
            db.close()
            return
          }
          try {
            if ([...db.objectStoreNames].join(',') !== STORE) return invalid()
            const store = db.transaction(STORE, 'readonly').objectStore(STORE)
            const index = store.index(INDEX)
            if (
              JSON.stringify(store.keyPath) !== JSON.stringify(KEY) ||
              [...store.indexNames].join(',') !== INDEX ||
              JSON.stringify(index.keyPath) !== JSON.stringify(SLOT_KEY) ||
              !index.unique
            )
              return invalid()
            resolve(new NativeEnvelopePersistence(db))
          } catch {
            db.close()
            fail()
          }
        }
      })
    } catch {
      return invalid()
    }
  }
  close(): void {
    this.#closed = true
    this.#database.close()
  }
  #transaction(
    key: NativeEnvelopeKey,
    expected?: StoredNativeEnvelope,
  ): Promise<StoredNativeEnvelope | null> {
    return new Promise((resolve, reject) => {
      let tx: IDBTransaction
      try {
        secure()
        validKey(key)
        if (this.#closed) return invalid()
        tx = this.#database.transaction(
          STORE,
          expected ? 'readwrite' : 'readonly',
          expected ? { durability: 'strict' } : undefined,
        )
        if (expected && tx.durability !== 'strict') {
          tx.abort()
          return invalid()
        }
      } catch {
        reject(new NativeEnvelopePersistenceError())
        return
      }
      let result: StoredNativeEnvelope | null = null,
        ready = false
      const fail = () => {
        try {
          tx.abort()
        } catch {
          reject(new NativeEnvelopePersistenceError())
        }
      }
      tx.onerror = (event) => {
        event.preventDefault()
        fail()
      }
      tx.onabort = () => reject(new NativeEnvelopePersistenceError())
      tx.oncomplete = () =>
        ready ? resolve(result) : reject(new NativeEnvelopePersistenceError())
      try {
        const store = tx.objectStore(STORE)
        const request = store.get([
          key.tenantId,
          key.gameId,
          key.d4,
          key.d1,
          key.d5,
        ])
        request.onsuccess = () => {
          try {
            if (request.result !== undefined) {
              result = readStored(request.result, key)
              if (
                expected &&
                (result.requestJson !== expected.requestJson ||
                  !sameOrdinaryWire(result.event, expected.event))
              )
                return invalid()
            } else if (expected) {
              store.add(expected)
              result = expected
            }
            ready = true
          } catch {
            fail()
          }
        }
      } catch {
        fail()
      }
    })
  }
  /** 未受理の準備行もD1単位で見つけ、原本のまま回復する。削除やTTLは設けない。 */
  async readPreparedSlot(
    key: Omit<NativeEnvelopeKey, 'd5'>,
  ): Promise<StoredNativeEnvelope | null> {
    try {
      secure()
      if (this.#closed) return invalid()
      return await new Promise((resolve, reject) => {
        const tx = this.#database.transaction(STORE, 'readonly')
        let result: StoredNativeEnvelope | null = null
        let ready = false
        tx.onabort = tx.onerror = () =>
          reject(new NativeEnvelopePersistenceError())
        tx.oncomplete = () =>
          ready ? resolve(result) : reject(new NativeEnvelopePersistenceError())
        const req = tx
          .objectStore(STORE)
          .index(INDEX)
          .get([key.tenantId, key.gameId, key.d4, key.d1])
        req.onsuccess = () => {
          try {
            if (req.result !== undefined) {
              result = readStored(req.result, { ...key, d5: req.result.d5 })
            }
            ready = true
          } catch {
            tx.abort()
          }
        }
      })
    } catch {
      return invalid()
    }
  }
  async read(key: NativeEnvelopeKey): Promise<StoredNativeEnvelope | null> {
    return this.#transaction(key)
  }
  async prepare(
    input: NativeEnvelopeInput,
    attemptId?: string,
  ): Promise<StoredNativeEnvelope> {
    try {
      validKey(input)
      const key: NativeEnvelopeKey = {
        tenantId: input.tenantId,
        gameId: input.gameId,
        d4: input.d4,
        d1: input.d1,
        d5: input.d5,
      }
      const expected = readStored(
        {
          ...key,
          attemptId: attemptId ?? crypto.randomUUID(),
          requestJson: canonicalPlayJson(input.body),
          event: structuredClone(input.event),
        },
        key,
      )
      const result = await this.#transaction(key, expected)
      if (!result) return invalid()
      return result
    } catch {
      return invalid()
    }
  }
}
