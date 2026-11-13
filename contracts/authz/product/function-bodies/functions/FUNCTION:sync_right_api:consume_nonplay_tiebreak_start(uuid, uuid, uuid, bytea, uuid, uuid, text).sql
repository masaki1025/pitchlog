-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:consume_nonplay_tiebreak_start(uuid, uuid, uuid, bytea, uuid, uuid, text)

CREATE FUNCTION sync_right_api.consume_nonplay_tiebreak_start(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_request_json text)
RETURNS TABLE(consumed boolean) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $nonplay$
DECLARE stamp sync_fence.nonplay_write_admissions%ROWTYPE; own_xid text; p jsonb;
 cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; before_cp jsonb; after_cp jsonb; own_event public.operation_events%ROWTYPE;
BEGIN

IF session_user <> 'pitchlog_app' OR current_user <> 'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_device_id IS NULL
 OR p_game_id IS NULL OR p_binding_nonce IS NULL
 OR pg_catalog.octet_length(p_binding_nonce) <> 32 THEN
 RAISE EXCEPTION 'sync writer binding rejected' USING ERRCODE='42501';
END IF;
-- 実関数未供給なら例外で閉じる。callerのnonceだけでは成功しない。
PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,
 p_phase_id,p_binding_nonce,p_device_id,p_game_id);

 own_xid:=pg_catalog.pg_current_xact_id()::text;
 SELECT s.* INTO STRICT stamp FROM sync_fence.nonplay_write_admissions s
 JOIN sync_fence.writer_bindings b
 ON (b.tenant_id,b.attempt_id,b.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 JOIN sync_fence.writer_admissions a
 ON (a.tenant_id,a.attempt_id,a.phase_id)=(b.tenant_id,b.attempt_id,b.phase_id)
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND s.transaction_id=own_xid AND b.transaction_id=own_xid
 AND a.transaction_id=own_xid AND a.lease_id=b.lease_id
 AND b.state='open' AND b.expires_at>pg_catalog.clock_timestamp()
 AND a.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND s.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND s.tenant_id IS NOT DISTINCT FROM b.tenant_id AND s.attempt_id IS NOT DISTINCT FROM b.attempt_id AND s.phase_id IS NOT DISTINCT FROM b.phase_id AND s.authority_id IS NOT DISTINCT FROM b.authority_id AND s.control_instance IS NOT DISTINCT FROM b.control_instance AND s.business_instance IS NOT DISTINCT FROM b.business_instance AND s.restore_epoch IS NOT DISTINCT FROM b.restore_epoch AND s.control_version IS NOT DISTINCT FROM b.control_version AND s.issuer IS NOT DISTINCT FROM b.issuer AND s.lease_id IS NOT DISTINCT FROM b.lease_id AND s.device_id IS NOT DISTINCT FROM b.device_id AND s.game_id IS NOT DISTINCT FROM b.game_id AND s.wire_d4 IS NOT DISTINCT FROM b.wire_d4 AND s.internal_generation IS NOT DISTINCT FROM b.internal_generation AND s.recovery_generation IS NOT DISTINCT FROM b.recovery_generation AND s.codec_version IS NOT DISTINCT FROM b.codec_version AND s.request_fingerprint IS NOT DISTINCT FROM b.request_fingerprint AND s.d5 IS NOT DISTINCT FROM b.d5 AND s.event_fingerprint IS NOT DISTINCT FROM b.event_fingerprint AND s.system_identifier IS NOT DISTINCT FROM b.system_identifier AND s.database_oid IS NOT DISTINCT FROM b.database_oid AND s.postmaster_started_at IS NOT DISTINCT FROM b.postmaster_started_at AND s.backend_pid IS NOT DISTINCT FROM b.backend_pid AND s.backend_start IS NOT DISTINCT FROM b.backend_start AND s.transaction_id IS NOT DISTINCT FROM b.transaction_id AND s.nonce_digest IS NOT DISTINCT FROM b.nonce_digest AND s.expires_at IS NOT DISTINCT FROM b.expires_at FOR UPDATE OF s;
 IF NOT EXISTS(SELECT 1 FROM public.trusted_devices d
 WHERE d.tenant_id=p_tenant_id AND d.device_id=p_device_id AND d.revoked_at IS NULL)
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations r
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id
 AND r.generation=stamp.internal_generation AND r.kind='normal'
 AND r.holder_device=p_device_id::text AND r.revoked_at IS NULL
 AND r.retired_at IS NULL AND r.import_batch_id IS NULL
 AND r.recovery_generation=stamp.recovery_generation)
 OR NOT EXISTS(SELECT 1 FROM public.rg1_restore_gate g
 WHERE g.singleton_id=1 AND g.state='open'
 AND g.recovery_generation=stamp.recovery_generation) THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;

 IF p_request_json IS NULL THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 p:=p_request_json::jsonb;

 IF stamp.state<>'right_verified'
 OR p->>'formatVersion' IS DISTINCT FROM 'nonplay-tiebreak-start-preparation-v1'
 OR p->'beforeSource'->'checkpoint'->>'formatVersion'
 IS DISTINCT FROM 'nonplay-prefix-checkpoint-v1'
 OR p->'afterSource'->>'formatVersion'
 IS DISTINCT FROM 'nonplay-prefix-source-v1'
 THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
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
 THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 UPDATE sync_fence.ordinary_pitch_checkpoints SET
 revision=(after_cp->'ref'->>'revision')::bigint,
 confirmed_watermark=own_event.d1,applied_watermark=own_event.d1,
 content_digest=after_cp->'ref'->>'digest',content=after_cp,
 saved_at=pg_catalog.clock_timestamp()
 WHERE tenant_id=p_tenant_id AND game_id=p_game_id
 AND internal_generation=stamp.internal_generation AND id=cp.id
 AND revision=cp.revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 INSERT INTO sync_fence.tiebreak_start_write_receipts (
 tenant_id,attempt_id,phase_id,game_id,source_event_id,source_d1,
 checkpoint_id,before_revision,after_revision,after_digest)
 VALUES (p_tenant_id,p_attempt_id,p_phase_id,p_game_id,own_event.id,
 own_event.d1,cp.id,cp.revision,(after_cp->'ref'->>'revision')::bigint,
 after_cp->'ref'->>'digest');
 RETURN QUERY SELECT true;

END;
$nonplay$;

ALTER FUNCTION sync_right_api.consume_nonplay_tiebreak_start(uuid, uuid, uuid, bytea, uuid, uuid, text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.consume_nonplay_tiebreak_start(uuid, uuid, uuid, bytea, uuid, uuid, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.consume_nonplay_tiebreak_start(uuid, uuid, uuid, bytea, uuid, uuid, text) TO pitchlog_app;
