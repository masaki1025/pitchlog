// 固定原典のreadonly参照外殻4型のみ。Ready/真正性の証明ではない。
export type ContentRefV1 = Readonly<{ "contract_id": string; "contract_version": string; "content_sha256": string }>;
export type T1ReadKeyV1 = Readonly<{ "tenant_id": string; "game_id": string; "wire_d4": string; "internal_generation": number; "d1": number; "d5": string; "business_scope_id": string; "canonical_lineage_id": string }>;
export type T1ContextRefsV1 = Readonly<{ "key": T1ReadKeyV1; "rules": ContentRefV1; "roster": ContentRefV1; "pre_state": ContentRefV1; "effective_prefix": PrefixEvidenceRefV1 }>;
export type PrefixEvidenceRefV1 = Readonly<{ "snapshot_id": string; "canonical_lineage_id": string; "before_d1": number; "content_ref": ContentRefV1 }>;
