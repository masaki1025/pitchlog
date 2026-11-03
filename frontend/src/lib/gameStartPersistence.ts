import {
  parseDeviceEnrollmentResponse,
  parseGameStartOwner,
  parseGameStartRequest,
  parseInitialGameStartResponse,
  type GameStartOwner,
  type GameStartRequest,
  type InitialDeviceEnrollmentResponse,
  type InitialGameStartResponse,
} from '../api/gameStart'

const DATABASE = 'pitchlog-game-start'
const DEVICES = 'devices'
const STARTS = 'starts'

export type StoredGameStart = Readonly<{
  owner: GameStartOwner
  request: GameStartRequest
  status: 'pending' | 'unknown' | 'received'
  grant: InitialGameStartResponse | null
}>

type Watch = <T>(request: IDBRequest<T>, accept: (value: T) => void) => void

/** 保存資格・元要求・DOM例外を保持しない。失敗を保存完了へ補完しない。 */
export class GameStartPersistenceError extends Error {
  constructor() {
    super('開始データを保存・復元できません')
    this.name = 'GameStartPersistenceError'
  }
}

function invalid(): never {
  throw new GameStartPersistenceError()
}

function secure(): void {
  if (
    globalThis.isSecureContext !== true ||
    typeof globalThis.indexedDB?.open !== 'function'
  )
    invalid()
}

function key(value: string): string {
  if (
    typeof value !== 'string' ||
    value.length !== 36 ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      value,
    )
  )
    invalid()
  return value
}

/** 既に外形検証されたJSONの比較用。配列順序と全値を保持する。 */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']'
  if (value !== null && typeof value === 'object') {
    const row = value as Record<string, unknown>
    return (
      '{' +
      Object.keys(row)
        .sort()
        .map((field) => JSON.stringify(field) + ':' + canonical(row[field]))
        .join(',') +
      '}'
    )
  }
  const result = JSON.stringify(value)
  if (result === undefined) return invalid()
  return result
}

function row(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null) return invalid()
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) return invalid()
  const descriptors = Object.getOwnPropertyDescriptors(value)
  if (Object.getOwnPropertySymbols(descriptors).length !== 0) return invalid()
  const fields = ['owner', 'request', 'status', 'grant']
  if (Object.keys(descriptors).length !== fields.length) return invalid()
  const snapshot: Record<string, unknown> = Object.create(null) as Record<
    string,
    unknown
  >
  for (const field of fields) {
    const descriptor = descriptors[field]
    if (
      descriptor === undefined ||
      !Object.hasOwn(descriptor, 'value') ||
      !descriptor.enumerable
    )
      return invalid()
    snapshot[field] = descriptor.value
  }
  return snapshot
}

function stored(value: unknown, tenant: string, game: string): StoredGameStart {
  const data = row(value)
  const owner = parseGameStartOwner(data.owner)
  if (owner.tenant_id !== tenant || owner.game_id !== game) return invalid()
  const request = parseGameStartRequest(data.request)
  if (
    owner.start_request_id !== request.start_request_id ||
    owner.device_id !== request.device_id
  )
    return invalid()
  if (
    data.status !== 'pending' &&
    data.status !== 'unknown' &&
    data.status !== 'received'
  )
    return invalid()
  if (data.status !== 'received' && data.grant !== null) return invalid()
  const grant =
    data.status === 'received'
      ? parseInitialGameStartResponse(data.grant, owner)
      : null
  return Object.freeze({ owner, request, status: data.status, grant })
}

/** Q1と別の専用IDB。返却はローカル保存証拠で、サーバーcommit/記録権の証明ではない。 */
export class GameStartPersistence {
  #database: IDBDatabase
  #closed = false

  private constructor(database: IDBDatabase) {
    this.#database = database
    database.onversionchange = () => this.close()
  }

