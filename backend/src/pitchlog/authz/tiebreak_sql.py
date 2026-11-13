"""タイブレーク開始の同TX保存専用SQL。"""

from pitchlog.authz.nonplay_prefix_sql import _REJECT, _function


def candidate_tiebreak_start_function_body() -> str:
    """評価済みタイブレーク開始を保存済みeventとCPに再結合して一回だけ確定する。"""
    return _function(
        "consume_nonplay_tiebreak_start",
        f"""
 IF stamp.state<>'right_verified'
 OR p->>'formatVersion' IS DISTINCT FROM 'nonplay-tiebreak-start-preparation-v1'
 OR p->'beforeSource'->'checkpoint'->>'formatVersion'
 IS DISTINCT FROM 'nonplay-prefix-checkpoint-v1'
 OR p->'afterSource'->>'formatVersion'
 IS DISTINCT FROM 'nonplay-prefix-source-v1'
 THEN {_REJECT} END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation AND c.state='current'
 AND c.recovery_generation=stamp.recovery_generation FOR UPDATE;
 SELECT e.* INTO STRICT own_event FROM public.operation_events e
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.event_slots s ON (s.tenant_id,s.game_id,s.generation,s.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.id=(p->>'eventId')::uuid AND e.d5=stamp.d5
 AND e.generation=stamp.internal_generation AND e.event_kind='tiebreak_start'
 AND e.ledger_kind='accepted' AND l.kind='accepted'
 AND l.source_fingerprint=stamp.event_fingerprint AND l.retired_at IS NULL
 AND l.import_batch_id IS NULL AND e.d2 IS NOT NULL AND e.state_diff IS NULL
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified;
 before_cp:=p->'beforeSource'->'checkpoint';
 after_cp:=p->'afterSource'->'checkpoint';
 IF pg_catalog.to_jsonb(cp) IS DISTINCT FROM p->'storage'->'row'
 OR (cp.content->>'version'='3' AND (
 cp.content->>'id' IS DISTINCT FROM before_cp->'ref'->>'id'
 OR cp.content->>'revision' IS DISTINCT FROM before_cp->'ref'->>'revision'
 OR cp.content->>'wire_d4' IS DISTINCT FROM
 before_cp->'content'->'scope'->>'generation'
 OR cp.confirmed_watermark::text IS DISTINCT FROM
 before_cp->'content'->>'d3'))
 OR (cp.content->>'version' IS DISTINCT FROM '3' AND (
 cp.content->>'formatVersion' IS DISTINCT FROM 'nonplay-prefix-checkpoint-v1'
 OR cp.content IS DISTINCT FROM before_cp
 OR cp.content_digest IS DISTINCT FROM before_cp->'ref'->>'digest'))
 OR cp.id IS DISTINCT FROM (before_cp->'ref'->>'id')::uuid
 OR cp.revision IS DISTINCT FROM (before_cp->'ref'->>'revision')::bigint
 OR own_event.payload IS DISTINCT FROM p->'eventOriginal'->'payload'
 OR own_event.payload->>'formatVersion' IS DISTINCT FROM 'tiebreak-start-event-v1'
 OR own_event.payload->'expectedCheckpoint' IS DISTINCT FROM before_cp->'ref'
 OR own_event.payload->>'eventId' IS DISTINCT FROM own_event.id::text
 OR p->'eventOriginal'->>'game_id' IS DISTINCT FROM p_game_id::text
 OR p->'eventOriginal'->>'d4' IS DISTINCT FROM stamp.wire_d4
 OR p->'eventOriginal'->>'d5' IS DISTINCT FROM own_event.d5::text
 OR (p->'eventOriginal'->>'d1')::bigint IS DISTINCT FROM own_event.d1
 OR own_event.d1 IS DISTINCT FROM (before_cp->'content'->>'d3')::bigint+1
 OR after_cp->'ref'->>'id' IS DISTINCT FROM before_cp->'ref'->>'id'
 OR (after_cp->'ref'->>'revision')::bigint IS DISTINCT FROM cp.revision+1
 OR after_cp->'content'->>'d3' IS DISTINCT FROM own_event.d1::text
 OR after_cp->'content'->'scope' IS DISTINCT FROM before_cp->'content'->'scope'
 OR after_cp->'content'->'executionArtifactSha256'
 IS DISTINCT FROM before_cp->'content'->'executionArtifactSha256'
 OR after_cp->'content'->'activeHead' IS DISTINCT FROM
 before_cp->'content'->'activeHead'
 OR after_cp->'content'->'activeDepth' IS DISTINCT FROM
 before_cp->'content'->'activeDepth'
 OR after_cp->'content'->'nextPhysicalPlayNumber'
 IS DISTINCT FROM before_cp->'content'->'nextPhysicalPlayNumber'
 OR p->'afterSource'->'activeStack' IS DISTINCT FROM p->'beforeSource'->'activeStack'
 OR after_cp->'content'->'restored' IS DISTINCT FROM p->'transition'
 OR after_cp->'content'->'tiebreakFrames'->-1->'source'->>'eventId'
 IS DISTINCT FROM own_event.id::text
 OR after_cp->'content'->'tiebreakFrames'->-1->'source'->>'fingerprint'
 IS DISTINCT FROM stamp.event_fingerprint
 OR after_cp->'content'->'historyVersion' IS DISTINCT FROM
 pg_catalog.to_jsonb(((before_cp->'content'->>'historyVersion')::bigint+1)::text)
 THEN {_REJECT} END IF;
 UPDATE sync_fence.ordinary_pitch_checkpoints SET
 revision=(after_cp->'ref'->>'revision')::bigint,
 confirmed_watermark=own_event.d1,applied_watermark=own_event.d1,
 content_digest=after_cp->'ref'->>'digest',content=after_cp,
 saved_at=pg_catalog.clock_timestamp()
 WHERE tenant_id=p_tenant_id AND game_id=p_game_id
 AND internal_generation=stamp.internal_generation AND id=cp.id
 AND revision=cp.revision;
 IF NOT FOUND THEN {_REJECT} END IF;
 INSERT INTO sync_fence.tiebreak_start_write_receipts (
 tenant_id,attempt_id,phase_id,game_id,source_event_id,source_d1,
 checkpoint_id,before_revision,after_revision,after_digest)
 VALUES (p_tenant_id,p_attempt_id,p_phase_id,p_game_id,own_event.id,
 own_event.d1,cp.id,cp.revision,(after_cp->'ref'->>'revision')::bigint,
 after_cp->'ref'->>'digest');
 RETURN QUERY SELECT true;
""",
        "consumed boolean",
        "before_cp jsonb; after_cp jsonb; own_event public.operation_events%ROWTYPE;",
    )
