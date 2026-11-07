"""P3 有効 slot 版だけを非play原本 reader へ接ぐ候補 SQL。"""

from pitchlog.authz.game_lifecycle_sql import _bind as _lifecycle_bind
from pitchlog.authz.game_lifecycle_sql import (
    candidate_function_bodies as lifecycle_function_bodies,
)
from pitchlog.authz.nonplay_prefix_read_sql import candidate_read_function_bodies
from pitchlog.authz.nonplay_prefix_sql import (
    _active_evidence_query,
    _saved_evidence_sql,
    candidate_function_bodies,
)
from pitchlog.authz.stats_primitive_sql import _ROOT, _verified_inputs

_P3_SLOT_PROOF = """EXISTS(
 SELECT 1 FROM sync_fence.p3_projection_heads ph
 JOIN sync_fence.p3_projection_capsules pc ON
 (pc.tenant_id,pc.game_id,pc.internal_generation,pc.id)=
 (ph.tenant_id,ph.game_id,ph.internal_generation,ph.capsule_id)
 JOIN sync_fence.p3_projection_capsule_items pi ON
 (pi.tenant_id,pi.game_id,pi.internal_generation,pi.capsule_id,pi.d1)=
 (pc.tenant_id,pc.game_id,pc.internal_generation,pc.id,e.d1)
 JOIN sync_fence.p3_projection_write_admissions pa ON
 (pa.tenant_id,pa.game_id,pa.internal_generation,pa.capsule_id)=
 (pc.tenant_id,pc.game_id,pc.internal_generation,pc.id)
 JOIN public.operation_events ce ON
 (ce.tenant_id,ce.game_id,ce.id)=(pc.tenant_id,pc.game_id,pc.change_event_id)
 JOIN public.idempotency_ledger cl ON
 (cl.tenant_id,cl.d5)=(ce.tenant_id,ce.d5)
 JOIN public.play_rows ep ON
 (ep.tenant_id,ep.game_id,ep.id)=
 (pi.tenant_id,pi.game_id,pi.effective_play_row_id)
 WHERE (ph.tenant_id,ph.game_id,ph.internal_generation)=
 (e.tenant_id,e.game_id,e.generation)
 AND pc.target_d1=e.d1 AND pc.expected_version=1
 AND pc.next_checkpoint_id=c.id AND pc.watermark>=e.d1
 AND ph.source_set_digest=pc.source_set_digest
 AND ph.stats_version_id=pc.stats_version_id
 AND pi.state='corrected' AND pi.original_event_id=e.id
 AND pi.original_play_row_id=pr.id AND pi.effective_event_id=ce.id
 AND pi.original_payload=e.payload AND pi.original_history_entry=h.entry
 AND pi.original_play_row=pg_catalog.to_jsonb(pr)
 AND pi.original_play_runners=(SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=pr.tenant_id
 AND rr.play_id=pr.id)
 AND pi.play_row=pg_catalog.to_jsonb(ep)
 AND pa.state='consumed' AND pa.play_row_id=ep.id
 AND pa.change_event_id=ce.id AND pa.ledger_fingerprint=cl.source_fingerprint
 AND pa.expected_play_row=pg_catalog.to_jsonb(ep)
 AND pa.transaction_id ~ '^[1-9][0-9]{0,19}$'
 AND pa.xmin::text::numeric=
 pg_catalog.mod(pa.transaction_id::numeric,4294967296::numeric)
 AND ce.event_kind='play_change' AND ce.ledger_kind='accepted'
 AND ce.target_generation=e.generation AND ce.target_d1=e.d1
 AND ce.expected_version=pc.expected_version AND ce.d5=pc.d5
 AND ce.replaced_at IS NULL AND ce.retired_at IS NULL
 AND NOT ce.is_tombstone AND ce.import_batch_id IS NULL
 AND NOT ce.migration_unverified
 AND cl.kind='accepted' AND cl.retired_at IS NULL
 AND cl.import_batch_id IS NULL AND cl.source_fingerprint=pa.ledger_fingerprint
 AND ep.source_event_id=ce.id AND ep.hidden_at IS NULL
 AND ep.import_batch_id IS NULL AND NOT ep.migration_unverified
 AND es.confirmed_version=pc.expected_version+1
 AND es.xmin=pa.xmin AND ce.xmin=pa.xmin
 AND ep.xmin=pa.xmin AND pc.xmin=pa.xmin AND pi.xmin=pa.xmin
 AND ph.xmin=pa.xmin)"""


