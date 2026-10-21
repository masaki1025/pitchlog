import type {
  BatterDay,
  BatterSeason,
  DisplaySupply,
  GameFlow,
  InningCell,
  LiveDisplaySources,
  LiveIdentity,
  PitcherDay,
  PitcherSeason,
  PitchTypeShare,
  PlateAppearanceRow,
  Scoreboard,
} from './GameScreenLiveDisplayTypes'

// 描画が読む値だけを一度取得して複製する。正式wireや計算結果の検証ではない。
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function nonEmpty(value: unknown): value is string {
  return typeof value === 'string' && value !== ''
}

function displayValue(value: unknown): value is string | null {
  return value === null || nonEmpty(value)
}

// 穴と余分な非添字keyを混同せず、表示対象の各添字を一度だけ読む。
function denseMap<T>(
  value: unknown,
  parse: (item: unknown) => T | undefined,
): T[] | undefined {
  if (!Array.isArray(value)) return undefined
  const length = value.length
  const ownIndices = Reflect.ownKeys(value).filter((key) => {
    if (typeof key !== 'string') return false
    const index = Number(key)
    return (
      Number.isSafeInteger(index) &&
      index >= 0 &&
      index < length &&
      String(index) === key
    )
  })
  if (ownIndices.length !== length) return undefined
  const result: T[] = []
  for (let index = 0; index < length; index += 1) {
    if (!Object.hasOwn(value, index)) return undefined
    const item = parse(value[index])
    if (item === undefined) return undefined
    result.push(item)
  }
  return result
}

function copyFields<T>(value: unknown, keys: readonly string[]): T | undefined {
  if (!record(value)) return undefined
  const copy: Record<string, string | null> = Object.create(null)
  for (const key of keys) {
    const field = value[key]
    if (!displayValue(field)) return undefined
    copy[key] = field
  }
  return copy as T
}

function copyCell(value: unknown): InningCell | undefined {
  if (!record(value)) return undefined
  const kind = value.kind
  if (kind === 'blank' || kind === 'unavailable') return { kind }
  if (kind !== 'text') return undefined
  const text = value.text
  return nonEmpty(text) ? { kind, text } : undefined
}

function copyTeam(value: unknown): Scoreboard['teams'][number] | undefined {
  if (!record(value)) return undefined
  const name = value.name
  const totals = copyFields<
    Pick<Scoreboard['teams'][number], 'total' | 'h' | 'e' | 'k' | 'b'>
  >(value, ['total', 'h', 'e', 'k', 'b'])
  return nonEmpty(name) && totals ? { name, ...totals } : undefined
}

function copyInning(value: unknown): Scoreboard['innings'][number] | undefined {
  if (!record(value)) return undefined
  const key = value.key
  const label = value.label
  const cells = denseMap(value.cells, copyCell)
  return nonEmpty(key) && nonEmpty(label) && cells?.length === 2
    ? {
        key,
        label,
        cells: cells as unknown as readonly [InningCell, InningCell],
      }
    : undefined
}

function copyScoreboard(value: unknown): Scoreboard | undefined {
  if (!record(value)) return undefined
  const teams = denseMap(value.teams, copyTeam)
  const innings = denseMap(value.innings, copyInning)
  if (!teams || teams.length !== 2 || !innings) return undefined
  if (new Set(innings.map((inning) => inning.key)).size !== innings.length)
    return undefined
  return { teams: teams as unknown as Scoreboard['teams'], innings }
}

const pitcherDayKeys = [
  'pitchCount',
  'inningsPitched',
  'fastestSpeed',
  'averageSpeed',
  'hitsAllowed',
  'strikeouts',
  'walks',
  'runsAllowed',
]
const pitcherSeasonKeys = [
  'vsLeftAverage',
  'vsRightAverage',
  'inningsPitched',
  'whip',
  'fip',
]
const batterDayKeys = [
  'plateAppearances',
  'atBats',
  'hits',
  'rbi',
  'walks',
  'hitByPitch',
  'strikeouts',
  'sacrificeBunts',
  'sacrificeFlies',
]
const batterSeasonKeys = ['vsLeftAverage', 'vsRightAverage', 'homeRuns']

