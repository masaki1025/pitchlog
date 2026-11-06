"""P3有限capsule/既T5版の同TX保存関数候補を描画する。"""

from __future__ import annotations

import re

from pitchlog.authz.stats_primitive_sql import _ROOT, _verified_inputs
from pitchlog.authz.sync_right_sql import _COMMON


def candidate_sql(*, health_sql: str | None = None) -> str:
    """生成Sの健康度を再利用し、元原本と唯一T5の有限P3だけ保存する。"""
    _, sections, model, artifact = _verified_inputs(_ROOT)
    if health_sql is None:
        health_sql = sections["canonical_health"]
    if (
        type(health_sql) is not str
        or "sync_fence.p3_projection_heads p3h" not in health_sql
        or "sync_fence.p3_projection_capsule_items p3i" not in health_sql
        or "canonical_source_set_sha256" not in health_sql
    ):
        raise ValueError("P3生成canonical selectorが未供給")
    pattern = r"'(?:''|[^'])*'|(?<!:):([a-z][a-z0-9_]*)"
    binds = {match[1] for match in re.finditer(pattern, health_sql) if match[1]}
    if binds != {"tenant_id", "game_id"}:
        raise ValueError("P3生成canonical selectorに未知bind")
    health = re.sub(
        pattern,
        lambda match: match[0] if not match[1] else "p_" + match[1],
        health_sql.rstrip(";"),
    )
    statement = _SQL.replace("__COMMON__", _COMMON)
    statement = statement.replace("__HEALTH__", health)
    statement = statement.replace("__MODEL__", model)
    statement = statement.replace("__ARTIFACT__", artifact)
    return statement


def candidate_current_read_sql(*, health_sql: str) -> str:
    """同tenantの現head・有限後続・生成Sを同一版へ閉じたreader候補。"""
    return _CURRENT_READ_SQL.replace("__HEALTH__", _bind_health(health_sql))


def _bind_health(health_sql: str) -> str:
    """P3生成Sの二bindだけを閉じた関数引数へ写す。"""
    if (
        type(health_sql) is not str
        or "sync_fence.p3_projection_heads p3h" not in health_sql
        or "sync_fence.p3_projection_capsule_items p3i" not in health_sql
        or "canonical_source_set_sha256" not in health_sql
    ):
        raise ValueError("P3生成canonical selectorが未供給")
    pattern = r"'(?:''|[^'])*'|(?<!:):([a-z][a-z0-9_]*)"
    binds = {match[1] for match in re.finditer(pattern, health_sql) if match[1]}
    if binds != {"tenant_id", "game_id"}:
        raise ValueError("P3生成canonical selectorに未知bind")
    return re.sub(
        pattern,
        lambda match: match[0]
        if not match[1]
        else ("p_tenant_id" if match[1] == "tenant_id" else "p_game_id"),
        health_sql.rstrip(";"),
    )


