/** 正式な履歴提供側が undo 自身を除外して選んだ直前の取消可能な操作。 */
export type UndoOffer = { contextKey: string } & (
  | { kind: 'unknown' }
  | { kind: 'none' }
  | { kind: 'available'; operationLabel: string; targetLabel: string }
)

/** 表示専用の提供状態。記録権・キュー・接続の判定を画面で行わない。 */
export interface CorrectionPrerequisites {
  writer: 'unknown' | 'held' | 'not-held'
  queue: 'unknown' | 'empty' | 'not-empty'
  connection: 'unknown' | 'online' | 'offline'
}

export type CorrectionOperation = 'modify' | 'insert' | 'delete'

export interface CorrectionQuestion {
  key: string
  label: string
  input: 'text' | 'choice'
  options?: readonly { id: string; label: string }[]
}

export interface CorrectionTarget {
  id: string
  label: string
  detail: string
}

/** 供給側でページングした一ページだけを受け取る。画面は全件取得しない。 */
export interface CorrectionRequest {
  contextKey: string
  page: {
    label: string
    targets: readonly CorrectionTarget[]
    hasPrevious: boolean
    hasNext: boolean
  }
  questions: Readonly<
    Record<CorrectionOperation, readonly CorrectionQuestion[]>
  >
}

/** 画面内だけの照合値。正式なイベント・同期ID・通信DTOではない。 */
export interface CorrectionDraftIdentity {
  contextKey: string
  uiInstanceId: string
  draftId: number
  targetId: string
  operation: CorrectionOperation
}

export interface CorrectionDraft {
  identity: CorrectionDraftIdentity
  answers: Readonly<Record<string, string | null>>
}

export interface CorrectionDiffRow {
  label: string
  before: string
  after: string
}

/** サーバー供給の結果だけを表示する。失敗の内部原因は表示しない。 */
export type CorrectionPreview =
  | {
      identity: CorrectionDraftIdentity
      kind: 'pending' | 'failed' | 'conflict'
    }
  | {
      identity: CorrectionDraftIdentity
      kind: 'ready'
      rows: readonly CorrectionDiffRow[]
    }
