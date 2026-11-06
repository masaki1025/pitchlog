import { expect, it } from 'vitest'
import {
  undoRead,
  installUndoArtifact,
} from '../screens/GameScreenUndoProduct.test-support'
import {
  undoContext,
  prepareNativeUndo,
} from '../screens/GameScreenUndoProductProvider'
import { nativeUndoBody } from './nativeUndoWire'
import type { DurableQueueSlot } from '../lib/sync/durableQueue'
async function slot() {
  const restore = installUndoArtifact()
  try {
    const g = undoRead(2),
      c = await undoContext(g, g.checkpoint.content.scope.tenantId),
      event = prepareNativeUndo(c, '00000000-0000-4000-8000-000000000777')!
    return {
      d1: 3,
      d4: g.current_d4,
      d5: event.fields.V1,
      event,
    } as DurableQueueSlot
  } finally {
    restore()
  }
}
it('初回形成と再掲で全wire値が一致し、保存slotは書き換えない', async () => {
  const s = await slot(),
    before = structuredClone(s),
    first = nativeUndoBody(s, 'opaque-proof'),
    again = nativeUndoBody(structuredClone(s), 'opaque-proof')
  expect(again).toEqual(first)
  expect(s).toEqual(before)
  expect(Object.keys(first.events[0]!).sort()).toEqual([
    'd1',
    'd4',
    'd5',
    'event_kind',
    'game_id',
    'payload',
    'target_reference',
  ])
  expect(first.events[0]!.target_reference).toEqual({
    game: s.event.fields.V4,
    d4: (s.event.fields.V10 as Record<string, unknown>)['対象の D4'],
    d1: 2,
  })
})
it.each(['d2', 'state', 'd1', 'd5', 'kind', 'target', 'payload'])(
  '余剰/異なるslotを修復せず拒否: %s',
  async (fault) => {
    const s = await slot()
    if (fault === 'd2') s.event.fields.V6 = 1
    else if (fault === 'state') s.event.fields.V8 = {}
    else if (fault === 'd1') s.event.fields.V2 = 4
    else if (fault === 'd5')
      s.event.fields.V1 = '00000000-0000-4000-8000-000000000999'
    else if (fault === 'kind') s.event.fields.V5 = 'undo'
    else if (fault === 'target')
      s.event.fields.V10 = { game: s.event.fields.V4, d4: s.d4, d1: 2 }
    else s.event.fields.V7 = {}
    expect(() => nativeUndoBody(s, 'opaque-proof')).toThrow()
  },
)
