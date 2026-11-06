import { beforeAll, afterAll, expect, it } from 'vitest'
import {
  undoRead,
  undoSample,
  undoObservation,
  installUndoArtifact,
} from './GameScreenUndoProduct.test-support'
import {
  undoContext,
  prepareNativeUndo,
  prepareBallAfterUndo,
} from './GameScreenUndoProductProvider'
import { nativeUndoBody } from '../api/nativeUndoWire'
import { isNonplayDefinition } from '../api/nonplayContract'
import type { DurableQueueSlot } from '../lib/sync/durableQueue'
let restore: () => void
beforeAll(() => {
  restore = installUndoArtifact()
})
afterAll(() => restore())
it.each([2, 3])(
  '正式artifactで%dの取消を生成し、P1はD2/V8を含めない',
  async (index) => {
    const game = undoRead(index),
      c = await undoContext(game, game.checkpoint.content.scope.tenantId),
      event = prepareNativeUndo(c, '00000000-0000-4000-8000-000000000777')!
    expect(Object.keys(event.fields).sort()).toEqual([
      'V1',
      'V10',
      'V3',
      'V4',
      'V5',
      'V7',
    ])
    const slot = {
      d1: Number(game.next_position.d1),
      d4: game.current_d4,
      d5: event.fields.V1,
      event,
    } as DurableQueueSlot
    const body = nativeUndoBody(slot, 'opaque-proof')
    expect(isNonplayDefinition(body.events[0], 'UndoEvent')).toBe(true)
    expect(body.events[0]!.target_reference.d1).toBe(
      Number(c.source.activeStack[0]!.play.source.d1),
    )
    expect(event.fields.V5).toBe('2')
    expect(body.events[0]!.event_kind).toBe('undo')
  },
)
it('空履歴はeventを作らない', async () => {
  const g = undoRead(4),
    c = await undoContext(g, g.checkpoint.content.scope.tenantId)
  expect(
    prepareNativeUndo(c, '00000000-0000-4000-8000-000000000777'),
  ).toBeNull()
})
it('取消後の通常ボールは唯一Source6から全応答を供給する', async () => {
  const g = undoRead(4),
    c = await undoContext(g, g.checkpoint.content.scope.tenantId),
    s = undoSample(4),
    q = s.payload.calculation.request
  const event = prepareBallAfterUndo(
    c,
    undoObservation(),
    q.playIdentity,
    q.nextCheckpoint.id,
  )
  const expected = structuredClone(s.payload)
  expected.calculation.request.nextCheckpoint.digest = '0'.repeat(64)
  expected.calculation.response.value.nextPrefixRef.digest = '0'.repeat(64)
  expect(event.fields.V7).toEqual(expected)
  expect(
    isNonplayDefinition(
      event.fields.V7,
      '$root',
      'lineup_play_prefix_payload_schema_v1',
    ),
  ).toBe(true)
  expect(event.fields.V8).toEqual(s.stateDiff)
})
