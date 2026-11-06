/** プレイ保存原本を改変せず、CP内の交代・終了再開frameで文脈差を照合する。 */
import type { Source } from '../../../contracts/state-transition/nonplay_prefix_bridge_v1'
import { sameOrdinaryWire } from './ordinaryPitchWire'
import { isNonplayDefinition } from './nonplayContract'

type Frame = Readonly<{
  source: Readonly<{
    eventId: string
    gameId: string
    generation: string
    d1: string
    d5: string
    eventKind: 'substitution'
  }>
  afterPlayId: string | null
  beforeContext: unknown
  afterContext: unknown
}>
type Control = Readonly<{
  source: Readonly<{
    eventId: string
    gameId: string
    generation: string
    d1: string
    d5: string
    eventKind: 'game_end_declaration' | 'game_reopen'
  }>
  action: 'end' | 'reopen'
  anchorEventId: string
  beforeContext: unknown
  afterContext: unknown
}>

/** 契約schema・全GET証拠は呼出側が別途確認する。 */
export function substitutionGapsMatch(source: Source): boolean {
  const content = source.checkpoint
    .content as typeof source.checkpoint.content & {
    substitutionFrames?: readonly Frame[]
    controlBridges?: readonly Control[]
  }
  const frames = content.substitutionFrames ?? []
  const controls = content.controlBridges ?? []
  if (!Array.isArray(frames) || !Array.isArray(controls)) return false
  const used = new Set<string>()
  const usedD5 = new Set<string>()
  const usedPosition = new Set<string>()
  const playIds = new Set(source.activeStack.map((frame) => frame.play.playId))
  const playEvents = new Set(
    source.activeStack.map((frame) => frame.play.source.eventId),
  )
  for (const play of source.activeStack) {
    used.add(play.play.source.eventId)
    usedD5.add(play.play.source.d5)
    usedPosition.add(`${play.play.source.generation}/${play.play.source.d1}`)
  }
  for (const frame of frames) {
    if (
      !isNonplayDefinition<Frame>(frame, 'SubstitutionFrame') ||
      frame.source.eventKind !== 'substitution' ||
      frame.source.gameId !== content.scope.gameId ||
      used.has(frame.source.eventId) ||
      usedD5.has(frame.source.d5) ||
      usedPosition.has(`${frame.source.generation}/${frame.source.d1}`) ||
      (frame.afterPlayId !== null && !playIds.has(frame.afterPlayId)) ||
      typeof frame.afterContext !== 'object' ||
      frame.afterContext === null ||
      !('substitutionState' in frame.afterContext)
    )
      return false
    used.add(frame.source.eventId)
    usedD5.add(frame.source.d5)
    usedPosition.add(`${frame.source.generation}/${frame.source.d1}`)
  }
  for (const control of controls) {
    if (
      !isNonplayDefinition<Control>(control, 'LifecycleControlBridge') ||
      control.source.gameId !== content.scope.gameId ||
      control.source.eventKind !==
        (control.action === 'end' ? 'game_end_declaration' : 'game_reopen') ||
      used.has(control.source.eventId) ||
      usedD5.has(control.source.d5) ||
      usedPosition.has(`${control.source.generation}/${control.source.d1}`) ||
      (control.anchorEventId !== content.origin.eventId &&
        !playEvents.has(control.anchorEventId))
    )
      return false
    used.add(control.source.eventId)
    usedD5.add(control.source.d5)
    usedPosition.add(`${control.source.generation}/${control.source.d1}`)
  }
  function gap(
    playAnchor: string | null,
    eventAnchor: string,
    before: unknown,
    after: unknown,
  ): boolean {
    let current = before
    const pending = [
      ...frames.filter((frame) => frame.afterPlayId === playAnchor),
      ...controls.filter((control) => control.anchorEventId === eventAnchor),
    ].sort((a, b) => {
      const left = BigInt(a.source.d1)
      const right = BigInt(b.source.d1)
      return left < right ? -1 : left > right ? 1 : 0
    })
    let lastD1: bigint | null = null
    for (const frame of pending) {
      const d1 = BigInt(frame.source.d1)
      if (lastD1 !== null && d1 <= lastD1) return false
      lastD1 = d1
      if (current !== null && !sameOrdinaryWire(current, frame.beforeContext))
        return false
      current = frame.afterContext
    }
    return current === null || sameOrdinaryWire(current, after)
  }
  let newer: (typeof source.activeStack)[number] | null = null
  for (const older of source.activeStack) {
    if (
      !gap(
        older.play.playId,
        older.play.source.eventId,
        older.afterContext,
        newer === null ? content.restored : newer.beforeContext,
      )
    )
      return false
    newer = older
  }
  return (
    gap(
      null,
      content.origin.eventId,
      null,
      newer === null ? content.restored : newer.beforeContext,
    ) &&
    frames.every(
      (frame) => frame.afterPlayId === null || playIds.has(frame.afterPlayId),
    )
  )
}
