/** 実IDB/queue/単一writerで交代原本文を保つ。HTTPだけを差し替える。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { IDBFactory, IDBKeyRange } from 'fake-indexeddb'
import {
  undoRead,
  installUndoArtifact,
} from './GameScreenUndoProduct.test-support'
import * as reads from '../api/substitutionRead'
import * as transport from '../api/substitutionWire'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { openDurableQueue } from '../lib/sync/durableQueue'
import { queueStateId } from '../lib/sync/queueState'
import { readOrdinaryPitchAck } from '../api/ordinaryPitchAck'
import { applyAckToSlot } from './GameScreenAckApplication'
import { GameScreenSubstitutionProductController } from './GameScreenSubstitutionProductController'
import {
  substitutionContextKey,
  type VerifiedSubstitutionContext,
} from './GameScreenSubstitutionProductProvider'
import { substitutionFromInitialRoster } from '../domain/substitutionKernel'
import type { RawSubstitutionDraft } from './GameScreenSubstitutionTypes'
import type { FirstBallIdentity } from './GameScreenFirstBallController'
import type { SingleWriterInjections } from '../lib/sync/singleWriter'

const base = undoRead(2)
const tenant = base.checkpoint.content.scope.tenantId
const scope = { game: base.id, d4: base.current_d4 }
const incoming = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
let restore: () => void
let identity: FirstBallIdentity
let serverRevision: string
let controllers: GameScreenSubstitutionProductController[] = []
const writer: SingleWriterInjections = {
  resolvePreconditions: () => ({
    topLevelHttps: true,
    sameBrowserProfile: true,
    sameBrowsingMode: true,
    sameStorageBucket: true,
    siteStorageAvailable: true,
    lockdownModeNotApplied: true,
  }),
  revalidateSingleWriter: () => true,
  lockManager: {
    request: async (_name, callback) => callback({ name: _name }),
  },
}
function context(): VerifiedSubstitutionContext {
  const current = base.checkpoint.content.restored.current.stateFields
  const side = current['state.half'] === 'top' ? 'away' : 'home'
  return {
    tenantId: tenant,
    gameId: base.id,
    generation: base.current_d4,
    recoveryGeneration: '1',
    awayLineupId: base.lineups.away.lineup_id,
    homeLineupId: base.lineups.home.lineup_id,
    checkpoint: { ...base.checkpoint.ref, revision: serverRevision },
    nextD1: 3,
    nextD2: 1000,
    currentCount: {
      strikes: current['state.count.strikes'],
      balls: current['state.count.balls'],
    },
    state: substitutionFromInitialRoster(base.roster, side),
    eligibleBySide: {
      away: side === 'home' ? [{ id: incoming, label: '交代投手' }] : [],
      home: side === 'away' ? [{ id: incoming, label: '交代投手' }] : [],
    },
    names: { [incoming]: '交代投手' },
    uniformNumbers: { [incoming]: '18' },
  }
}
function draft(c: VerifiedSubstitutionContext): RawSubstitutionDraft {
  const side = c.state.attackingSide === 'away' ? 'home' : 'away'
  const outgoingId = c.state[side].fielding['1']!
  return {
    identity: {
      contextKey: substitutionContextKey(c),
      uiInstanceId: 'screen-1',
      draftId: 1,
      operation: 'pitcher',
      targetId: outgoingId,
    },
    outgoingId,
    incomingMode: 'existing',
    incomingId: incoming,
    answers: {
      side,
      strikes: c.currentCount.strikes,
      balls: c.currentCount.balls,
      dh: 'retain',
    },
  }
}
function controller() {
  const c = new GameScreenSubstitutionProductController(
    base.id,
    () => identity,
    writer,
  )
  controllers.push(c)
  return c
}
async function queue() {
  return openDurableQueue({
    databaseName: 'pitchlog-first-ball-queue-' + tenant,
  })
}
beforeEach(async () => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('IDBKeyRange', IDBKeyRange)
  vi.stubGlobal('isSecureContext', true)
  restore = installUndoArtifact()
  identity = { tenantId: tenant, epoch: 1, verified: true }
  serverRevision = base.checkpoint.ref.revision
  vi.spyOn(reads, 'readSubstitutionContext').mockImplementation(async () =>
    context(),
  )
  vi.spyOn(GameStartPersistence, 'open').mockResolvedValue({
    readDevice: async () => ({
      tenant_id: tenant,
      device_id: tenant,
      device_credential: 'unit-only-credential',
    }),
    readStart: async () => ({
      status: 'received',
      grant: {
        device_id: tenant,
        d4: base.current_d4,
        recovery_generation: '1',
        away_lineup_id: base.lineups.away.lineup_id,
        home_lineup_id: base.lineups.home.lineup_id,
        recording_right_proof: 'unit-only-proof',
      },
    }),
    close: () => {},
  } as unknown as GameStartPersistence)
  const q = await queue()
  try {
    for (let i = 1; i <= 2; i++) {
      const d5 = `00000000-0000-4000-8000-${String(900 + i).padStart(12, '0')}`
      const slot = await q.append(
        q.prepareAppend({
          scope,
          d5,
          version: 1,
          event: {
            fields: {
              V1: d5,
              V3: scope.d4,
              V4: scope.game,
              V5: '1',
              V7: { fixture: 'already-synced' },
            },
          },
        }),
      )
      const ack = readOrdinaryPitchAck(
        {
          advancedD3: slot.d1,
          eventResults: [{ d1: slot.d1, d4: slot.d4, d5, a5Result: '受理' }],
        },
        { d4: scope.d4, d1: slot.d1, d5 },
      )
      expect(
        (await applyAckToSlot({ scope, d1: slot.d1, ack }, q)).outcome,
      ).toBe('applied')
    }
  } finally {
    q.close()
  }
})
afterEach(() => {
  for (const c of controllers) c.dispose()
  controllers = []
  restore()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('応答不明でも同D5/原本文/attemptを耐久保持し、再送ACKだけを適用する', async () => {
  const post = vi.spyOn(transport, 'postSubstitution').mockResolvedValue({
    sent: false,
    reason: 'no-response',
    error: new Error('network'),
  } as never)
  const first = controller()
  expect(await first.load()).toBe('ready')
  const input = draft(first.context!)
  expect(await first.commit(input)).toBe('pending')
  const q = await queue()
  const saved = await q.readSlot(scope, 3)
  expect(saved?.state).toBe(queueStateId('未送信'))
  q.close()
  const original = structuredClone(post.mock.calls[0])
  first.dispose()
  const second = controller()
  expect(await second.load()).toBe('pending')
  expect(await second.commit(input)).toBe('pending')
  expect(post).toHaveBeenCalledTimes(1)
  post.mockImplementation(async (slot, proof) => {
    serverRevision = String(Number(serverRevision) + 1)
    return {
      sent: true,
      requestBody: transport.substitutionBody(slot, proof),
      response: {
        advancedD3: slot.d1,
        eventResults: [
          { d1: slot.d1, d4: slot.d4, d5: slot.d5, a5Result: '重複' },
        ],
      },
    }
  })
  expect(await second.retry()).toBe('saved')
  expect(post.mock.calls[1]).toEqual(original)
})

it('CP改訂とauth epoch変化では新しいqueue slotを作らない', async () => {
  const post = vi.spyOn(transport, 'postSubstitution')
  const c = controller()
  expect(await c.load()).toBe('ready')
  const input = draft(c.context!)
  serverRevision = String(Number(serverRevision) + 1)
  expect(await c.commit(input)).toBe('blocked')
  identity = { ...identity, epoch: 2 }
  expect(await c.commit(input)).toBe('blocked')
  const q = await queue()
  expect(await q.readSlot(scope, 3)).toBeUndefined()
  q.close()
  expect(post).not.toHaveBeenCalled()
})
