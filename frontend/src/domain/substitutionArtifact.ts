/** 唯一交代kernelを固定artifactのJSON入口へ接続する純adapter。 */
import {
  applySubstitution,
  isSubstitutionOperation,
  isSubstitutionState,
  isSubstitutionUuid,
  substitutionFromInitialRoster,
  type SubstitutionResult,
  type SubstitutionState,
} from './substitutionKernel'
export type SubstitutionCalculation = {
  version: 'substitution-calculation-v1'
  state: unknown
  operation: unknown
  eligibleIncomingIds: unknown
}
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
function exact(
  value: unknown,
  keys: Array<string>,
): value is Record<string, unknown> {
  if (!record(value)) return false
  for (const key of keys) if (!Object.hasOwn(value, key)) return false
  for (const key of Object.keys(value)) if (!keys.includes(key)) return false
  return true
}
/** 真正原本・所属照合は呼出側が別途行う。入力全値は閉じる。 */
export function calculateSubstitution(value: unknown): SubstitutionResult {
  if (
    !exact(value, ['version', 'state', 'operation', 'eligibleIncomingIds']) ||
    value.version !== 'substitution-calculation-v1' ||
    !isSubstitutionState(value.state) ||
    !isSubstitutionOperation(value.operation) ||
    !Array.isArray(value.eligibleIncomingIds)
  )
    return { ok: false, error: 'invalid-source' }
  let seen: Array<string> = []
  for (const player of value.eligibleIncomingIds) {
    if (!isSubstitutionUuid(player) || seen.includes(player))
      return { ok: false, error: 'invalid-source' }
    seen = seen.concat([player])
  }
  return applySubstitution(
    value.state,
    value.operation,
    value.eligibleIncomingIds,
  )
}

/** 保存済み初期rosterと現在の走者を組み立て、閉形だけを確認する。 */
export function deriveInitialSubstitutionState(
  value: unknown,
): SubstitutionState | null {
  if (
    !exact(value, ['version', 'roster', 'attackingSide', 'runners']) ||
    value.version !== 'substitution-initial-state-v1' ||
    (value.attackingSide !== 'away' && value.attackingSide !== 'home') ||
    !Array.isArray(value.runners)
  )
    return null
  try {
    const state = substitutionFromInitialRoster(
      value.roster,
      value.attackingSide,
    )
    const complete: SubstitutionState = {
      attackingSide: state.attackingSide,
      away: state.away,
      home: state.home,
      runners: value.runners,
      exitedPlayerIds: [],
      responsibility: { kind: 'unchanged' },
    }
    if (!isSubstitutionState(complete)) return null
    return complete
  } catch {
    return null
  }
}

/** 唯一計算結果を既nonplay復元文脈へ投影する。保存資格は別途必要。 */
export function transitionSubstitution(value: unknown): unknown {
  if (
    !exact(value, [
      'version',
      'state',
      'operation',
      'eligibleIncomingIds',
      'restoreContext',
    ]) ||
    value.version !== 'substitution-transition-v1' ||
    !record(value.restoreContext)
  )
    return null
  const context = value.restoreContext
  if (
    !record(context.current) ||
    !record(context.current.stateFields) ||
    !record(context.participants) ||
    !record(context.responsibility) ||
    !Array.isArray(context.runners) ||
    !isSubstitutionState(value.state) ||
    !isSubstitutionOperation(value.operation) ||
    JSON.stringify(value.state.runners) !== JSON.stringify(context.runners)
  )
    return null
  const fields = context.current.stateFields
  function field(name: string): unknown {
    for (const pair of Object.entries(fields)) {
      const key = pair.shift()
      const member = pair.pop()
      if (key === name) return member
    }
    return null
  }
  if (value.state.attackingSide === 'away') {
    if (field('state.half') !== 'top') return null
  } else if (field('state.half') !== 'bottom') return null
  if (
    value.operation.kind === 'pitcher' &&
    (value.operation.count.strikes !== field('state.count.strikes') ||
      value.operation.count.balls !== field('state.count.balls'))
  )
    return null
  const result = calculateSubstitution({
    version: 'substitution-calculation-v1',
    state: value.state,
    operation: value.operation,
    eligibleIncomingIds: value.eligibleIncomingIds,
  })
  if (!result.ok || result.continuationLineup === null) return result
  const slot = field('state.battingOrder')
  if (typeof slot !== 'string') return null
  let batting = result.state.home.battingOrder
  if (result.state.attackingSide === 'away')
    batting = result.state.away.battingOrder
  let batter: unknown = null
  for (const pair of Object.entries(batting)) {
    const name = pair.shift()
    const player = pair.pop()
    if (name === slot) batter = player
  }
  if (
    !isSubstitutionUuid(batter) ||
    !record(context.responsibility.paStartSource)
  )
    return null
  let fielding = result.continuationLineup.away
  if (result.state.attackingSide === 'away')
    fielding = result.continuationLineup.home
  let responsibility: unknown = context.responsibility
  if (result.state.responsibility.kind !== 'unchanged')
    responsibility = {
      kind: 'changed-mid-plate-appearance',
      paStartSource: context.responsibility.paStartSource,
      previousPitcherId: result.state.responsibility.previousPitcherId,
      strikesAtChange: result.state.responsibility.strikesAtChange,
      ballsAtChange: result.state.responsibility.ballsAtChange,
    }
  const afterContext = JSON.parse(JSON.stringify(context)) as Record<
    string,
    unknown
  >
  Object.assign(afterContext, {
    lineup: result.continuationLineup,
    participants: {
      batterId: batter,
      pitcherId: fielding.pitcherId,
      catcherId: fielding.catcherId,
      battingOrder: slot,
    },
    runners: result.state.runners,
    responsibility,
    substitutionState: result.state,
  })
  return {
    ok: true,
    state: result.state,
    warnings: result.warnings,
    afterContext,
  }
}

/** 投球確定後も全9配置/退出を保持し、走者・攻守・打席責任だけを前進する。 */
export function advanceSubstitutionAfterPitch(value: unknown): SubstitutionState | null {
  if (
    !exact(value, [
      'version',
      'state',
      'beforeHalf',
      'afterHalf',
      'runners',
      'plateAppearanceEnded',
    ]) ||
    value.version !== 'substitution-pitch-advance-v1' ||
    !isSubstitutionState(value.state) ||
    (value.beforeHalf !== 'top' && value.beforeHalf !== 'bottom') ||
    (value.afterHalf !== 'top' && value.afterHalf !== 'bottom') ||
    !Array.isArray(value.runners) ||
    typeof value.plateAppearanceEnded !== 'boolean'
  )
    return null
  let beforeSide: 'away' | 'home' = 'home'
  if (value.beforeHalf === 'top') beforeSide = 'away'
  if (
    value.state.attackingSide !== beforeSide ||
    (value.beforeHalf !== value.afterHalf && !value.plateAppearanceEnded)
  )
    return null
  const next = JSON.parse(JSON.stringify(value.state)) as SubstitutionState
  next.attackingSide = 'home'
  if (value.afterHalf === 'top') next.attackingSide = 'away'
  next.runners = value.runners
  if (value.plateAppearanceEnded) next.responsibility = { kind: 'unchanged' }
  if (!isSubstitutionState(next)) return null
  return next
}
