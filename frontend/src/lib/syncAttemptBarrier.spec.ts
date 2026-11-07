import { IDBFactory } from 'fake-indexeddb'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { SyncAttemptBarrier } from './syncAttemptBarrier'

const tenant = '00000000-0000-4000-8000-000000000011'
const game = '00000000-0000-4000-8000-000000000012'
const device = '00000000-0000-4000-8000-000000000013'
const attempt = '00000000-0000-4000-8000-000000000014'
const next = '00000000-0000-4000-8000-000000000015'
const d5 = '00000000-0000-4000-8000-000000000016'
const opened: SyncAttemptBarrier[] = []
function body() {
  return {
    recovery_generation: '1',
    recording_right_proof: 'original-proof',
    change: {
      d5,
      game_id: game,
      event_kind: 'play_change',
      target_reference: { game, d4: 'original-D4', d1: 1 },
      expected_version: 1,
      payload: { observed: 'original' },
    },
  }
}
async function open() {
  const value = await SyncAttemptBarrier.open()
  opened.push(value)
  return value
}
beforeEach(() => {
  vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('indexedDB', new IDBFactory())
})
afterEach(() => {
  for (const value of opened.splice(0)) value.close()
  vi.unstubAllGlobals()
})
it('P3原本文を閉鎖後も全値保持し、同D5でattemptだけをCAS更新する', async () => {
  const original = body(),
    one = await open()
  const first = await one.prepare(tenant, game, original, device, attempt)
  expect(first.created).toBe(true)
  expect(JSON.parse(first.barrier.bodyJson)).toEqual(original)
  one.close()
  const two = await open()
  const restored = await two.prepare(tenant, game, original, device, attempt)
  expect(restored).toEqual({ barrier: first.barrier, created: false })
  await two.advance(restored.barrier, next)
  const changed = await two.prepare(tenant, game, original, device, attempt)
  expect(changed.barrier).toEqual({ ...first.barrier, currentAttemptId: next })
  await expect(
    two.advance(first.barrier, crypto.randomUUID()),
  ).rejects.toThrow()
})
it.each(['proof', 'generation', 'target', 'version', 'payload'])(
  '同D5の元%sを現在値で補完・置換しない',
  async (field) => {
    const barrier = await open(),
      original = body()
    await barrier.prepare(tenant, game, original, device, attempt)
    const changed = structuredClone(original)
    if (field === 'proof') changed.recording_right_proof = 'new-proof'
    else if (field === 'generation') changed.recovery_generation = '2'
    else if (field === 'target') changed.change.target_reference.d1 = 2
    else if (field === 'version') changed.change.expected_version = 2
    else changed.change.payload.observed = 'changed'
    await expect(
      barrier.prepare(tenant, game, changed, device, attempt),
    ).rejects.toThrow()
    expect(
      (await barrier.prepare(tenant, game, original, device, attempt)).barrier
        .bodyJson,
    ).toBe(JSON.stringify(original))
  },
)
it.each(['d1', 'd4', 'events', 'extra', 'wrong-kind'])(
  'P3を一般D1任意型へ広げず混在/未知%sを拒否する',
  async (field) => {
    const barrier = await open(),
      original = body()
    const changed = structuredClone(original) as unknown as Record<
      string,
      unknown
    >
    if (field === 'events' || field === 'extra') changed[field] = []
    else if (field === 'wrong-kind') original.change.event_kind = 'play_input'
    else (changed.change as Record<string, unknown>)[field] = 1
    await expect(
      barrier.prepare(
        tenant,
        game,
        field === 'wrong-kind' ? original : changed,
        device,
        attempt,
      ),
    ).rejects.toThrow()
  },
)
it('getterで元本文を作り変えず、副作用を実行前に拒否する', async () => {
  const barrier = await open(),
    original = body(),
    getter = vi.fn(() => 'new-proof')
  Object.defineProperty(original, 'recording_right_proof', {
    enumerable: true,
    get: getter,
  })
  await expect(
    barrier.prepare(tenant, game, original, device, attempt),
  ).rejects.toThrow()
  expect(getter).not.toHaveBeenCalled()
})
