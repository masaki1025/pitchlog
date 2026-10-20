import type {
  BatterDay,
  BatterSeason,
  DisplaySupply,
  GameFlow,
  InningCell,
  LiveDisplaySources,
  PitcherDay,
  PitcherSeason,
  PitchTypeShare,
  PlateAppearanceRow,
  Scoreboard,
} from './GameScreenLiveDisplayTypes'

// 描画が読む形だけを調べる。正式wireや成績・終了条件の検証ではない。
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function displayValue(value: unknown): value is string | null {
  return typeof value === 'string' || value === null
}

function fields(value: unknown, keys: readonly string[]): boolean {
  return record(value) && keys.every((key) => displayValue(value[key]))
}

// extraキーの個数で穴を埋められないよう、添字だけを数えた後に各own添字を調べる。
function denseArray<T>(
  value: unknown,
  item: (value: unknown) => value is T,
): value is T[] {
  if (!Array.isArray(value)) return false
  const ownIndices = Reflect.ownKeys(value).filter((key) => {
    if (typeof key !== 'string') return false
    const index = Number(key)
    return (
      Number.isSafeInteger(index) &&
      index >= 0 &&
      index < value.length &&
      String(index) === key
    )
  })
  if (ownIndices.length !== value.length) return false
  for (let index = 0; index < value.length; index += 1) {
    if (!Object.hasOwn(value, index) || !item(value[index])) return false
  }
  return true
}

function cell(value: unknown): value is InningCell {
  return (
    record(value) &&
    ((value.kind === 'text' && typeof value.text === 'string') ||
      value.kind === 'blank' ||
      value.kind === 'unavailable')
  )
}

function scoreboard(value: unknown): value is Scoreboard {
  if (!record(value)) return false
  const teams = value.teams
  const innings = value.innings
  if (
    !denseArray(
      teams,
      (team): team is Scoreboard['teams'][number] =>
        fields(team, ['total', 'h', 'e', 'k', 'b']) &&
        record(team) &&
        typeof team.name === 'string',
    ) ||
    teams.length !== 2
  )
    return false
  if (
    !denseArray(
      innings,
      (inning): inning is Scoreboard['innings'][number] =>
        record(inning) &&
        typeof inning.key === 'string' &&
        inning.key !== '' &&
        typeof inning.label === 'string' &&
        denseArray(inning.cells, cell) &&
        inning.cells.length === 2,
    )
  )
    return false
  return new Set(innings.map((inning) => inning.key)).size === innings.length
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

function pitcherDay(value: unknown): value is PitcherDay {
  return fields(value, pitcherDayKeys)
}
function pitcherSeason(value: unknown): value is PitcherSeason {
  return fields(value, pitcherSeasonKeys)
}
function batterDay(value: unknown): value is BatterDay {
  return fields(value, batterDayKeys)
}
function batterSeason(value: unknown): value is BatterSeason {
  return fields(value, batterSeasonKeys)
}

function historyRow(value: unknown): value is PlateAppearanceRow {
  return (
    record(value) &&
    typeof value.key === 'string' &&
    value.key !== '' &&
    [
      'number',
      'inning',
      'resultName',
      'atBat',
      'hitType',
      'rbi',
      'onBaseType',
    ].every((key) => typeof value[key] === 'string')
  )
}
function history(value: unknown): value is readonly PlateAppearanceRow[] {
  return (
    denseArray(value, historyRow) &&
    new Set(value.map((row) => row.key)).size === value.length
  )
}

function pitchType(value: unknown): value is PitchTypeShare {
  return (
    record(value) &&
    typeof value.key === 'string' &&
    value.key !== '' &&
    ['name', 'share', 'count'].every((key) => typeof value[key] === 'string')
  )
}
function pitchTypes(value: unknown): value is readonly PitchTypeShare[] {
  return (
    denseArray(value, pitchType) &&
    new Set(value.map((pitch) => pitch.key)).size === value.length
  )
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
function flow(value: unknown): value is GameFlow {
  return (
    record(value) &&
    displayValue(value.inning) &&
    displayValue(value.battingOrder) &&
    typeof value.endState === 'string' &&
    endStates.has(value.endState as GameFlow['endState']) &&
    flag(value.promptRequired) &&
    flag(value.undoAllowed) &&
    flag(value.substitutionAllowed)
  )
}
function suppliedString(value: unknown): value is string {
  return typeof value === 'string' && value !== ''
}
function suppliedBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean'
}

function safeSupply<T>(
  supply: unknown,
  valid: (value: unknown) => value is T,
): DisplaySupply<T> | undefined {
  try {
    if (!record(supply)) return undefined
    if (
      typeof supply.scopeKey !== 'string' ||
      supply.scopeKey === '' ||
      typeof supply.contextKey !== 'string' ||
      supply.contextKey === '' ||
      (supply.playerId !== undefined && typeof supply.playerId !== 'string') ||
      (supply.provisional !== undefined &&
        typeof supply.provisional !== 'boolean') ||
      (supply.offline !== undefined && typeof supply.offline !== 'boolean') ||
      (supply.fetchedAt !== undefined && !displayValue(supply.fetchedAt))
    )
      return undefined
    if (
      supply.status !== 'ready' &&
      supply.status !== 'unavailable' &&
      supply.status !== 'read-failed' &&
      supply.status !== 'empty'
    )
      return undefined
    if (supply.status === 'ready' && !valid(supply.value)) return undefined
    return supply as DisplaySupply<T>
  } catch {
    // 壊れた表示供給では画面を落とさず未取得へ縮退する。
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

export function safeLiveSources(sources: unknown): LiveDisplaySources {
  if (!record(sources)) return {}
  return {
    scoreboard: safeSupply(sourceField(sources, 'scoreboard'), scoreboard),
    pitcherDay: safeSupply(sourceField(sources, 'pitcherDay'), pitcherDay),
    pitcherSeason: safeSupply(
      sourceField(sources, 'pitcherSeason'),
      pitcherSeason,
    ),
    currentBatterDay: safeSupply(
      sourceField(sources, 'currentBatterDay'),
      batterDay,
    ),
    currentBatterSeason: safeSupply(
      sourceField(sources, 'currentBatterSeason'),
      batterSeason,
    ),
    currentBatterHistory: safeSupply(
      sourceField(sources, 'currentBatterHistory'),
      history,
    ),
    nextBatterDay: safeSupply(sourceField(sources, 'nextBatterDay'), batterDay),
    nextBatterSeason: safeSupply(
      sourceField(sources, 'nextBatterSeason'),
      batterSeason,
    ),
    nextBatterHistory: safeSupply(
      sourceField(sources, 'nextBatterHistory'),
      history,
    ),
    pitchTypes: safeSupply(sourceField(sources, 'pitchTypes'), pitchTypes),
    flow: safeSupply(sourceField(sources, 'flow'), flow),
    viewerAppliedAt: safeSupply(
      sourceField(sources, 'viewerAppliedAt'),
      suppliedString,
    ),
    inputOffline: safeSupply(
      sourceField(sources, 'inputOffline'),
      suppliedBoolean,
    ),
  }
}
