/** 既契約手例の機械射影。DB/実認可や新計算の正解を作らない。 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { Script, createContext } from 'node:vm'
import fixture from '../api/fixtures/nativeUndoProduct.current.v1.json'
import metadata from '../api/fixtures/lineupPrefixGame.v3.json'
import { STARTED_GAME_BASE_KEYS } from '../api/startedGame'
import { isNativeUndoGame, type NativeUndoGame } from '../api/nativeUndoGame'
import type { Observations } from '../../../contracts/state-transition/play_prefix_v2_payload_v1'
import { isPlayDefinition } from '../api/terminalPitchWire'
import { isNonplayDefinition } from '../api/nonplayContract'
import type { Source } from '../../../contracts/state-transition/nonplay_prefix_bridge_v1'
export function installUndoArtifact(): () => void {
  const old = Object.getOwnPropertyDescriptor(globalThis, 'PitchlogDomain'),
    scope = createContext({})
  new Script(
    readFileSync(
      resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
      'utf8',
    ),
  ).runInContext(scope)
  Object.defineProperty(globalThis, 'PitchlogDomain', {
    configurable: true,
    value: Object.getOwnPropertyDescriptor(scope, 'PitchlogDomain')!.value,
  })
  return () => {
    if (old) Object.defineProperty(globalThis, 'PitchlogDomain', old)
    else Reflect.deleteProperty(globalThis, 'PitchlogDomain')
  }
}
export function undoSample(index = 4) {
  return structuredClone(fixture.samples.find((x) => x.index === index)!)
}
export function undoRead(index = 4): NativeUndoGame {
  const sample = undoSample(index),
    q = sample.payload.calculation.request,
    source: unknown = q.source
  if (!isNonplayDefinition<Source>(source, 'Source'))
    throw new Error('規範Source fixtureの型が不一致')
  const base = Object.fromEntries(
    STARTED_GAME_BASE_KEYS.map((k) => [
      k,
      metadata.value[k as keyof typeof metadata.value],
    ]),
  )
  const value: unknown = {
    ...base,
    read_kind: 'nonplay-prefix',
    profile: 'nonplay-prefix-read-v1',
    id: source.checkpoint.content.scope.gameId,
    current_d4: source.checkpoint.content.scope.generation,
    checkpoint: source.checkpoint,
    after: source.checkpoint.content.restored.current,
    next_position: { d1: q.sourcePosition.d1, d2: q.sourcePosition.d2 },
    recovery_generation: '1',
    page: { items: source.activeStack, next_cursor: null },
    append_policy: {
      version: 'ordinary-append-v1',
      first_d2: '1',
      d2_gap: '1000',
      max_d2: '9007199254740991',
    },
    last_saved_at: '2026-11-06T10:00:00Z',
  }
  if (!isNativeUndoGame(value)) throw new Error('規範metadata射影が不一致')
  return value
}

export function undoObservation(index = 4) {
  const value: unknown = undoSample(index).payload.observations
  if (!isPlayDefinition<Observations>(value, 'PayloadObservations'))
    throw new Error('規範の観測が不一致')
  return value
}