  static async open(): Promise<GameStartPersistence> {
    try {
      secure()
      return await new Promise<GameStartPersistence>((resolve, reject) => {
        const opening = indexedDB.open(DATABASE, 1)
        let settled = false
        const fail = () => {
          settled = true
          reject(new GameStartPersistenceError())
        }
        opening.onblocked = fail
        opening.onerror = (event) => {
          event.preventDefault()
          fail()
        }
        opening.onupgradeneeded = () => {
          try {
            const database = opening.result
            database.createObjectStore(DEVICES, { keyPath: 'tenant_id' })
            database.createObjectStore(STARTS, {
              keyPath: ['owner.tenant_id', 'owner.game_id'],
            })
          } catch {
            try {
              opening.transaction?.abort()
            } catch {
              /* 終結済みでも成功へしない。 */
            }
            fail()
          }
        }
        opening.onsuccess = () => {
          const database = opening.result
          if (settled) {
            database.close()
            return
          }
          try {
            const names = [...database.objectStoreNames].sort()
            if (canonical(names) !== canonical([DEVICES, STARTS].sort()))
              invalid()
            const transaction = database.transaction(
              [DEVICES, STARTS],
              'readonly',
            )
            if (
              transaction.objectStore(DEVICES).keyPath !== 'tenant_id' ||
              canonical(transaction.objectStore(STARTS).keyPath) !==
                canonical(['owner.tenant_id', 'owner.game_id'])
            )
              invalid()
            settled = true
            resolve(new GameStartPersistence(database))
          } catch {
            database.close()
            fail()
          }
        }
      })
    } catch {
      throw new GameStartPersistenceError()
    }
  }

  close(): void {
    this.#closed = true
    this.#database.close()
  }

