import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { afterAll, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import * as native from './nativeUndoGame'
import * as roster from './roster'
import { readSubstitutionContext } from './substitutionRead'
import { undoRead } from '../screens/GameScreenUndoProduct.test-support'

const previous = Object.getOwnPropertyDescriptor(globalThis, 'PitchlogDomain')
beforeAll(() => {
  const scope = createContext({})
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
})
afterAll(() => {
  vi.restoreAllMocks()
  if (previous) Object.defineProperty(globalThis, 'PitchlogDomain', previous)
  else Reflect.deleteProperty(globalThis, 'PitchlogDomain')
})
const game = undoRead(2)
const tenant = game.checkpoint.content.scope.tenantId
const source = {
  formatVersion: 'nonplay-prefix-source-v1' as const,
  checkpoint: game.checkpoint,
  activeStack: game.page.items,
}
beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(native, 'readCompleteUndoGame').mockResolvedValue({
    game,
    source,
    storedNative: true,
  })
  vi.spyOn(roster, 'listPlayers').mockImplementation(async () => ({
    items: [],
    next_cursor: null,
  }))
})

it('真正GETのCPと二チームのページを照合して交代状態を供給する', async () => {
  const read = await readSubstitutionContext(game.id, tenant)
  expect(read.checkpoint).toEqual(game.checkpoint.ref)
  expect(read.generation).toBe(game.current_d4)
  expect(read.state.runners).toEqual(game.checkpoint.content.restored.runners)
  expect(roster.listPlayers).toHaveBeenCalledTimes(2)
  expect(roster.listPlayers).toHaveBeenCalledWith(
    { team_record_id: game.lineups.away.team_record_id, limit: 100 },
    { signal: undefined },
  )
})

it('候補ページ中のCP改訂を拒否する', async () => {
  const changed = structuredClone(game)
  Object.assign(changed.checkpoint.ref, { revision: '999' })
  vi.mocked(native.readCompleteUndoGame)
    .mockResolvedValueOnce({ game, source, storedNative: true })
    .mockResolvedValueOnce({
      game: changed,
      source: { ...source, checkpoint: changed.checkpoint },
      storedNative: true,
    })
  await expect(readSubstitutionContext(game.id, tenant)).rejects.toThrow(
    '取得中に試合が変わりました',
  )
})

it('交代frameに状態がない値と循環する候補ページを拒否する', async () => {
  const incomplete = structuredClone(source)
  Object.assign(incomplete.checkpoint.content, { substitutionFrames: [{}] })
  vi.mocked(native.readCompleteUndoGame).mockResolvedValue({
    game,
    source: incomplete,
    storedNative: true,
  })
  await expect(readSubstitutionContext(game.id, tenant)).rejects.toThrow(
    '交代履歴の状態が欠落',
  )
  vi.mocked(native.readCompleteUndoGame).mockResolvedValue({
    game,
    source,
    storedNative: true,
  })
  vi.mocked(roster.listPlayers).mockResolvedValue({
    items: [],
    next_cursor: 'same-cursor',
  })
  await expect(readSubstitutionContext(game.id, tenant)).rejects.toThrow(
    'ページが進みません',
  )
})
