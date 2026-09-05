// この状態定義と保持契約は docs/design/sync-protocol.md 7-2 の写しである。
// 値は実装で決めず、変更は正本の改訂ゲートを通すこと。

export const QUEUE_ACTION_REQUIRED_LABELS = [
  { id: '改訂待ち' },
  { id: '墓標待ち' },
  { id: '管理者対応待ち' },
] as const

export type QueueActionRequiredLabel =
  (typeof QUEUE_ACTION_REQUIRED_LABELS)[number]

type QueueStateDefinition = Readonly<{
  id: string
  actionRequiredLabels: readonly QueueActionRequiredLabel[]
}>

export const QUEUE_STATES = [
  { id: '未送信', actionRequiredLabels: [] },
  { id: '要操作', actionRequiredLabels: QUEUE_ACTION_REQUIRED_LABELS },
  { id: '同期済み', actionRequiredLabels: [] },
  { id: '退避済み', actionRequiredLabels: [] },
] as const satisfies readonly QueueStateDefinition[]

export type QueueState = (typeof QUEUE_STATES)[number]
export type QueueStateId = QueueState['id']

export function queueStateId<Id extends QueueStateId>(id: Id): Id {
  if (!QUEUE_STATES.some((state) => state.id === id)) {
    throw new Error(`キュー状態 ID が存在しません: ${id}`)
  }
  return id
}

export function actionRequiredLabelId<
  Id extends QueueActionRequiredLabel['id'],
>(id: Id): Id {
  if (!QUEUE_ACTION_REQUIRED_LABELS.some((label) => label.id === id)) {
    throw new Error(`要操作の下位ラベル ID が存在しません: ${id}`)
  }
  return id
}

type I6HoldingContractElementDefinition = Readonly<{ id: string }>
type I6HoldingContractDefinition = Readonly<{
  id: string
  name: string
  elements: readonly I6HoldingContractElementDefinition[]
}>

export const I6_HOLDING_CONTRACT = {
  id: 'I6',
  name: 'P3受理結果の端末保持',
  elements: [
    { id: '端末永続化まで成立した対象参照' },
    { id: 'V11の版' },
    { id: 'D5' },
    { id: '確定内容' },
    { id: 'accepted_atを起点' },
    { id: '同期済みと同じ24時間保持' },
    { id: '保存済み結果の再掲で延長しない' },
    { id: 'サーバー確定から端末永続化まで保護なし' },
    { id: 'RG1中は自動破棄停止' },
    { id: '退避・閲覧・書き出し対象' },
    { id: '復元規則なし' },
  ],
} as const satisfies I6HoldingContractDefinition

export type I6HoldingContract = typeof I6_HOLDING_CONTRACT
export type I6HoldingContractElement = I6HoldingContract['elements'][number]