  #run<T>(
    names: readonly string[],
    mode: IDBTransactionMode,
    begin: (
      transaction: IDBTransaction,
      done: (value: T) => void,
      watch: Watch,
    ) => void,
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      let transaction: IDBTransaction
      try {
        secure()
        if (this.#closed) invalid()
        transaction = this.#database.transaction(
          [...names],
          mode,
          mode === 'readwrite' ? { durability: 'strict' } : undefined,
        )
        if (mode === 'readwrite' && transaction.durability !== 'strict') {
          transaction.abort()
          invalid()
        }
      } catch {
        reject(new GameStartPersistenceError())
        return
      }
      let failed = false
      let ready = false
      let result: T
      const fail = () => {
        failed = true
        try {
          transaction.abort()
        } catch {
          reject(new GameStartPersistenceError())
        }
      }
      const watch: Watch = (request, accept) => {
        request.onsuccess = () => {
          try {
            accept(request.result)
          } catch {
            fail()
          }
        }
      }
      transaction.onerror = (event) => {
        event.preventDefault()
        fail()
      }
      transaction.onabort = () => reject(new GameStartPersistenceError())
      transaction.oncomplete = () => {
        if (failed || !ready) reject(new GameStartPersistenceError())
        else resolve(result)
      }
      try {
        begin(
          transaction,
          (value) => {
            result = value
            ready = true
          },
          watch,
        )
      } catch {
        fail()
      }
    })
  }

  async rememberDevice(value: unknown, expectedTenant: string): Promise<void> {
    let device: InitialDeviceEnrollmentResponse
    try {
      device = parseDeviceEnrollmentResponse(value, expectedTenant)
    } catch {
      return invalid()
    }
    return this.#run([DEVICES], 'readwrite', (transaction, done, watch) => {
      const devices = transaction.objectStore(DEVICES)
      watch(devices.get(device.tenant_id), (previous: unknown) => {
        if (previous === undefined) devices.put(device)
        else if (
          canonical(
            parseDeviceEnrollmentResponse(previous, device.tenant_id),
          ) !== canonical(device)
        )
          invalid()
        done(undefined)
      })
    })
  }

  async readDevice(
    tenantId: string,
  ): Promise<InitialDeviceEnrollmentResponse | null> {
    const tenant = key(tenantId)
    return this.#run([DEVICES], 'readonly', (transaction, done, watch) => {
      watch(transaction.objectStore(DEVICES).get(tenant), (value: unknown) =>
        done(
          value === undefined
            ? null
            : parseDeviceEnrollmentResponse(value, tenant),
        ),
      )
    })
  }

  async prepareStart(
    tenantId: string,
    gameId: string,
    value: unknown,
  ): Promise<StoredGameStart> {
    let request: GameStartRequest
    let owner: GameStartOwner
    try {
      request = parseGameStartRequest(value)
      owner = parseGameStartOwner({
        tenant_id: tenantId,
        game_id: gameId,
        start_request_id: request.start_request_id,
        device_id: request.device_id,
      })
    } catch {
      return invalid()
    }
    return this.#run(
      [DEVICES, STARTS],
      'readwrite',
      (transaction, done, watch) => {
        this.#device(transaction, owner, request, watch, () => {
          const starts = transaction.objectStore(STARTS)
          watch(
            starts.get([owner.tenant_id, owner.game_id]),
            (previous: unknown) => {
              if (previous !== undefined) {
                const saved = stored(previous, owner.tenant_id, owner.game_id)
                if (
                  canonical(saved.owner) !== canonical(owner) ||
                  canonical(saved.request) !== canonical(request)
                )
                  invalid()
                done(saved)
              } else {
                const saved: StoredGameStart = Object.freeze({
                  owner,
                  request,
                  status: 'pending',
                  grant: null,
                })
                starts.put(saved)
                done(saved)
              }
            },
          )
        })
      },
    )
  }

  #device(
    transaction: IDBTransaction,
    owner: GameStartOwner,
    request: GameStartRequest,
    watch: Watch,
    accept: () => void,
  ): void {
    watch(
      transaction.objectStore(DEVICES).get(owner.tenant_id),
      (value: unknown) => {
        const device = parseDeviceEnrollmentResponse(value, owner.tenant_id)
        if (
          device.device_id !== owner.device_id ||
          device.device_credential !== request.device_credential
        )
          invalid()
        accept()
      },
    )
  }

  async readStart(
    tenantId: string,
    gameId: string,
  ): Promise<StoredGameStart | null> {
    const tenant = key(tenantId)
    const game = key(gameId)
    return this.#run(
      [DEVICES, STARTS],
      'readonly',
      (transaction, done, watch) => {
        watch(
          transaction.objectStore(STARTS).get([tenant, game]),
          (value: unknown) => {
            if (value === undefined) {
              done(null)
              return
            }
            const saved = stored(value, tenant, game)
            this.#device(transaction, saved.owner, saved.request, watch, () =>
              done(saved),
            )
          },
        )
      },
    )
  }

  async markUnknown(value: GameStartOwner): Promise<StoredGameStart> {
    let owner: GameStartOwner
    try {
      owner = parseGameStartOwner(value)
    } catch {
      return invalid()
    }
    return this.#run(
      [DEVICES, STARTS],
      'readwrite',
      (transaction, done, watch) => {
        const starts = transaction.objectStore(STARTS)
        watch(
          starts.get([owner.tenant_id, owner.game_id]),
          (previous: unknown) => {
            const saved = stored(previous, owner.tenant_id, owner.game_id)
            if (canonical(saved.owner) !== canonical(owner)) invalid()
            this.#device(transaction, saved.owner, saved.request, watch, () => {
              if (saved.status === 'received') {
                done(saved)
                return
              }
              const pending: StoredGameStart = Object.freeze({
                ...saved,
                status: 'unknown',
              })
              starts.put(pending)
              done(pending)
            })
          },
        )
      },
    )
  }

  async rememberGrant(
    ownerValue: GameStartOwner,
    response: unknown,
  ): Promise<StoredGameStart> {
    let owner: GameStartOwner
    let grant: InitialGameStartResponse
    try {
      owner = parseGameStartOwner(ownerValue)
      grant = parseInitialGameStartResponse(response, owner)
    } catch {
      return invalid()
    }
    return this.#run(
      [DEVICES, STARTS],
      'readwrite',
      (transaction, done, watch) => {
        const starts = transaction.objectStore(STARTS)
        watch(
          starts.get([owner.tenant_id, owner.game_id]),
          (previous: unknown) => {
            const saved = stored(previous, owner.tenant_id, owner.game_id)
            if (canonical(saved.owner) !== canonical(owner)) invalid()
            this.#device(transaction, saved.owner, saved.request, watch, () => {
              if (saved.status === 'received') {
                if (canonical(saved.grant) !== canonical(grant)) invalid()
                done(saved)
                return
              }
              const received: StoredGameStart = Object.freeze({
                ...saved,
                status: 'received',
                grant,
              })
              starts.put(received)
              done(received)
            })
          },
        )
      },
    )
  }
}
