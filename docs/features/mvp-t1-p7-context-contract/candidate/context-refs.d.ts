/**
 * US1固定外殻4定義に対応する、局所候補のreadonly宣言。
 * UUID・非空・digest・正整数・余剰field拒否は実行時の構造検査が必要。
 * readonlyは静的制約であり、実値の凍結・真正性・完全性を保証しない。
 * numberは外殻integerの静的対応だけを表す。整数の実行時表現、精度、
 * BigInt/十進文字列ABIやドメイン演算を決定する宣言ではない。
 * 正式型・製品ABI・T1/P7完了の宣言ではない。
 */
export interface ContentRefV1 {
  readonly contract_id: string;
  readonly contract_version: string;
  readonly content_sha256: string;
}

export interface T1ReadKeyV1 {
  readonly tenant_id: string;
  readonly game_id: string;
  readonly wire_d4: string;
  readonly internal_generation: number;
  readonly d1: number;
  readonly d5: string;
  readonly business_scope_id: string;
  readonly canonical_lineage_id: string;
}

export interface PrefixEvidenceRefV1 {
  readonly snapshot_id: string;
  readonly canonical_lineage_id: string;
  readonly before_d1: number;
  readonly content_ref: ContentRefV1;
}

export interface T1ContextRefsV1 {
  readonly key: T1ReadKeyV1;
  readonly rules: ContentRefV1;
  readonly roster: ContentRefV1;
  readonly pre_state: ContentRefV1;
  readonly effective_prefix: PrefixEvidenceRefV1;
}
/** 後続の閉構造候補。unresolvedは未受理の意味/出所を表し、Readyへ変換できない。 */
export type PlayerRefV1 = ({ readonly kind: "official"; readonly player_id: string; } | { readonly kind: "temporary"; readonly temporary_id: string; });

export type ScorerRefV1 = ({ readonly kind: "runner"; readonly runner_id: PlayerRefV1; } | { readonly kind: "batter"; readonly batter_id: PlayerRefV1; });

export type HomeTouchOrderV1 = ({ readonly kind: "not-required"; } | { readonly kind: "observed"; readonly scorers: ReadonlyArray<ScorerRefV1>; });

export type T1EventRefV1 = { readonly event_id: string; readonly record_version: number; };

export type T1ContextPointV1 = { readonly key: T1ReadKeyV1; readonly content_ref: ContentRefV1; readonly content_version: string; };

export type T1HalfRefV1 = { readonly inning: number; readonly side: ("top" | "bottom"); };

export type T1BattingSlotV1 = ({ readonly kind: "none"; } | { readonly kind: "slot"; readonly slot: number; });

export type T1FieldingRoleV1 = ({ readonly kind: "fielding"; readonly position: number; } | { readonly kind: "designated-hitter"; });

export type T1RosterEntryOriginV1 = ({ readonly kind: "initial"; } | { readonly kind: "substitution"; readonly event: T1EventRefV1; readonly replaced_player: PlayerRefV1; });

export type T1RosterEntryV1 = { readonly player: PlayerRefV1; readonly batting_slot: T1BattingSlotV1; readonly roles: ReadonlyArray<T1FieldingRoleV1>; readonly entry_origin: T1RosterEntryOriginV1; };

export type T1TeamRosterV1 = { readonly team_id: string; readonly side: ("away" | "home"); readonly participants: ReadonlyArray<T1RosterEntryV1>; };

export type T1RosterAtEventV1 = { readonly point: T1ContextPointV1; readonly teams: ReadonlyArray<T1TeamRosterV1>; };

export type T1BaseOccupantV1 = ({ readonly kind: "empty"; } | { readonly kind: "occupied"; readonly player: PlayerRefV1; });

export type T1HalfApplicationMarkV1 = { readonly half: T1HalfRefV1; readonly event: T1EventRefV1; readonly application: { readonly kind: "unresolved"; readonly obligation: "half-application-mark"; readonly source: ContentRefV1; }; };