function copySeason<T extends PitcherSeason | BatterSeason>(
  value: unknown,
  keys: readonly string[],
): T | undefined {
  if (!record(value)) return undefined
  const periodLabel = value.periodLabel
  const fields = copyFields<Omit<T, 'periodLabel'>>(value, keys)
  return nonEmpty(periodLabel) && fields
    ? ({ ...fields, periodLabel } as T)
    : undefined
}

function copyHistoryRow(value: unknown): PlateAppearanceRow | undefined {
  if (!record(value)) return undefined
  const keys = [
    'key',
    'number',
    'inning',
    'resultName',
    'atBat',
    'hitType',
    'rbi',
    'onBaseType',
  ] as const
  const copy: Record<string, string> = Object.create(null)
  for (const key of keys) {
    const field = value[key]
    if (!nonEmpty(field)) return undefined
    copy[key] = field
  }
  return copy as unknown as PlateAppearanceRow
}
function copyHistory(
  value: unknown,
): readonly PlateAppearanceRow[] | undefined {
  const rows = denseMap(value, copyHistoryRow)
  return rows && new Set(rows.map((row) => row.key)).size === rows.length
    ? rows
    : undefined
}

function copyPitchType(value: unknown): PitchTypeShare | undefined {
  if (!record(value)) return undefined
  const keys = ['key', 'name', 'share', 'count'] as const
  const copy: Record<string, string> = Object.create(null)
  for (const key of keys) {
    const field = value[key]
    if (!nonEmpty(field)) return undefined
    copy[key] = field
  }
  return copy as unknown as PitchTypeShare
}
function copyPitchTypes(value: unknown): readonly PitchTypeShare[] | undefined {
  const rows = denseMap(value, copyPitchType)
  return rows && new Set(rows.map((row) => row.key)).size === rows.length
    ? rows
    : undefined
}

const endStates = new Set<GameFlow['endState']>([
  'undetected',
  'detected',
  'declared-unsynced',
  'declared-synced',
  'reopened',
  'reclosed-unsynced',
  'reclosed-synced',
])
function flag(value: unknown): value is boolean | null {
  return value === true || value === false || value === null
}
function copyFlow(value: unknown): GameFlow | undefined {
  if (!record(value)) return undefined
  const inning = value.inning
  const battingOrder = value.battingOrder
  const endState = value.endState
  const promptRequired = value.promptRequired
  const undoAllowed = value.undoAllowed
  const substitutionAllowed = value.substitutionAllowed
  if (
    !displayValue(inning) ||
    !displayValue(battingOrder) ||
    typeof endState !== 'string' ||
    !endStates.has(endState as GameFlow['endState']) ||
    !flag(promptRequired) ||
    !flag(undoAllowed) ||
    !flag(substitutionAllowed)
  )
    return undefined
  return {
    inning,
    battingOrder,
    endState: endState as GameFlow['endState'],
    promptRequired,
    undoAllowed,
    substitutionAllowed,
  }
}

function copyBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined
}
function copyString(value: unknown): string | undefined {
  return nonEmpty(value) ? value : undefined
}

function snapshotSupply<T>(
  value: unknown,
  parse: (value: unknown) => T | undefined,
  season = false,
): DisplaySupply<T> | undefined {
  try {
    if (!record(value)) return undefined
    const scopeKey = value.scopeKey
    const contextKey = value.contextKey
    const playerId = value.playerId
    const status = value.status
    const provisional = value.provisional
    const offline = value.offline
    const fetchedAt = value.fetchedAt
    if (
      !nonEmpty(scopeKey) ||
      !nonEmpty(contextKey) ||
      (playerId !== undefined && !nonEmpty(playerId)) ||
      (provisional !== undefined && typeof provisional !== 'boolean') ||
      (offline !== undefined && typeof offline !== 'boolean') ||
      (fetchedAt !== undefined &&
        fetchedAt !== null &&
        typeof fetchedAt !== 'string') ||
      (status !== 'ready' &&
        status !== 'unavailable' &&
        status !== 'read-failed' &&
        status !== 'empty')
    )
      return undefined
    if (
      season &&
      status === 'ready' &&
      offline === true &&
      (typeof fetchedAt !== 'string' || fetchedAt.trim() === '')
    ) {
      // 断中の最終取得時刻がないシーズン値は表示せず未取得へ倒す。
      return {
        scopeKey,
        contextKey,
        status: 'unavailable',
        ...(playerId !== undefined && { playerId }),
        offline: true,
      }
    }
    const snapshot: DisplaySupply<T> = {
      scopeKey,
      contextKey,
      status,
      ...(playerId !== undefined && { playerId }),
      ...(provisional !== undefined && { provisional }),
      ...(offline !== undefined && { offline }),
      ...(fetchedAt !== undefined && { fetchedAt }),
    }
    if (status === 'ready') {
      const parsed = parse(value.value)
      if (parsed === undefined) return undefined
      snapshot.value = parsed
    }
    return snapshot
  } catch {
    // 例外を投げるgetterは当該表示値だけ未取得へ倒す。
    return undefined
  }
}

