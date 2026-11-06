import { expect, it } from 'vitest'
import { undoRead } from '../screens/GameScreenUndoProduct.test-support'
import { applyGameLifecycle } from '../domain/gameLifecycle'
import { substitutionFromInitialRoster } from '../domain/substitutionKernel'
import { substitutionGapsMatch } from './substitutionHistory'

const game = undoRead(2)
const base = {
  formatVersion: 'nonplay-prefix-source-v1' as const,
  checkpoint: game.checkpoint,
  activeStack: game.page.items,
}
function source() {
  const value = structuredClone(base)
  const content = value.checkpoint.content
  const top = value.activeStack[0]!
  const state = substitutionFromInitialRoster(game.roster, 'away')
  const afterContext = { ...content.restored, substitutionState: state }
  const frame = {
    source: {
      ...top.play.source,
      eventId: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
      d5: 'ffffffff-ffff-4fff-8fff-ffffffffffff',
      d1: String(BigInt(top.play.source.d1) + 1n),
      eventKind: 'substitution' as const,
    },
    afterPlayId: top.play.playId,
    beforeContext: top.afterContext,
    afterContext,
  }
  Object.assign(content, {
    restored: afterContext,
    substitutionFrames: [frame],
  })
  return { value, frame }
}

it('保存playの文脈差を交代frame一件で説明する', () => {
  const { value } = source()
  expect(substitutionGapsMatch(value)).toBe(true)
})

it('別試合、同D5、同位置の交代frameを拒否する', () => {
  const { value, frame } = source()
  const content = value.checkpoint
    .content as typeof value.checkpoint.content & {
    substitutionFrames: unknown[]
  }
  content.substitutionFrames = [
    { ...frame, source: { ...frame.source, gameId: 'bad' } },
  ]
  expect(substitutionGapsMatch(value)).toBe(false)
  content.substitutionFrames = [
    frame,
    {
      ...frame,
      source: {
        ...frame.source,
        eventId: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
      },
    },
  ]
  expect(substitutionGapsMatch(value)).toBe(false)
})

it('再開bridgeによるcurrent変更をplay間の同一gapで連結する', () => {
  const { value, frame } = source()
  const top = value.activeStack[0]!
  const ended = structuredClone(top.afterContext)
  Object.assign(ended.current, {
    stateFields: { ...ended.current.stateFields, 'state.gameEnded': true },
  })
  Object.assign(top, { afterContext: ended })
  frame.beforeContext = ended
  frame.afterContext = {
    ...ended,
    substitutionState: frame.afterContext.substitutionState,
  }
  const active = {
    version: '1',
    eventId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    receiptId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  }
  const request = {
    formatVersion: 'native-game-lifecycle-v1',
    action: 'reopen',
    current: frame.afterContext.current,
    lifecycle: { status: 'finished', lastVersion: '1', active },
    target: active,
    event: {
      eventId: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
      receiptId: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    },
  }
  const response = JSON.parse(applyGameLifecycle(JSON.stringify(request)))
  expect(response.ok).toBe(true)
  const after = { ...frame.afterContext, current: response.value.current }
  const control = {
    source: {
      ...top.play.source,
      eventId: request.event.eventId,
      d5: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
      d1: String(BigInt(top.play.source.d1) + 2n),
      eventKind: 'game_reopen',
    },
    action: 'reopen',
    anchorEventId: top.play.source.eventId,
    beforeContext: frame.afterContext,
    afterContext: after,
    kernel: { request, response },
    frameId: 'ffffffff-ffff-4fff-8fff-ffffffffffff',
    checkpointBefore: value.checkpoint.ref,
  }
  Object.assign(value.checkpoint.content, {
    restored: after,
    controlBridges: [control],
  })
  expect(substitutionGapsMatch(value)).toBe(true)
  const collision = structuredClone(value)
  Object.assign(collision.checkpoint.content.controlBridges![0]!.source, {
    d1: frame.source.d1,
  })
  expect(substitutionGapsMatch(collision)).toBe(false)
  Object.assign(control, { afterContext: ended })
  expect(substitutionGapsMatch(value)).toBe(false)
})
