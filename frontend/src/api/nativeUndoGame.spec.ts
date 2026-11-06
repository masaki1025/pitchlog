import { expect, it } from 'vitest'
import { isNativeUndoGame, completeUndoSource } from './nativeUndoGame'
import { undoRead } from '../screens/GameScreenUndoProduct.test-support'
it.each([2, 3, 4, 5])('実既DTOで完全Source%dを保持する', async (index) => {
  const game = undoRead(index)
  expect(isNativeUndoGame(game)).toBe(true)
  const source = await completeUndoSource(
    game,
    game.checkpoint.content.scope.tenantId,
  )
  expect(source.activeStack).toEqual(game.page.items)
})
it.each([
  'partial',
  'missing',
  'extra',
  'digest',
  'tenant',
  'current',
  'generation',
])('情報不足/異なるanchorを推測しない: %s', async (fault) => {
  const game = undoRead(2),
    tenant = game.checkpoint.content.scope.tenantId
  const bad = structuredClone(game) as unknown as Record<string, unknown>
  if (fault === 'extra') bad.extra = true
  else if (fault === 'missing') delete bad.checkpoint
  else if (fault === 'current') bad.after = {}
  else if (fault === 'generation') bad.current_d4 = 'other'
  else if (fault === 'partial')
    bad.page = { ...game.page, next_cursor: 'remaining' }
  else if (fault === 'digest')
    bad.checkpoint = {
      ...game.checkpoint,
      ref: { ...game.checkpoint.ref, digest: '0'.repeat(64) },
    }
  await expect(
    completeUndoSource(
      bad as unknown as typeof game,
      fault === 'tenant' ? '00000000-0000-4000-8000-000000000999' : tenant,
    ),
  ).rejects.toThrow()
})