function sourceField(sources: Record<string, unknown>, key: string): unknown {
  try {
    return sources[key]
  } catch {
    return undefined
  }
}

export function snapshotLiveIdentity(value: unknown): LiveIdentity | null {
  try {
    if (!record(value)) return null
    const scopeKey = value.scopeKey
    const contextKey = value.contextKey
    const pitcherId = value.pitcherId
    const currentBatterId = value.currentBatterId
    const nextBatterId = value.nextBatterId
    const pitcherName = value.pitcherName
    const currentBatterName = value.currentBatterName
    const nextBatterName = value.nextBatterName
    if (!nonEmpty(scopeKey) || !nonEmpty(contextKey)) return null
    return {
      scopeKey,
      contextKey,
      pitcherId: nonEmpty(pitcherId) ? pitcherId : '',
      currentBatterId: nonEmpty(currentBatterId) ? currentBatterId : '',
      nextBatterId: nonEmpty(nextBatterId) ? nextBatterId : '',
      pitcherName: nonEmpty(pitcherName) ? pitcherName : '',
      currentBatterName: nonEmpty(currentBatterName) ? currentBatterName : '',
      nextBatterName: nonEmpty(nextBatterName) ? nextBatterName : '',
    }
  } catch {
    return null
  }
}

export function safeLiveSources(sources: unknown): LiveDisplaySources {
  try {
    if (!record(sources)) return {}
    return {
      scoreboard: snapshotSupply(
        sourceField(sources, 'scoreboard'),
        copyScoreboard,
      ),
      pitcherDay: snapshotSupply(sourceField(sources, 'pitcherDay'), (value) =>
        copyFields<PitcherDay>(value, pitcherDayKeys),
      ),
      pitcherSeason: snapshotSupply(
        sourceField(sources, 'pitcherSeason'),
        (value) => copySeason<PitcherSeason>(value, pitcherSeasonKeys),
        true,
      ),
      currentBatterDay: snapshotSupply(
        sourceField(sources, 'currentBatterDay'),
        (value) => copyFields<BatterDay>(value, batterDayKeys),
      ),
      currentBatterSeason: snapshotSupply(
        sourceField(sources, 'currentBatterSeason'),
        (value) => copySeason<BatterSeason>(value, batterSeasonKeys),
        true,
      ),
      currentBatterHistory: snapshotSupply(
        sourceField(sources, 'currentBatterHistory'),
        copyHistory,
      ),
      nextBatterDay: snapshotSupply(
        sourceField(sources, 'nextBatterDay'),
        (value) => copyFields<BatterDay>(value, batterDayKeys),
      ),
      nextBatterSeason: snapshotSupply(
        sourceField(sources, 'nextBatterSeason'),
        (value) => copySeason<BatterSeason>(value, batterSeasonKeys),
        true,
      ),
      nextBatterHistory: snapshotSupply(
        sourceField(sources, 'nextBatterHistory'),
        copyHistory,
      ),
      pitchTypes: snapshotSupply(
        sourceField(sources, 'pitchTypes'),
        copyPitchTypes,
      ),
      flow: snapshotSupply(sourceField(sources, 'flow'), copyFlow),
      viewerAppliedAt: snapshotSupply(
        sourceField(sources, 'viewerAppliedAt'),
        copyString,
      ),
      inputOffline: snapshotSupply(
        sourceField(sources, 'inputOffline'),
        copyBoolean,
      ),
    }
  } catch {
    return {}
  }
}
