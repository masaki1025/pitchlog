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