_CURRENT_READ_SQL = """CREATE FUNCTION sync_right_api.read_p3_current(
p_tenant_id uuid,p_game_id uuid,p_generation bigint)
RETURNS TABLE(record_json text) LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_current$
#variable_conflict use_column
DECLARE h sync_fence.p3_projection_heads%ROWTYPE;
 c sync_fence.p3_projection_capsules%ROWTYPE;
 cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 v sync_fence.stats_fact_versions%ROWTYPE;
 change_event public.operation_events%ROWTYPE;
 change_ledger public.idempotency_ledger%ROWTYPE;
 members jsonb; member_count bigint; suffix_member jsonb;
 source_rows jsonb; source_count bigint; health record;
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL OR p_generation IS NULL
 OR p_generation<=0 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 THEN RAISE EXCEPTION 'P3 current read rejected' USING ERRCODE='42501'; END IF;
 SELECT x.* INTO h FROM sync_fence.p3_projection_heads x
 WHERE (x.tenant_id,x.game_id,x.internal_generation)=
 (p_tenant_id,p_game_id,p_generation);
 IF NOT FOUND THEN
 RETURN QUERY SELECT pg_catalog.jsonb_build_object('kind','none')::text;
 RETURN;
 END IF;
 SELECT x.* INTO STRICT c FROM sync_fence.p3_projection_capsules x
 WHERE (x.tenant_id,x.game_id,x.internal_generation,x.id)=
 (p_tenant_id,p_game_id,p_generation,h.capsule_id);
 SELECT x.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints x
 WHERE (x.tenant_id,x.game_id,x.internal_generation)=
 (p_tenant_id,p_game_id,p_generation) AND x.state='current';
 SELECT x.* INTO STRICT v FROM sync_fence.stats_fact_versions x
 WHERE (x.tenant_id,x.game_id,x.id)=
 (p_tenant_id,p_game_id,h.stats_version_id)
 AND x.is_current AND x.invalidated_at IS NULL;
 SELECT x.* INTO STRICT change_event FROM public.operation_events x
 WHERE (x.tenant_id,x.game_id,x.id)=
 (p_tenant_id,p_game_id,c.change_event_id)
 AND x.event_kind='play_change' AND x.ledger_kind='accepted'
 AND NOT x.is_tombstone AND x.replaced_at IS NULL AND x.retired_at IS NULL;
 SELECT x.* INTO STRICT change_ledger FROM public.idempotency_ledger x
 WHERE (x.tenant_id,x.d5)=(p_tenant_id,c.d5)
 AND x.kind='accepted' AND x.retired_at IS NULL;
 SELECT pg_catalog.count(*),COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.jsonb_build_object(
 'item',pg_catalog.to_jsonb(i),
 'original_event',pg_catalog.to_jsonb(e),
 'original_ledger',pg_catalog.to_jsonb(ol),
 'original_history',pg_catalog.to_jsonb(hi),
 'original_play_row',pg_catalog.to_jsonb(op),
 'original_play_runners',original_runners.rows,
 'effective_play_row',pg_catalog.to_jsonb(ep),
 'effective_play_runners',effective_runners.rows)
 ORDER BY i.d1),'[]'::jsonb)
 INTO member_count,members
 FROM sync_fence.p3_projection_capsule_items i
 LEFT JOIN public.operation_events e ON
 (e.tenant_id,e.id)=(i.tenant_id,i.original_event_id)
 LEFT JOIN public.idempotency_ledger ol ON
 (ol.tenant_id,ol.d5)=(e.tenant_id,e.d5)
 LEFT JOIN sync_fence.ordinary_pitch_history hi ON
 (hi.tenant_id,hi.game_id,hi.internal_generation,hi.source_event_id,hi.d1)=
 (i.tenant_id,i.game_id,i.internal_generation,i.original_event_id,i.d1)
 AND hi.history_version=cp.history_version
 LEFT JOIN public.play_rows op ON
 (op.tenant_id,op.id)=(i.tenant_id,i.original_play_row_id)
 LEFT JOIN public.play_rows ep ON
 (ep.tenant_id,ep.id)=(i.tenant_id,i.effective_play_row_id)
 CROSS JOIN LATERAL (SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(r) ORDER BY r.base),'[]'::jsonb) rows
 FROM public.play_runners r WHERE r.tenant_id=i.tenant_id
 AND r.play_id=i.original_play_row_id) original_runners
 CROSS JOIN LATERAL (SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(r) ORDER BY r.base),'[]'::jsonb) rows
 FROM public.play_runners r WHERE r.tenant_id=i.tenant_id
 AND r.play_id=i.effective_play_row_id) effective_runners
 WHERE (i.tenant_id,i.game_id,i.internal_generation,i.capsule_id)=
 (p_tenant_id,p_game_id,p_generation,h.capsule_id);
 IF member_count IS DISTINCT FROM c.watermark OR member_count NOT BETWEEN 1 AND 25
 OR cp.id IS DISTINCT FROM c.next_checkpoint_id
 OR cp.history_version IS DISTINCT FROM
 (c.next_checkpoint_content->>'history_version')::bigint
 OR cp.confirmed_watermark NOT BETWEEN c.watermark AND c.watermark+1
 OR cp.applied_watermark IS DISTINCT FROM cp.confirmed_watermark
 OR cp.revision IS DISTINCT FROM
 c.next_checkpoint_revision+(cp.confirmed_watermark-c.watermark)
 OR (cp.confirmed_watermark=c.watermark AND
 (cp.content IS DISTINCT FROM c.next_checkpoint_content OR
 cp.content_digest IS DISTINCT FROM c.next_checkpoint_digest))
 OR h.source_set_digest IS DISTINCT FROM c.source_set_digest
 OR h.stats_version_id IS DISTINCT FROM c.stats_version_id
 OR v.model_sha256 IS DISTINCT FROM c.stats_model_sha256
 OR v.source_count IS DISTINCT FROM cp.confirmed_watermark
 THEN RAISE EXCEPTION 'P3 current read rejected' USING ERRCODE='42501'; END IF;
 IF cp.confirmed_watermark>c.watermark THEN
 SELECT pg_catalog.jsonb_build_object(
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'history',pg_catalog.to_jsonb(hi),'play_row',pg_catalog.to_jsonb(p),
 'play_runners',r.rows) INTO STRICT suffix_member
 FROM public.event_slots slot
 JOIN public.operation_events e ON
 (e.tenant_id,e.game_id,e.generation,e.d1)=
 (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
 AND e.event_kind='play_input' AND e.ledger_kind='accepted'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 JOIN public.idempotency_ledger l ON
 (l.tenant_id,l.d5)=(e.tenant_id,e.d5)
 AND l.kind='accepted' AND l.retired_at IS NULL
 JOIN sync_fence.ordinary_pitch_history hi ON
 (hi.tenant_id,hi.game_id,hi.internal_generation,hi.d1,hi.source_event_id)=
 (e.tenant_id,e.game_id,e.generation,e.d1,e.id)
 AND hi.history_version=cp.history_version
 JOIN public.play_rows p ON
 (p.tenant_id,p.game_id,p.source_event_id)=(e.tenant_id,e.game_id,e.id)
 AND p.hidden_at IS NULL
 CROSS JOIN LATERAL (SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(pr) ORDER BY pr.base),'[]'::jsonb) rows
 FROM public.play_runners pr WHERE pr.tenant_id=p.tenant_id
 AND pr.play_id=p.id) r
 WHERE (slot.tenant_id,slot.game_id,slot.generation,slot.d1)=
 (p_tenant_id,p_game_id,p_generation,c.watermark+1)
 AND slot.confirmed_version=1;
 END IF;
 SELECT pg_catalog.count(*),COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(s) ORDER BY s.d1),'[]'::jsonb)
 INTO source_count,source_rows FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id)=
 (p_tenant_id,p_game_id,v.id);
 SELECT * INTO STRICT health FROM (__HEALTH__) p3_current_health;
 IF source_count IS DISTINCT FROM v.source_count
 OR health.game_count IS DISTINCT FROM 1::bigint
 OR health.unavailable_count IS DISTINCT FROM 0::bigint
 OR health.canonical_source_count IS DISTINCT FROM v.source_count
 OR health.canonical_source_set_sha256 IS DISTINCT FROM v.source_set_sha256
 THEN RAISE EXCEPTION 'P3 current read rejected' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object(
 'kind','p3-current','head',pg_catalog.to_jsonb(h),
 'capsule',pg_catalog.to_jsonb(c),'checkpoint',pg_catalog.to_jsonb(cp),
 'stats',pg_catalog.to_jsonb(v),
 'change_event',pg_catalog.to_jsonb(change_event),
 'change_ledger',pg_catalog.to_jsonb(change_ledger),
 'members',members,'suffix',suffix_member,'stats_sources',source_rows)::text;
END;
$p3_current$;
ALTER FUNCTION sync_right_api.read_p3_current(uuid,uuid,bigint)
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_p3_current(uuid,uuid,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.read_p3_current(uuid,uuid,bigint)
 TO pitchlog_app;
"""


