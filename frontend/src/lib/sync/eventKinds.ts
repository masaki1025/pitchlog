// この表は docs/design/sync-protocol.md 5-5 の写しである。
// 値は実装で決めず、変更は正本の改訂ゲートを通すこと。
export const EVENT_PARTICIPATION = {
  LOGICAL_POSITION: '論理位置を持つ',
  SYNC_ORDER_ONLY: '同期順のみ',
  DEPENDENT: '従属',
  INHERIT_SOURCE: '元イベントの参加区分を継承',
} as const

export type EventParticipation =
  (typeof EVENT_PARTICIPATION)[keyof typeof EVENT_PARTICIPATION]

export const EVENT_KIND_GROUP = {
  A: 'A',
  B: 'B',
} as const

export type EventKindGroup =
  (typeof EVENT_KIND_GROUP)[keyof typeof EVENT_KIND_GROUP]

type EventKindDefinition = {
  id: string
  name: string
  participation: EventParticipation
  hasRevisionOrder: boolean
  group: EventKindGroup
}

export const EVENT_KIND_RULES = [
  {
    id: '1',
    name: '毎球入力',
    participation: EVENT_PARTICIPATION.LOGICAL_POSITION,
    hasRevisionOrder: false,
    group: EVENT_KIND_GROUP.A,
  },
  {
    id: '2',
    name: 'undo',
    participation: EVENT_PARTICIPATION.DEPENDENT,
    hasRevisionOrder: false,
    group: EVENT_KIND_GROUP.A,
  },
  {
    id: '3',
    name: '選手交代',
    participation: EVENT_PARTICIPATION.LOGICAL_POSITION,
    hasRevisionOrder: false,
    group: EVENT_KIND_GROUP.A,
  },
  {
    id: '4',
    name: 'タイブレーク開始',
    participation: EVENT_PARTICIPATION.LOGICAL_POSITION,
    hasRevisionOrder: false,
    group: EVENT_KIND_GROUP.A,
  },
  {
    id: '5',
    name: '試合終了宣言',
    participation: EVENT_PARTICIPATION.LOGICAL_POSITION,
    hasRevisionOrder: false,
    group: EVENT_KIND_GROUP.A,
  },
  {
    id: '6',
    name: '選手のその場登録',
    participation: EVENT_PARTICIPATION.SYNC_ORDER_ONLY,
    hasRevisionOrder: false,
    group: EVENT_KIND_GROUP.A,
  },
  {
    id: '7',
    name: '状態補正',
    participation: EVENT_PARTICIPATION.LOGICAL_POSITION,
    hasRevisionOrder: false,
    group: EVENT_KIND_GROUP.A,
  },
  {
    id: '8',
    name: '墓標',
    participation: EVENT_PARTICIPATION.SYNC_ORDER_ONLY,
    hasRevisionOrder: false,
    group: EVENT_KIND_GROUP.A,
  },
  {
    id: '9',
    name: '改訂版',
    participation: EVENT_PARTICIPATION.INHERIT_SOURCE,
    hasRevisionOrder: false,
    group: EVENT_KIND_GROUP.A,
  },
  {
    id: '10',
    name: 'プレイの修正',
    participation: EVENT_PARTICIPATION.DEPENDENT,
    hasRevisionOrder: true,
    group: EVENT_KIND_GROUP.B,
  },
  {
    id: '11',
    name: 'プレイ行の論理削除',
    participation: EVENT_PARTICIPATION.DEPENDENT,
    hasRevisionOrder: true,
    group: EVENT_KIND_GROUP.B,
  },
  {
    id: '12',
    name: '交代イベントの修正',
    participation: EVENT_PARTICIPATION.DEPENDENT,
    hasRevisionOrder: true,
    group: EVENT_KIND_GROUP.B,
  },
] as const satisfies readonly EventKindDefinition[]

export type EventKind = (typeof EVENT_KIND_RULES)[number]
export type EventKindId = EventKind['id']

export function buildSyncEventKindSet({
  stateCorrectionAdopted,
}: {
  stateCorrectionAdopted: boolean
}): readonly EventKind[] {
  return Object.freeze(
    EVENT_KIND_RULES.filter(
      (eventKind) => stateCorrectionAdopted || eventKind.id !== '7',
    ),
  )
}