def _p3_active_evidence_query() -> str:
    """旧証明式の slot 版分岐だけを置換し、元原本の条件を保つ。"""
    original = _active_evidence_query()
    proof = _saved_evidence_sql("a", history=True)
    if original.count(proof) != 1:
        raise ValueError("非play証明式の位置が一意ではありません")
    version = "AND es.generation=e.generation AND es.d1=e.d1 AND es.confirmed_version=1"
    xmin = "AND es.xmin=a.xmin"
    if proof.count(version) != 1 or proof.count(xmin) != 1:
        raise ValueError("非play slot 証明式が変更されました")
    changed = proof.replace(
        version,
        "AND es.generation=e.generation AND es.d1=e.d1 "
        "AND es.confirmed_version IN (1,2)",
        1,
    ).replace(
        xmin,
        "AND ((es.confirmed_version=1 AND es.xmin=a.xmin) "
        f"OR (es.confirmed_version=2 AND {_P3_SLOT_PROOF}))",
        1,
    )
    return original.replace(proof, changed, 1)


def candidate_function_bodies_p3_nonplay_bridge() -> dict[str, str]:
    """0048 候補として既関数二件の P3 版だけを返す。"""
    original = _active_evidence_query()
    changed = _p3_active_evidence_query()
    if changed == original:
        raise ValueError("P3 slot 証明式が適用されませんでした")
    writer = candidate_function_bodies()["read_nonplay_history_page"]
    reader = candidate_read_function_bodies()["read_nonplay_active_history"]
    read_query = original.replace("stamp.internal_generation", "p_generation")
    changed_read_query = changed.replace("stamp.internal_generation", "p_generation")
    if writer.count(original) != 1 or reader.count(read_query) != 6:
        raise ValueError("非play関数本文の引用数が変更されました")
    return {
        "read_nonplay_history_page": writer.replace(original, changed, 1),
        "read_nonplay_active_history": reader.replace(read_query, changed_read_query),
    }


def candidate_lifecycle_p3_body(health_sql: str, members_sql: str) -> str:
    """唯一生成Sの現行P3 selectorだけを終了consumeへ接続する。"""
    if (
        type(health_sql) is not str
        or type(members_sql) is not str
        or "sync_fence.p3_projection_heads p3h" not in health_sql
        or "sync_fence.p3_projection_capsule_items p3i" not in health_sql
        or "sync_fence.p3_projection_heads p3h" not in members_sql
        or "sync_fence.p3_projection_capsule_items p3i" not in members_sql
        or "canonical_source_set_sha256" not in health_sql
    ):
        raise ValueError("P3生成canonical selectorが未供給です")
    _, sections, _, _ = _verified_inputs(_ROOT)
    old_health = _lifecycle_bind(sections["canonical_health"])
    old_members = _lifecycle_bind(sections["canonical_source_members"])

    def bound_p3_section(section: str) -> str:
        """LCのjsonb変数pと生成queryのplay_rows alias pを区別する。"""
        bound = _lifecycle_bind(section)
        whole_row = "pg_catalog.to_jsonb(p)"
        if bound.count(whole_row) != 1:
            raise ValueError("P3有効PlayRowの行参照が変更されました")
        return bound.replace(whole_row, "pg_catalog.to_jsonb(p.*)", 1)

    new_health = bound_p3_section(health_sql)
    new_members = bound_p3_section(members_sql)
    body = lifecycle_function_bodies()["consume_game_lifecycle"]
    if body.count(old_health) != 1 or body.count(old_members) != 1:
        raise ValueError("終了consumeの既canonical位置が変更されました")
    return body.replace(old_health, new_health, 1).replace(old_members, new_members, 1)