// HTTP/DTO境界だけの明示double。fingerprint等は形の試験値で、実DB資格ではない。
import { beforeEach, afterEach, vi } from 'vitest'
import { createPinia, setActivePinia, disposePinia, type Pinia } from 'pinia'
import { setVerifiedAuthForTest } from './auth.test-support'
import { useAuthStore } from '../stores/authStore'
import { readCompleteUndoGame } from './nativeUndoGame'
import { playHash } from './terminalPitchWire'
import type { ActiveFrame } from '../../../contracts/state-transition/nonplay_prefix_bridge_v1'
let pinia: Pinia
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: undoRead(2).checkpoint.content.scope.tenantId,
    teamName: 'DTO-only',
  })
})
afterEach(() => {
  disposePinia(pinia)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
async function transport205() {
  const original = undoRead(2),
    r = structuredClone(original.checkpoint.content.restored),
    frames: ActiveFrame[] = []
  for (let n = 205; n >= 1; n--) {
    const frame = structuredClone(original.page.items[0]!),
      uuid = (k: number) =>
        '00000000-0000-4000-8000-' + k.toString(16).padStart(12, '0')
    frames.push({
      ...frame,
      play: {
        ...frame.play,
        playId: uuid(1000 + n),
        physicalPlayNumber: String(n),
        d2: String(n * 1000),
        source: {
          ...frame.play.source,
          eventId: uuid(2000 + n),
          d5: uuid(3000 + n),
          d1: String(n),
        },
      },
      beforeContext: structuredClone(r),
      afterContext: structuredClone(r),
      historyEntry: {
        ...frame.historyEntry,
        difference: { ...frame.historyEntry.difference, stateFields: {} },
      },
    })
  }
  const content = {
    ...original.checkpoint.content,
    restored: r,
    d3: '205',
    activeDepth: '205',
    activeHead: frames[0]!.play,
    d1Head: { kind: 'accepted-event' as const, source: frames[0]!.play.source },
    projectionHead: {
      kind: 'd1-event' as const,
      source: frames[0]!.play.source,
    },
    historyVersion: '205',
    storageHistoryEpoch: '205',
    nextPhysicalPlayNumber: '206',
  }
  const checkpoint = {
    ...original.checkpoint,
    content,
    ref: {
      ...original.checkpoint.ref,
      revision: '205',
      digest: await playHash(content),
    },
  }
  const base = {
    ...original,
    checkpoint,
    after: r.current,
    next_position: { d1: '206', d2: '206000' },
  }
  const page = (start: number) => ({
    ...base,
    page: {
      items: frames.slice(start, start + 100),
      next_cursor: start + 100 < frames.length ? String(start + 100) : null,
    },
  })
  return { page, base, frames }
}
function mockedFetch(
  page: (cursor: string | null, projection: string | null) => unknown,
) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input, init) => {
      const url = new URL(String(input), location.origin),
        value = page(
          url.searchParams.get('cursor'),
          url.searchParams.get('projection'),
        )
      return new Response(JSON.stringify(value), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'X-Pitchlog-Tenant-Match': '1',
          'X-Pitchlog-Tenant-Challenge': new Headers(init?.headers).get(
            'X-Pitchlog-Tenant-Challenge',
          )!,
        },
      })
    }),
  )
}
it('205件を100/100/5の有限HTTP pageで全値保持し、100件で打切らない', async () => {
  const t = await transport205()
  mockedFetch((cursor) => t.page(Number(cursor ?? 0)))
  const value = await readCompleteUndoGame(
    t.base.id,
    t.base.checkpoint.content.scope.tenantId,
  )
  expect(value.source.activeStack).toEqual(t.frames)
  expect(value.source.activeStack).toHaveLength(205)
  expect(value.storedNative).toBe(true)
  expect(fetch).toHaveBeenCalledTimes(4)
})
it('途中pageのCP変更は全履歴へ合成しない', async () => {
  const t = await transport205()
  mockedFetch((cursor) => {
    const game = t.page(Number(cursor ?? 0))
    return cursor === null
      ? game
      : { ...game, last_saved_at: '2026-11-06T11:00:00Z' }
  })
  await expect(
    readCompleteUndoGame(t.base.id, t.base.checkpoint.content.scope.tenantId),
  ).rejects.toThrow('取得中に変わり')
})
it('繰返しcursorは次の要求へ進めず閉拒否する', async () => {
  const t = await transport205()
  mockedFetch((cursor) => {
    const game = t.page(Number(cursor ?? 0))
    return cursor === null
      ? game
      : { ...game, page: { ...game.page, next_cursor: '100' } }
  })
  await expect(
    readCompleteUndoGame(t.base.id, t.base.checkpoint.content.scope.tenantId),
  ).rejects.toThrow('循環')
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('independent: 新undo GETが完全Sourceを返すlegacy2球から初回取消を提示できる', async () => {
  const game = undoRead(2)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input, init) => {
      const url = new URL(String(input), location.origin)
      if (url.searchParams.get('projection') === 'play-prefix-v3')
        return new Response(JSON.stringify({ detail: 'Service Unavailable' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        })
      return new Response(JSON.stringify(game), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'X-Pitchlog-Tenant-Match': '1',
          'X-Pitchlog-Tenant-Challenge': new Headers(init?.headers).get(
            'X-Pitchlog-Tenant-Challenge',
          )!,
        },
      })
    }),
  )
  const result = await readCompleteUndoGame(
    game.id,
    game.checkpoint.content.scope.tenantId,
  )
  expect(result.source.activeStack).toHaveLength(2)
  expect(result.storedNative).toBe(false)
})

import recordedLegacy from './fixtures/lineupPrefixGame.recorded.v3.json'
import { STARTED_GAME_BASE_KEYS } from './startedGame'
import { isLineupPrefixGame } from './lineupPrefixGame'

