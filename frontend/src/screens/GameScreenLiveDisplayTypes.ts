/** 計算済み投影・生成formatterを画面へ渡すためのUI専用契約。正式Portではない。 */
export type DisplaySupply<T> = {
  scopeKey: string
  contextKey: string
  playerId?: string
  status: 'ready' | 'unavailable' | 'read-failed' | 'empty'
  value?: T
  /** 当日値の暫定性は提供側が決める。 */
  provisional?: boolean
  /** シーズン値の最終取得情報も提供側から受ける。 */
  offline?: boolean
  fetchedAt?: string | null
}

export interface LiveIdentity {
  scopeKey: string
  contextKey: string
  pitcherId: string
  currentBatterId: string
  nextBatterId: string
  pitcherName: string
  currentBatterName: string
  nextBatterName: string
}

export type InningCell =
  { kind: 'text'; text: string } | { kind: 'blank' } | { kind: 'unavailable' }

export interface Scoreboard {
  teams: readonly [
    {
      name: string
      total: string | null
      h: string | null
      e: string | null
      k: string | null
      b: string | null
    },
    {
      name: string
      total: string | null
      h: string | null
      e: string | null
      k: string | null
      b: string | null
    },
  ]
  /** 開始済みの全回。順序は投影のまま使う。 */
  innings: readonly {
    key: string
    label: string
    cells: readonly [InningCell, InningCell]
  }[]
}

export interface PitcherDay {
  pitchCount: string | null
  inningsPitched: string | null
  fastestSpeed: string | null
  averageSpeed: string | null
  hitsAllowed: string | null
  strikeouts: string | null
  walks: string | null
  runsAllowed: string | null
}

export interface PitcherSeason {
  vsLeftAverage: string | null
  vsRightAverage: string | null
  inningsPitched: string | null
  whip: string | null
  fip: string | null
}

export interface BatterDay {
  plateAppearances: string | null
  atBats: string | null
  hits: string | null
  rbi: string | null
  walks: string | null
  hitByPitch: string | null
  strikeouts: string | null
  sacrificeBunts: string | null
  sacrificeFlies: string | null
}

export interface BatterSeason {
  vsLeftAverage: string | null
  vsRightAverage: string | null
  homeRuns: string | null
}

export interface PlateAppearanceRow {
  key: string
  number: string
  inning: string
  resultName: string
  atBat: string
  hitType: string
  rbi: string
  onBaseType: string
}

export interface PitchTypeShare {
  key: string
  name: string
  share: string
  count: string
}

export interface GameFlow {
  inning: string | null
  battingOrder: string | null
  endState:
    | 'undetected'
    | 'detected'
    | 'declared-unsynced'
    | 'declared-synced'
    | 'reopened'
    | 'reclosed-unsynced'
    | 'reclosed-synced'
  promptRequired: boolean | null
  undoAllowed: boolean | null
  substitutionAllowed: boolean | null
}

export interface LiveDisplaySources {
  scoreboard?: DisplaySupply<Scoreboard>
  pitcherDay?: DisplaySupply<PitcherDay>
  pitcherSeason?: DisplaySupply<PitcherSeason>
  currentBatterDay?: DisplaySupply<BatterDay>
  currentBatterSeason?: DisplaySupply<BatterSeason>
  currentBatterHistory?: DisplaySupply<readonly PlateAppearanceRow[]>
  nextBatterDay?: DisplaySupply<BatterDay>
  nextBatterSeason?: DisplaySupply<BatterSeason>
  nextBatterHistory?: DisplaySupply<readonly PlateAppearanceRow[]>
  pitchTypes?: DisplaySupply<readonly PitchTypeShare[]>
  flow?: DisplaySupply<GameFlow>
  /** 正式鮮度契約から供給された表示文字列と状態のみを使う。 */
  viewerAppliedAt?: DisplaySupply<string>
  inputOffline?: DisplaySupply<boolean>
}
