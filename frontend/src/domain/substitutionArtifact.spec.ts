import { expect, it } from 'vitest'
import { undoRead } from '../screens/GameScreenUndoProduct.test-support'
import { isNonplayDefinition } from '../api/nonplayContract'
import { substitutionFromInitialRoster } from './substitutionKernel'
import {
  advanceSubstitutionAfterPitch,
  transitionSubstitution,
} from './substitutionArtifact'

const game = undoRead(2)
const restored = game.checkpoint.content.restored
const side =
  restored.current.stateFields['state.half'] === 'top' ? 'away' : 'home'
const state = {
  ...substitutionFromInitialRoster(game.roster, side),
  runners: restored.runners,
}
const fielding = side === 'away' ? state.home : state.away
const newcomer = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
const operation = {
  kind: 'pitcher',
  side: side === 'away' ? 'home' : 'away',
  outgoingId: fielding.fielding['1'],
  incomingId: newcomer,
  count: {
    strikes: restored.current.stateFields['state.count.strikes'],
    balls: restored.current.stateFields['state.count.balls'],
  },
  dh: 'retain',
}

it('交代後のCP文脈を唯一計算から作り、球・得点・履歴評価を保持する', () => {
  const result = transitionSubstitution({
    version: 'substitution-transition-v1',
    state,
    operation,
    eligibleIncomingIds: [newcomer],
    restoreContext: restored,
  }) as Record<string, unknown>
  expect(result.ok).toBe(true)
  const after = result.afterContext as Record<string, unknown>
  expect(isNonplayDefinition(after, 'RestoreContext')).toBe(true)
  expect(after.current).toEqual(restored.current)
  expect(after.rules).toEqual(restored.rules)
  expect(after.lastPlayEvaluation).toEqual(restored.lastPlayEvaluation)
  expect((after.participants as { pitcherId: string }).pitcherId).toBe(newcomer)
})

it('交代投手のカウント偽装は純評価前に拒否する', () => {
  const result = transitionSubstitution({
    version: 'substitution-transition-v1',
    state,
    operation: { ...operation, count: { ...operation.count, balls: '3' } },
    eligibleIncomingIds: [newcomer],
    restoreContext: restored,
  })
  expect(result).toBeNull()
})

it('次球後も守備配置と退出を保持し、打席終了時だけ責任を閉じる', () => {
  const transition = transitionSubstitution({
    version: 'substitution-transition-v1',
    state,
    operation,
    eligibleIncomingIds: [newcomer],
    restoreContext: restored,
  }) as { state: typeof state }
  const changed = transition.state
  const request = {
    version: 'substitution-pitch-advance-v1',
    state: changed,
    beforeHalf: restored.current.stateFields['state.half'],
    afterHalf: restored.current.stateFields['state.half'],
    runners: restored.runners,
    plateAppearanceEnded: false,
  }
  const ongoing = advanceSubstitutionAfterPitch(request)
  expect(ongoing?.away).toEqual(changed.away)
  expect(ongoing?.home).toEqual(changed.home)
  expect(ongoing?.exitedPlayerIds).toEqual(changed.exitedPlayerIds)
  expect(ongoing?.responsibility).toEqual(changed.responsibility)
  const ended = advanceSubstitutionAfterPitch({
    ...request,
    plateAppearanceEnded: true,
  })
  expect(ended?.responsibility).toEqual({ kind: 'unchanged' })
  expect(advanceSubstitutionAfterPitch({ ...request, afterHalf: 'invalid' })).toBeNull()
})