_SQL = """CREATE FUNCTION sync_right_api.persist_p3_projection(
__COMMON__,p_capsule_json text,p_stats_json text)
RETURNS TABLE(capsule_id uuid,checkpoint_digest text,evaluation_set_digest text,
 stats_version_id uuid) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_projection$
#variable_conflict use_variable
DECLARE tenant uuid; own_xid text; binding record;
 c jsonb; t jsonb; item jsonb; source_item jsonb;
 old_cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 change_event public.operation_events%ROWTYPE;
 old_event public.operation_events%ROWTYPE;
 old_play public.play_rows%ROWTYPE;
 old_history sync_fence.ordinary_pitch_history%ROWTYPE;
 old_stats sync_fence.stats_fact_versions%ROWTYPE;
 old_source sync_fence.stats_primitive_sources%ROWTYPE;
 game_row record; lifecycle sync_fence.game_lifecycle_heads%ROWTYPE;
 health record; new_id uuid; new_event uuid; old_event_id uuid; new_play uuid;
 target_d1 bigint; generation bigint; watermark bigint; current_d1 bigint:=0;
 runner_rows jsonb; original_eval jsonb; effective_eval jsonb; new_artifact text;
 metric record; credit record; credit_ordinal bigint; source_keys text[];
 common_keys text[];
 now_at timestamptz; matched_count bigint;
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL OR p_attempt_id IS NULL
 OR p_phase_id IS NULL OR p_device_id IS NULL OR p_binding_nonce IS NULL
 OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 OR p_capsule_json IS NULL OR p_stats_json IS NULL THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,p_phase_id,
 p_binding_nonce,p_device_id,p_game_id);
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 SELECT b.* INTO STRICT binding FROM sync_fence_api.read_p3_writer_binding(
 p_tenant_id,p_attempt_id,p_phase_id,p_binding_nonce,p_device_id,p_game_id) b;
 tenant:=binding.tenant_id;
 c:=p_capsule_json::jsonb; t:=p_stats_json::jsonb;
 IF pg_catalog.jsonb_typeof(c) IS DISTINCT FROM 'object'
 OR pg_catalog.jsonb_typeof(t) IS DISTINCT FROM 'object'
 OR c->>'version' IS DISTINCT FROM 'p3-current-capsule-v1'
 OR t->>'version' IS DISTINCT FROM 'p3-current-stats-v1'
 OR c->>'tenant_id' IS DISTINCT FROM tenant::text
 OR c->>'game_id' IS DISTINCT FROM p_game_id::text
 OR c->>'d5' IS DISTINCT FROM binding.d5::text
 OR c->>'ledger_fingerprint' !~ '^[a-f0-9]{64}$'
 OR t->>'capsule_id' IS DISTINCT FROM c->>'capsule_id'
 OR c->>'source_set_digest' !~ '^[a-f0-9]{64}$'
 OR t->>'evaluation_set_digest' !~ '^[a-f0-9]{64}$'
 OR t->>'model_sha256' IS DISTINCT FROM '__MODEL__'
 OR pg_catalog.jsonb_typeof(c->'items') IS DISTINCT FROM 'array'
 OR pg_catalog.jsonb_typeof(t->'sources') IS DISTINCT FROM 'array'
 OR pg_catalog.jsonb_array_length(c->'items') NOT BETWEEN 1 AND 25
 OR pg_catalog.jsonb_array_length(c->'items') IS DISTINCT FROM
 pg_catalog.jsonb_array_length(t->'sources') THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 generation:=(c->>'internal_generation')::bigint;
 target_d1:=(c->>'target_d1')::bigint;
 watermark:=pg_catalog.jsonb_array_length(c->'items');
 IF generation IS DISTINCT FROM binding.internal_generation
 OR target_d1 NOT BETWEEN 1 AND watermark
 OR (c->>'expected_version')::bigint<>1
 OR EXISTS(SELECT 1 FROM sync_fence.p3_projection_heads h
 WHERE (h.tenant_id,h.game_id,h.internal_generation)=(tenant,p_game_id,generation))
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT cp.* INTO STRICT old_cp FROM sync_fence.ordinary_pitch_checkpoints cp
 WHERE (cp.tenant_id,cp.game_id,cp.internal_generation)=(tenant,p_game_id,generation)
 AND cp.state='current' AND cp.confirmed_watermark=watermark
 AND cp.applied_watermark=watermark AND cp.id=(c->>'previous_checkpoint_id')::uuid
 AND cp.revision=(c->>'previous_checkpoint_revision')::bigint
 AND cp.content_digest=c->>'previous_checkpoint_digest' FOR UPDATE;
 IF old_cp.content IS DISTINCT FROM c->'previous_checkpoint'
 OR (c->'next_checkpoint'->>'id')::uuid IS DISTINCT FROM old_cp.id
 OR (c->'next_checkpoint'->>'history_version')::bigint IS DISTINCT FROM
 old_cp.history_version
 OR c->'next_checkpoint'->'storage_anchor' IS DISTINCT FROM
 old_cp.content->'storage_anchor'
 OR c->'next_checkpoint'->>'wire_d4' IS DISTINCT FROM
 old_cp.content->>'wire_d4'
 OR target_d1>=watermark
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF c->'next_checkpoint'->>'content_digest' !~ '^[a-f0-9]{64}$'
 OR c->'next_checkpoint'->'prefix_ref'->'checkpoint'->>'digest'
 !~ '^[a-f0-9]{64}$'
 OR (c->'next_checkpoint'->>'confirmed_watermark')::bigint<>watermark
 OR (c->'next_checkpoint'->>'applied_watermark')::bigint<>watermark
 OR (c->'next_checkpoint'->>'internal_generation')::bigint<>generation
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT e.* INTO STRICT change_event FROM public.operation_events e
 WHERE (e.tenant_id,e.game_id,e.id)=(tenant,p_game_id,(c->>'change_event_id')::uuid)
 AND e.event_kind='play_change' AND e.ledger_kind='accepted' AND NOT e.is_tombstone
 AND e.generation IS NULL AND e.d1 IS NULL AND e.d2 IS NULL
 AND e.target_generation=generation AND e.target_d1=target_d1
 AND e.expected_version=1 AND e.d5=binding.d5
 AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified;
 IF NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l
 WHERE l.tenant_id=tenant AND l.d5=binding.d5 AND l.kind='accepted'
 AND l.source_fingerprint=c->>'ledger_fingerprint' AND l.retired_at IS NULL)
 OR change_event.payload->>'formatVersion' IS DISTINCT FROM
 'p3-lineup-pitch-change-v1'
 OR change_event.payload->>'targetEventId' IS DISTINCT FROM
 c->'items'->((target_d1-1)::integer)->>'original_event_id'
 OR NOT EXISTS(SELECT 1 FROM public.event_slots slot
 WHERE (slot.tenant_id,slot.game_id,slot.generation,slot.d1)=
 (tenant,p_game_id,generation,target_d1) AND slot.confirmed_version=2)
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT v.* INTO STRICT old_stats FROM sync_fence.stats_fact_versions v
 WHERE (v.tenant_id,v.game_id,v.model_sha256)=(tenant,p_game_id,'__MODEL__')
 AND v.is_current AND v.invalidated_at IS NULL
 AND v.source_count=watermark AND v.t5_artifact_set_sha256='__ARTIFACT__'
 FOR UPDATE;
 SELECT g.status INTO STRICT game_row FROM public.games g
 WHERE (g.tenant_id,g.id)=(tenant,p_game_id) AND g.status IN ('in_progress','finished')
 AND g.hidden_at IS NULL AND g.trashed_at IS NULL
 AND g.import_batch_id IS NULL;
 IF (SELECT pg_catalog.count(*) FROM public.recording_generations r
 WHERE (r.tenant_id,r.game_id,r.generation)=(tenant,p_game_id,generation)
 AND r.kind='normal' AND r.holder_device=p_device_id::text
 AND r.revoked_at IS NULL AND r.retired_at IS NULL
 AND r.recovery_generation=(SELECT g.recovery_generation
 FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open'))<>1
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF (game_row.status='finished') IS DISTINCT FROM
 (old_stats.completion_state='confirmed_ended')
 OR old_stats.rule_sha256 !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF game_row.status='finished' THEN
 SELECT h.* INTO STRICT lifecycle FROM sync_fence.game_lifecycle_heads h
 WHERE (h.tenant_id,h.game_id)=(tenant,p_game_id)
 AND h.is_finished AND h.active_stats_version_id=old_stats.id
 AND h.active_receipt_id=old_stats.completion_receipt_id
 AND h.active_receipt_id=old_stats.public_pointer_receipt_id FOR UPDATE;
 END IF;
 -- 旧版の全source・原event・履歴・物理行を元値と双方向照合する。
 FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(c->'items') LOOP
 current_d1:=current_d1+1;
 source_item:=t->'sources'->((current_d1-1)::integer);
 old_event_id:=(item->>'original_event_id')::uuid;
 new_event:=(item->>'effective_event_id')::uuid;
 new_play:=(item->>'effective_play_row_id')::uuid;
 original_eval:=source_item->'original_evaluation';
 effective_eval:=source_item->'evaluation';
 IF (item->>'d1')::bigint IS DISTINCT FROM current_d1
 OR (source_item->>'d1')::bigint IS DISTINCT FROM current_d1
 OR source_item->>'original_event_id' IS DISTINCT FROM old_event_id::text
 OR source_item->>'effective_event_id' IS DISTINCT FROM new_event::text
 OR source_item->>'effective_play_row_id' IS DISTINCT FROM new_play::text
 OR pg_catalog.jsonb_typeof(original_eval) IS DISTINCT FROM 'object'
 OR pg_catalog.jsonb_typeof(effective_eval) IS DISTINCT FROM 'object'
 OR original_eval->>'source_event_id' IS DISTINCT FROM old_event_id::text
 OR effective_eval->>'source_event_id' IS DISTINCT FROM new_event::text
 OR source_item->>'original_evaluation_digest' !~ '^[a-f0-9]{64}$'
 OR source_item->>'evaluation_digest' !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT e.* INTO STRICT old_event FROM public.operation_events e
 WHERE (e.tenant_id,e.game_id,e.id)=(tenant,p_game_id,old_event_id)
 AND e.event_kind='play_input' AND e.ledger_kind='accepted' AND NOT e.is_tombstone
 AND e.generation=generation AND e.d1=current_d1
 AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified;
 SELECT p.* INTO STRICT old_play FROM public.play_rows p
 WHERE (p.tenant_id,p.game_id,p.id)=
 (tenant,p_game_id,(item->>'original_play_row_id')::uuid)
 AND p.source_event_id=old_event_id AND p.hidden_at IS NULL
 AND p.import_batch_id IS NULL AND NOT p.migration_unverified;
 SELECT h.* INTO STRICT old_history FROM sync_fence.ordinary_pitch_history h
 WHERE (h.tenant_id,h.game_id,h.internal_generation,h.source_event_id,h.d1)=
 (tenant,p_game_id,generation,old_event_id,current_d1)
 AND h.history_version=old_cp.history_version;
 SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(r)
 ORDER BY r.base),'[]'::jsonb)
 INTO runner_rows FROM public.play_runners r WHERE r.tenant_id=tenant
 AND r.play_id=old_play.id;
 SELECT s.* INTO STRICT old_source FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id,s.source_event_id)=
 (tenant,p_game_id,old_stats.id,old_event_id)
 AND s.recording_generation=generation AND s.d1=current_d1;
 IF item->'original_payload' IS DISTINCT FROM old_event.payload
 OR item->'original_history_entry' IS DISTINCT FROM old_history.entry
 OR item->'original_play_row' IS DISTINCT FROM pg_catalog.to_jsonb(old_play)
 OR item->'original_play_runners' IS DISTINCT FROM runner_rows
 OR original_eval IS DISTINCT FROM old_source.metric_states
 OR original_eval->>'native_rule_sha256' IS DISTINCT FROM old_source.rule_sha256
 OR old_source.play_row_id IS DISTINCT FROM old_play.id
 OR old_source.d2 IS DISTINCT FROM old_event.d2
 OR item->>'d2' IS DISTINCT FROM old_event.d2::text
 OR item->>'original_play_row_id' IS DISTINCT FROM old_play.id::text
 OR item->>'original_event_id' IS DISTINCT FROM old_event.id::text
 OR old_source.evaluation_sha256 IS DISTINCT FROM pg_catalog.encode(
 pg_catalog.sha256(pg_catalog.convert_to(original_eval::text,'UTF8')),'hex')
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF current_d1=target_d1 THEN
   IF new_event IS DISTINCT FROM change_event.id OR new_play=old_play.id
   OR item->>'state' IS DISTINCT FROM 'corrected'
   OR item->'play_row'->>'source_event_id' IS DISTINCT FROM new_event::text
   OR item->'play_row'->>'id' IS DISTINCT FROM new_play::text
   THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 ELSE
   IF new_event IS DISTINCT FROM old_event.id OR new_play IS DISTINCT FROM old_play.id
   OR item->'play_row' IS DISTINCT FROM pg_catalog.to_jsonb(old_play)
   OR item->'play_runners' IS DISTINCT FROM runner_rows
   THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 END IF;
 END LOOP;
 -- 元全値を閉じた後だけP3有効対象行を追記する。元行は物理削除しない。
 item:=c->'items'->((target_d1-1)::integer);
 INSERT INTO sync_fence.p3_projection_write_admissions(
 tenant_id,attempt_id,phase_id,game_id,internal_generation,capsule_id,
 change_event_id,play_row_id,ledger_fingerprint,expected_play_row,transaction_id,state)
 VALUES(tenant,p_attempt_id,p_phase_id,p_game_id,generation,
 (c->>'capsule_id')::uuid,change_event.id,
 (item->>'effective_play_row_id')::uuid,c->>'ledger_fingerprint',
 item->'play_row',own_xid,'ready');
 IF pg_catalog.jsonb_array_length(item->'play_runners')<>0 THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 INSERT INTO public.play_rows SELECT (pg_catalog.jsonb_populate_record(
 NULL::public.play_rows,item->'play_row')).*;
 IF NOT EXISTS(SELECT 1 FROM sync_fence.p3_projection_write_admissions a
 WHERE (a.tenant_id,a.attempt_id,a.phase_id)=(tenant,p_attempt_id,p_phase_id)
 AND a.state='consumed' AND a.transaction_id=own_xid) THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 new_id:=pg_catalog.gen_random_uuid(); now_at:=pg_catalog.clock_timestamp();
 INSERT INTO sync_fence.p3_projection_capsules(
 tenant_id,game_id,internal_generation,id,change_event_id,d5,target_d1,expected_version,
 prior_checkpoint_id,prior_checkpoint_revision,prior_checkpoint_digest,
 prior_checkpoint_content,
 next_checkpoint_id,next_checkpoint_revision,next_checkpoint_digest,
 next_checkpoint_content,source_set_digest,stats_evaluation_set_digest,
 stats_model_sha256,stats_version_id,watermark,created_at)
 VALUES(tenant,p_game_id,generation,(c->>'capsule_id')::uuid,change_event.id,binding.d5,
 target_d1,1,old_cp.id,old_cp.revision,old_cp.content_digest,old_cp.content,
 (c->'next_checkpoint'->>'id')::uuid,(c->'next_checkpoint'->>'revision')::bigint,
 c->'next_checkpoint'->>'content_digest',c->'next_checkpoint',
 c->>'source_set_digest',t->>'evaluation_set_digest','__MODEL__',new_id,watermark,now_at);
 INSERT INTO sync_fence.p3_projection_capsule_items(
 tenant_id,game_id,internal_generation,capsule_id,d1,d2,state,
 original_event_id,effective_event_id,original_play_row_id,effective_play_row_id,
 original_payload,original_history_entry,original_play_row,original_play_runners,
 payload,history_entry,play_row,play_runners,item_digest)
 SELECT tenant,p_game_id,generation,(c->>'capsule_id')::uuid,
 (j.value->>'d1')::bigint,(j.value->>'d2')::bigint,j.value->>'state',
 (j.value->>'original_event_id')::uuid,(j.value->>'effective_event_id')::uuid,
 (j.value->>'original_play_row_id')::uuid,(j.value->>'effective_play_row_id')::uuid,
 j.value->'original_payload',j.value->'original_history_entry',
 j.value->'original_play_row',j.value->'original_play_runners',
 j.value->'payload',j.value->'history_entry',j.value->'play_row',
 j.value->'play_runners',j.value->>'digest'
 FROM pg_catalog.jsonb_array_elements(c->'items') j;
 INSERT INTO sync_fence.p3_projection_heads(tenant_id,game_id,internal_generation,
 capsule_id,revision,source_set_digest,stats_version_id,updated_at)
 VALUES(tenant,p_game_id,generation,(c->>'capsule_id')::uuid,1,
 c->>'source_set_digest',new_id,now_at);
 SELECT * INTO STRICT health FROM (__HEALTH__) actual_p3_health;
 IF health.game_count IS DISTINCT FROM 1 OR health.unavailable_count<>0
 OR health.canonical_source_count IS DISTINCT FROM watermark
 OR health.canonical_source_set_sha256 !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 UPDATE sync_fence.stats_fact_versions v SET is_current=false,invalidated_at=now_at
 WHERE (v.tenant_id,v.game_id,v.id)=(tenant,p_game_id,old_stats.id)
 AND v.is_current AND v.invalidated_at IS NULL;
 IF NOT FOUND THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 INSERT INTO sync_fence.stats_fact_versions(
 tenant_id,game_id,id,model_sha256,rule_sha256,t5_artifact_set_sha256,
 source_set_sha256,source_count,revision,last_generation,last_d1,last_d2,
 updated_at,computed_metric_keys,is_current,completion_state,
 completion_receipt_id,public_pointer_receipt_id,created_at,invalidated_at)
 SELECT tenant,p_game_id,new_id,v.model_sha256,v.rule_sha256,v.t5_artifact_set_sha256,
 health.canonical_source_set_sha256,watermark,v.revision+1,
 v.last_generation,v.last_d1,v.last_d2,now_at,v.computed_metric_keys,true,
 v.completion_state,v.completion_receipt_id,v.public_pointer_receipt_id,now_at,NULL
 FROM sync_fence.stats_fact_versions v WHERE (v.tenant_id,v.game_id,v.id)=
 (tenant,p_game_id,old_stats.id);
 FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(c->'items') LOOP
 current_d1:=(item->>'d1')::bigint;
 source_item:=t->'sources'->((current_d1-1)::integer);
 old_event_id:=(item->>'original_event_id')::uuid;
 new_event:=(item->>'effective_event_id')::uuid;
 new_play:=(item->>'effective_play_row_id')::uuid;
 effective_eval:=source_item->'evaluation';
 IF pg_catalog.jsonb_typeof(effective_eval->'metrics') IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
 pg_catalog.jsonb_object_keys(effective_eval) k) IS DISTINCT FROM
 ARRAY['decisions','metrics','native_rule_sha256','pa_row','selected','source_event_id']::text[]
 OR effective_eval->>'native_rule_sha256' IS DISTINCT FROM old_source.rule_sha256
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT s.* INTO STRICT old_source FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id,s.source_event_id)=
 (tenant,p_game_id,old_stats.id,old_event_id);
 new_artifact:=item->'payload'->'calculation'->>'artifactSha256';
 IF new_artifact IS NULL OR new_artifact !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT COALESCE(pg_catalog.array_agg(key ORDER BY key),'{}'::text[])
 INTO source_keys FROM pg_catalog.jsonb_each(effective_eval->'metrics')
 WHERE value->>'state'='available';
 IF current_d1=1 THEN common_keys:=source_keys;
 ELSE
 common_keys:=ARRAY(SELECT k FROM pg_catalog.unnest(common_keys) k
 WHERE k=ANY(source_keys) ORDER BY k);
 END IF;
 INSERT INTO sync_fence.stats_primitive_sources(
 tenant_id,game_id,fact_version_id,source_event_id,play_row_id,
 recording_generation,d1,d2,slot_version,play_row_version,provider_kind,
 attempt_id,phase_id,wire_d4,source_fingerprint,checkpoint_id,
 checkpoint_revision,checkpoint_digest,frame_digest,evaluation_sha256,
 artifact_sha256,rule_sha256,metric_states,computed_metric_keys,saved_at)
 VALUES(tenant,p_game_id,new_id,new_event,new_play,generation,current_d1,
 old_source.d2,CASE WHEN current_d1=target_d1 THEN 2 ELSE old_source.slot_version END,
 CASE WHEN current_d1=target_d1 THEN 1 ELSE old_source.play_row_version END,
 CASE WHEN current_d1=target_d1 THEN 'past_correction'
 ELSE old_source.provider_kind END,
 CASE WHEN current_d1=target_d1 THEN p_attempt_id ELSE old_source.attempt_id END,
 CASE WHEN current_d1=target_d1 THEN p_phase_id ELSE old_source.phase_id END,
 CASE WHEN current_d1=target_d1 THEN binding.wire_d4 ELSE old_source.wire_d4 END,
 CASE WHEN current_d1=target_d1 THEN c->>'ledger_fingerprint'
 ELSE old_source.source_fingerprint END,
 CASE WHEN current_d1=target_d1 THEN (c->'next_checkpoint'->>'id')::uuid
 ELSE old_source.checkpoint_id END,
 CASE WHEN current_d1=target_d1 THEN (c->'next_checkpoint'->>'revision')::bigint
 ELSE old_source.checkpoint_revision END,
 CASE WHEN current_d1=target_d1 THEN c->'next_checkpoint'->>'content_digest'
 ELSE old_source.checkpoint_digest END,
 CASE WHEN current_d1=target_d1 THEN item->>'digest' ELSE old_source.frame_digest END,
 pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(effective_eval::text,'UTF8')),'hex'),
 new_artifact,old_source.rule_sha256,effective_eval,source_keys,now_at);
 FOR metric IN SELECT key,value FROM
 pg_catalog.jsonb_each(effective_eval->'metrics') LOOP
 IF pg_catalog.jsonb_typeof(metric.value) IS DISTINCT FROM 'object'
 OR pg_catalog.jsonb_typeof(metric.value->'credits') IS DISTINCT FROM 'array'
 OR metric.value->>'state' NOT IN ('available','source_unavailable')
 THEN RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF metric.value->>'state'='available' THEN
 credit_ordinal:=0;
 FOR credit IN SELECT value FROM pg_catalog.jsonb_array_elements(
 metric.value->'credits') LOOP
 INSERT INTO sync_fence.stats_primitive_facts(
 tenant_id,game_id,fact_version_id,source_event_id,metric_id,player_id,
 credit_ordinal,state,amount)
 VALUES(tenant,p_game_id,new_id,new_event,metric.key,
 (credit.value->>'player_id')::uuid,credit_ordinal,'available',
 (credit.value->>'quantity')::numeric);
 credit_ordinal:=credit_ordinal+1;
 END LOOP;
 ELSIF pg_catalog.jsonb_array_length(metric.value->'credits')<>0 THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501';
 END IF;
 END LOOP;
 END LOOP;
 UPDATE sync_fence.stats_fact_versions v SET computed_metric_keys=common_keys
 WHERE (v.tenant_id,v.game_id,v.id)=(tenant,p_game_id,new_id)
 AND v.is_current AND v.invalidated_at IS NULL;
 IF NOT FOUND THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 SELECT count(*) INTO matched_count FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id)=(tenant,p_game_id,new_id);
 IF matched_count<>watermark THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 UPDATE sync_fence.ordinary_pitch_checkpoints cp SET
 revision=(c->'next_checkpoint'->>'revision')::bigint,
 content_digest=c->'next_checkpoint'->>'content_digest',
 content=c->'next_checkpoint',saved_at=now_at
 WHERE (cp.tenant_id,cp.game_id,cp.internal_generation)=
 (tenant,p_game_id,generation) AND cp.id=old_cp.id
 AND cp.revision=old_cp.revision AND cp.content_digest=old_cp.content_digest
 AND cp.content=old_cp.content AND cp.state='current';
 IF NOT FOUND THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 IF game_row.status='finished' THEN
 UPDATE sync_fence.game_lifecycle_heads h SET active_stats_version_id=new_id
 WHERE (h.tenant_id,h.game_id,h.active_stats_version_id)=
 (tenant,p_game_id,old_stats.id) AND h.active_receipt_id=lifecycle.active_receipt_id
 AND h.is_finished;
 IF NOT FOUND THEN
 RAISE EXCEPTION 'P3 projection rejected' USING ERRCODE='42501'; END IF;
 END IF;
 PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,p_phase_id,
 p_binding_nonce,p_device_id,p_game_id);
 RETURN QUERY SELECT (c->>'capsule_id')::uuid,
 c->'next_checkpoint'->>'content_digest',t->>'evaluation_set_digest',new_id;
END;
$p3_projection$;
ALTER FUNCTION sync_right_api.persist_p3_projection(
 uuid,uuid,uuid,bytea,uuid,uuid,text,text)
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.persist_p3_projection(
 uuid,uuid,uuid,bytea,uuid,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.persist_p3_projection(
 uuid,uuid,uuid,bytea,uuid,uuid,text,text) TO pitchlog_app;
"""