function legacyUndoPair() {
  // 既契約Sourceと既DTOを使う輸送試験。野球計算の期待値を生成しない。
  const game = undoRead(2),
    content = game.checkpoint.content
  const standard: Record<string, unknown> = structuredClone(
    recordedLegacy.value,
  )
  for (const key of STARTED_GAME_BASE_KEYS) standard[key] = game[key]
  Object.assign(standard, {
    read_kind: 'lineup-prefix',
    after: game.after,
    rules: content.restored.rules,
    lineup: content.restored.lineup,
    participants: content.restored.participants,
    runners: content.restored.runners,
    roster_digest: content.restored.rosterDigest,
    prefix_ref: {
      ...recordedLegacy.value.prefix_ref,
      tenantId: content.scope.tenantId,
      gameId: game.id,
      generation: game.current_d4,
      historyVersion: content.historyVersion,
      checkpoint: {
        ...recordedLegacy.value.prefix_ref.checkpoint,
        revision: game.checkpoint.ref.revision,
      },
      origin: {
        ...recordedLegacy.value.prefix_ref.origin,
        eventId: game.checkpoint.ref.id,
      },
    },
    checkpoint_anchor: {
      id: game.checkpoint.ref.id,
      revision: game.checkpoint.ref.revision,
      history_version: content.storageHistoryEpoch,
    },
    storage_anchor: {
      id: game.checkpoint.ref.id,
      history_epoch: content.storageHistoryEpoch,
    },
    next_position: game.next_position,
    recovery_generation: game.recovery_generation,
    append_policy: game.append_policy,
    last_saved_at: game.last_saved_at,
    page: { items: [], next_cursor: null },
  })
  // この既SourceのDH・1番DH配置を、輸送metadataにも明示する。
  standard.applied_rules = {
    ...game.applied_rules,
    regulationInnings: Number(content.restored.rules.regulationInnings),
    extensionLimit: Number(content.restored.rules.extensionLimit),
    dh: content.restored.rules.dh,
  }
  standard.roster = {
    teams: (['away', 'home'] as const).map((side) => {
      const lineup = content.restored.lineup[side]
      return {
        side,
        team_id: lineup.teamId,
        participants: [
          ...Object.entries(lineup.battingOrder).map(([slot, playerId]) => ({
            player: { kind: 'official', player_id: playerId },
            batting_slot: { kind: 'slot', slot },
            roles:
              slot === '1'
                ? [{ kind: 'designated-hitter' }]
                : [{ kind: 'fielding', position: slot }],
            entry_origin: { kind: 'initial' },
          })),
          {
            player: { kind: 'official', player_id: lineup.pitcherId },
            batting_slot: { kind: 'none' },
            roles: [{ kind: 'fielding', position: '1' }],
            entry_origin: { kind: 'initial' },
          },
        ],
      }
    }),
  }
  expect(isLineupPrefixGame(standard)).toBe(true)
  if (!isLineupPrefixGame(standard)) throw new Error('試験用legacy DTOが不正')
  expect(standard.prefix_ref.checkpoint.id).not.toBe(
    standard.checkpoint_anchor?.id,
  )
  return { game, standard }
}

it('legacy入力CPと保存CPが異なっても実保存anchorで取消原本を照合する', async () => {
  const { game, standard } = legacyUndoPair()
  mockedFetch((_cursor, projection) =>
    projection === 'play-prefix-v3' ? standard : game,
  )
  const value = await readCompleteUndoGame(
    game.id,
    game.checkpoint.content.scope.tenantId,
  )
  expect(value.source.checkpoint).toEqual(game.checkpoint)
  expect(value.storedNative).toBe(false)
})

it('入力CPが一致しても保存CPが別なら取消原本へ接続しない', async () => {
  const { game, standard } = legacyUndoPair()
  const other = recordedLegacy.value.checkpoint_anchor.id
  const wrong = {
    ...standard,
    prefix_ref: {
      ...standard.prefix_ref,
      checkpoint: {
        ...standard.prefix_ref.checkpoint,
        id: game.checkpoint.ref.id,
      },
      origin: { ...standard.prefix_ref.origin, eventId: other },
    },
    checkpoint_anchor: { ...standard.checkpoint_anchor!, id: other },
    storage_anchor: { ...standard.storage_anchor!, id: other },
  }
  expect(isLineupPrefixGame(wrong)).toBe(true)
  mockedFetch((_cursor, projection) =>
    projection === 'play-prefix-v3' ? wrong : game,
  )
  await expect(
    readCompleteUndoGame(game.id, game.checkpoint.content.scope.tenantId),
  ).rejects.toThrow('派生CPと保存原本')
})
