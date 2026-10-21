/** 画面専用の供給要求。正式な交代・登録・回切替 wire 型ではない。 */
export interface SubstitutionChoice {
  id: string
  label: string
}

export interface SubstitutionQuestion {
  key: string
  label: string
  input: 'text' | 'choice'
  /** 必須性も供給側が決める。欠落時は要求を表示しない。 */
  required: boolean
  options?: readonly SubstitutionChoice[]
}

export type SubstitutionKind =
  'pitcher' | 'pinch-hitter' | 'pinch-runner' | 'defense'

export interface SubstitutionOperationSupply {
  kind: SubstitutionKind
  outgoing: readonly SubstitutionChoice[]
  incoming: readonly SubstitutionChoice[]
  /** その場登録は質問が供給された場合だけ入力できる。 */
  registrationQuestions: readonly SubstitutionQuestion[]
  /** 守備位置・DH等も供給された選択肢のまま表示する。 */
  placementQuestions: readonly SubstitutionQuestion[]
  questions: readonly SubstitutionQuestion[]
}

export interface SubstitutionRequest {
  contextKey: string
  operations: readonly SubstitutionOperationSupply[]
}

export interface TiebreakRequest {
  contextKey: string
  placementQuestions: readonly SubstitutionQuestion[]
  leadBatterQuestions: readonly SubstitutionQuestion[]
  inningQuestions: readonly SubstitutionQuestion[]
}

export interface PastSubstitutionRequest {
  contextKey: string
  /** 供給側がページングした一ページ。画面から全件取得しない。 */
  page: {
    label: string
    hasPrevious: boolean
    hasNext: boolean
    targets: readonly (SubstitutionChoice & { detail: string })[]
  }
  personQuestions: readonly SubstitutionQuestion[]
  inningQuestions: readonly SubstitutionQuestion[]
  timingQuestions: readonly SubstitutionQuestion[]
}

export interface SubstitutionDraftIdentity {
  contextKey: string
  uiInstanceId: string
  draftId: number
  operation: SubstitutionKind | 'tiebreak' | 'past-correction'
  targetId: string | null
}

/** 未選択は null。画面下書きであり、保存・送信・queue に渡さない。 */
export interface RawSubstitutionDraft {
  readonly identity: Readonly<SubstitutionDraftIdentity>
  readonly outgoingId: string | null
  readonly incomingMode: 'existing' | 'new' | null
  readonly incomingId: string | null
  readonly answers: Readonly<Record<string, string | null>>
}

/** 保存や操作要求ではない、画面から供給側へ渡す不変のUI下書き。 */
export interface SubstitutionDraftsSnapshot {
  readonly normal: RawSubstitutionDraft | null
  readonly tiebreak: RawSubstitutionDraft | null
  readonly past: RawSubstitutionDraft | null
}

/** 提供側の検証結果だけを描画する。画面では9位置や打順を判定しない。 */
export interface SubstitutionValidation {
  identity: SubstitutionDraftIdentity
  kind: 'pending' | 'failed' | 'invalid' | 'valid'
  messages?: readonly string[]
}

export interface SubstitutionPreviewRow {
  label: string
  before: string
  after: string
}

/** 下流帰属は提供側で計算した差分だけを受け取る。 */
export type PastSubstitutionPreview =
  | {
      identity: SubstitutionDraftIdentity
      kind: 'pending' | 'failed' | 'conflict'
    }
  | {
      identity: SubstitutionDraftIdentity
      kind: 'ready'
      rows: readonly SubstitutionPreviewRow[]
    }

/** 終了条件の判定結果とその文脈は提供側の状態。画面では判定しない。 */
export interface SubstitutionLockState {
  contextKey: string
  state:
    | 'unknown'
    | 'open'
    | 'ending-locked-undo-available'
    | 'ending-locked-undo-unavailable'
}