export type T1PreStateV1 = { readonly point: T1ContextPointV1; readonly roster_version: string; readonly inning: number; readonly half: ("top" | "bottom"); readonly outs: (0 | 1 | 2); readonly count: { readonly strikes: (0 | 1 | 2); readonly balls: (0 | 1 | 2 | 3); }; readonly runners: { readonly first: T1BaseOccupantV1; readonly second: T1BaseOccupantV1; readonly third: T1BaseOccupantV1; }; readonly score: { readonly away: number; readonly home: number; }; readonly batting_order: number; readonly batter: PlayerRefV1; readonly tiebreak_active: boolean; readonly game_ended: boolean; readonly half_application_marks: ReadonlyArray<T1HalfApplicationMarkV1>; readonly canonical_membership: { readonly kind: "unresolved"; readonly obligation: "canonical-membership"; readonly source: ContentRefV1; }; };

export type T1QueuedSourceV1 = { readonly kind: "queued"; readonly wire_d4: string; readonly internal_generation: number; readonly d1: number; readonly d5: string; };

export type T1ChangeSourceV1 = { readonly kind: "online-change"; readonly change: { readonly kind: "unresolved"; readonly obligation: "online-change-source"; readonly source: ContentRefV1; }; };

export type T1ReplayParticipationV1 = ({ readonly kind: "own-d2"; readonly d2: number; } | { readonly kind: "dependent"; readonly target: T1EventRefV1; } | { readonly kind: "sync-only"; });

export type T1EffectiveEntryV1 = { readonly event: T1EventRefV1; readonly source: (T1QueuedSourceV1 | T1ChangeSourceV1); readonly operation_kind: ("per-pitch" | "undo" | "substitution" | "tiebreak-start" | "game-end-declaration" | "adhoc-registration" | "play-change" | "play-delete" | "substitution-change"); readonly participation: T1ReplayParticipationV1; readonly content: { readonly kind: "unresolved"; readonly obligation: "operation-content"; readonly source: ContentRefV1; }; readonly canonical_membership: { readonly kind: "unresolved"; readonly obligation: "canonical-membership"; readonly source: ContentRefV1; }; readonly version_relation: ({ readonly kind: "original"; } | { readonly kind: "revision"; readonly replaces: T1EventRefV1; } | { readonly kind: "tombstone"; readonly replaces: T1EventRefV1; }); };

export type T1TemporaryOriginV1 = { readonly mapping_id: string; readonly temporary_id: string; readonly player_id: string; readonly origin_game_id: string; readonly origin_internal_generation: number; readonly origin_d1: number; readonly origin_d5: string; readonly origin_ledger_kind: "accepted"; readonly origin_source_fingerprint: string; readonly origin_record_version: 1; };

export type T1PrefixCursorV1 = ({ readonly kind: "start"; } | { readonly kind: "continue"; readonly cursor_id: string; });

export type T1PrefixNextCursorV1 = ({ readonly kind: "end"; } | { readonly kind: "continue"; readonly cursor_id: string; });

export type T1PrefixPageDescriptorV1 = { readonly page_index: number; readonly cursor: T1PrefixCursorV1; readonly next_cursor: T1PrefixNextCursorV1; readonly page_ref: ContentRefV1; };

export type T1PrefixPageV1 = { readonly key: T1ReadKeyV1; readonly prefix: PrefixEvidenceRefV1; readonly content_version: string; readonly descriptor: T1PrefixPageDescriptorV1; readonly entries: ReadonlyArray<T1EffectiveEntryV1>; readonly origins: ReadonlyArray<T1TemporaryOriginV1>; };

export type T1PrefixManifestV1 = { readonly key: T1ReadKeyV1; readonly prefix: PrefixEvidenceRefV1; readonly content_version: string; readonly pages: ReadonlyArray<T1PrefixPageDescriptorV1>; readonly selection_evidence: { readonly kind: "unresolved"; readonly obligation: "prefix-selection"; readonly source: ContentRefV1; }; readonly terminal_evidence: { readonly kind: "unresolved"; readonly obligation: "prefix-terminal"; readonly source: ContentRefV1; }; };

export type T1EffectivePrefixV1 = { readonly point: T1ContextPointV1; readonly prefix: PrefixEvidenceRefV1; readonly pages: ReadonlyArray<T1PrefixPageV1>; readonly manifest: T1PrefixManifestV1; readonly replay_window: { readonly kind: "unresolved"; readonly obligation: "undo-replay-diff"; readonly source: ContentRefV1; }; };
