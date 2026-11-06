/** 実GETと登録選手pageから、交代画面に渡す検査済み文脈を作る。 */
import { readCompleteUndoGame } from './nativeUndoGame'
import { listPlayers, type PlayerRead } from './roster'
import { canonicalUuid } from './authIntent'
import { sameOrdinaryWire } from './ordinaryPitchWire'
import { invokeFirstBallDomain } from '../lib/generated/wrappers/domainArtifact'
import {
  isSubstitutionState,
  type Side,
  type SubstitutionState,
} from '../domain/substitutionKernel'
import type { VerifiedSubstitutionContext } from '../screens/GameScreenSubstitutionProductProvider'

function safePosition(raw: string): number {
  if (
    !/^[1-9][0-9]*$/.test(raw) ||
    BigInt(raw) > BigInt(Number.MAX_SAFE_INTEGER)
  )
    throw new Error('交代位置の範囲が不一致です')
  return Number(raw)
}

function player(value: unknown, teamId: string): value is PlayerRead {
  if (
    value === null ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    Object.keys(value).sort().join(',') !==
      'bats,hidden_at,id,name,roster_label_key,roster_status_key,team_record_id,throws,uniform_number'
  )
    return false
  const row = value as Record<string, unknown>
  return (
    typeof row.id === 'string' &&
    canonicalUuid.test(row.id) &&
    row.team_record_id === teamId &&
    typeof row.name === 'string' &&
    row.name.length > 0 &&
    typeof row.roster_status_key === 'string' &&
    row.hidden_at === null &&
    (row.throws === null || row.throws === 'right' || row.throws === 'left') &&
    (row.bats === null ||
      row.bats === 'right' ||
      row.bats === 'left' ||
      row.bats === 'both') &&
    (row.uniform_number === null || typeof row.uniform_number === 'string') &&
    (row.roster_label_key === null || typeof row.roster_label_key === 'string')
  )
}

async function teamPlayers(
  teamId: string,
  signal?: AbortSignal,
): Promise<PlayerRead[]> {
  const seen = new Set<string>()
  const rows: PlayerRead[] = []
  let cursor: string | undefined
  while (true) {
    const page = await listPlayers(
      { team_record_id: teamId, limit: 100, ...(cursor ? { cursor } : {}) },
      { signal },
    )
    if (
      !Array.isArray(page?.items) ||
      page.items.length > 100 ||
      (page.next_cursor !== null &&
        (typeof page.next_cursor !== 'string' ||
          !page.next_cursor ||
          seen.has(page.next_cursor)))
    )
      throw new Error('交代候補のページを確認できません')
    for (const row of page.items) {
      if (!player(row, teamId) || rows.some((prior) => prior.id === row.id))
        throw new Error('交代候補の所属・重複を確認できません')
      rows.push(row)
    }
    if (page.next_cursor === null) return rows
    if (page.items.length === 0) throw new Error('交代候補のページが進みません')
    seen.add(page.next_cursor)
    cursor = page.next_cursor
  }
}

/** CP改訂後の要求だけを用意する。GETは保存資格ではなく、HTTP側で再照合する。 */
export async function readSubstitutionContext(
  gameId: string,
  tenantId: string,
  signal?: AbortSignal,
): Promise<VerifiedSubstitutionContext> {
  const read = await readCompleteUndoGame(gameId, tenantId, signal)
  const content = read.source.checkpoint.content
  const restored = content.restored
  const side: Side =
    restored.current.stateFields['state.half'] === 'top' ? 'away' : 'home'
  const stored =
    'substitutionState' in restored ? restored.substitutionState : undefined
  if (
    stored === undefined &&
    'substitutionFrames' in content &&
    content.substitutionFrames?.length
  )
    throw new Error('交代履歴の状態が欠落しています')
  const state: unknown =
    stored === undefined
      ? invokeFirstBallDomain('deriveInitialSubstitutionStateV1', {
          version: 'substitution-initial-state-v1',
          roster: read.game.roster,
          attackingSide: side,
          runners: restored.runners,
        })
      : stored
  if (
    !isSubstitutionState(state) ||
    state.attackingSide !== side ||
    !sameOrdinaryWire(state.runners, restored.runners) ||
    state.away.teamId !== read.game.roster.teams[0].team_id ||
    state.home.teamId !== read.game.roster.teams[1].team_id
  )
    throw new Error('交代状態が保存CPと一致しません')
  const beforeRef = structuredClone(read.source.checkpoint.ref)
  const away = await teamPlayers(read.game.lineups.away.team_record_id, signal)
  const home = await teamPlayers(read.game.lineups.home.team_record_id, signal)
  const after = await readCompleteUndoGame(gameId, tenantId, signal)
  if (
    !sameOrdinaryWire(beforeRef, after.source.checkpoint.ref) ||
    after.game.current_d4 !== read.game.current_d4 ||
    !sameOrdinaryWire(after.game.lineups, read.game.lineups)
  )
    throw new Error('交代候補の取得中に試合が変わりました')
  const activeAway = away.filter((p) => p.roster_status_key === 'active')
  const activeHome = home.filter((p) => p.roster_status_key === 'active')
  const eligibleBySide = {
    away: activeAway.map((p) => ({ id: p.id, label: p.name })),
    home: activeHome.map((p) => ({ id: p.id, label: p.name })),
  }
  const names: Record<string, string> = {}
  const uniformNumbers: Record<string, string | null> = {}
  for (const entry of [...activeAway, ...activeHome]) {
    names[entry.id] = entry.name
    uniformNumbers[entry.id] = entry.uniform_number
  }
  return {
    tenantId,
    gameId,
    generation: read.game.current_d4,
    recoveryGeneration: read.game.recovery_generation,
    awayLineupId: read.game.lineups.away.lineup_id,
    homeLineupId: read.game.lineups.home.lineup_id,
    checkpoint: beforeRef,
    nextD1: safePosition(read.game.next_position.d1),
    nextD2: safePosition(read.game.next_position.d2),
    currentCount: {
      strikes: restored.current.stateFields['state.count.strikes'] as
        '0' | '1' | '2',
      balls: restored.current.stateFields['state.count.balls'] as
        '0' | '1' | '2' | '3',
    },
    state: state as SubstitutionState,
    eligibleBySide,
    names,
    uniformNumbers,
  }
}
