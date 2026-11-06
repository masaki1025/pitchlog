-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:consume_game_lifecycle(uuid, uuid, uuid, bytea, uuid, uuid, text)

CREATE FUNCTION sync_right_api.consume_game_lifecycle(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_request_json text)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $lifecycle$
DECLARE stamp sync_fence.nonplay_write_admissions%ROWTYPE; own_xid text; p jsonb;
 cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 game_row record; h sync_fence.game_lifecycle_heads%ROWTYPE; before_cp jsonb; after_cp jsonb; expected_content jsonb; expected_head jsonb; expected_restored jsonb; expected_bridge jsonb; lifecycle jsonb; next_lifecycle jsonb; own_event public.operation_events%ROWTYPE; action text; anchor_id text; lifecycle_stamp sync_fence.lifecycle_write_admissions%ROWTYPE; prior sync_fence.stats_fact_versions%ROWTYPE; new_id uuid; source_health record;
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

 IF stamp.state<>'right_verified' OR p_request_json IS NULL THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 p:=p_request_json::jsonb;

 SELECT x.tenant_id,x.id,x.status,x.trashed_at,x.hidden_at,x.import_batch_id
 INTO STRICT game_row FROM public.games x
 WHERE x.tenant_id=p_tenant_id AND x.id=p_game_id
 AND x.trashed_at IS NULL AND x.hidden_at IS NULL
 AND x.import_batch_id IS NULL;
 SELECT x.* INTO h FROM sync_fence.game_lifecycle_heads x
 WHERE x.tenant_id=p_tenant_id AND x.game_id=p_game_id;
 IF NOT FOUND THEN
   IF game_row.status<>'in_progress' OR EXISTS(SELECT 1 FROM public.operation_events e
   WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
   AND e.event_kind IN ('game_end_declaration','game_reopen')
   AND e.ledger_kind='accepted' AND e.replaced_at IS NULL AND e.retired_at IS NULL
   AND e.id IS DISTINCT FROM (p->>'event_id')::uuid) THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
   lifecycle:=pg_catalog.jsonb_build_object('status','in_progress','lastVersion','0','active',NULL);
 ELSE
   IF h.is_finished IS DISTINCT FROM (game_row.status='finished')
   OR game_row.status NOT IN ('in_progress','finished') THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
   IF h.is_finished AND NOT EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v
   JOIN public.operation_events e ON e.tenant_id=v.tenant_id
   AND e.game_id=v.game_id AND e.id=h.active_end_event_id
   JOIN sync_fence.lifecycle_write_admissions a ON a.tenant_id=e.tenant_id AND a.game_id=e.game_id
   AND a.source_event_id=e.id AND a.receipt_id=h.active_receipt_id
   WHERE v.tenant_id=p_tenant_id AND v.game_id=p_game_id AND
 v.id=h.active_stats_version_id
   AND v.is_current AND v.invalidated_at IS NULL AND
 v.completion_state='confirmed_ended'
   AND v.completion_receipt_id=h.active_receipt_id
   AND v.public_pointer_receipt_id=h.active_receipt_id AND a.state='consumed'
   AND a.action='end' AND e.event_kind='game_end_declaration'
   AND e.ledger_kind='accepted' AND NOT e.is_tombstone AND e.retired_at IS NULL
   AND e.replaced_at IS NULL) THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
   lifecycle:=pg_catalog.jsonb_build_object('status',game_row.status,
    'lastVersion',h.last_version::text,'active',CASE WHEN h.is_finished
     THEN pg_catalog.jsonb_build_object('version',h.last_version::text,
      'eventId',h.active_end_event_id::text,'receiptId',h.active_receipt_id::text)
     ELSE NULL END);
 END IF;

 IF pg_catalog.jsonb_typeof(p) IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.jsonb_object_keys(p) k)
 IS DISTINCT FROM ARRAY['after_source','artifact_sha256','before_source','event_id',
 'event_original','frame_digest','frame_id','receipt_id','request','response',
 'source_fingerprint','storage']::text[] THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation AND c.state='current'
 AND c.recovery_generation=stamp.recovery_generation FOR UPDATE;
 IF p->'storage'->'row' IS DISTINCT FROM pg_catalog.to_jsonb(cp)
 OR p->'before_source'->'checkpoint'->'ref'->>'id' IS DISTINCT FROM cp.id::text
 OR p->'before_source'->'checkpoint'->'ref'->>'revision' IS DISTINCT FROM
 cp.revision::text
 -- v3の物理digestと既readerが導出するnonplay論理digestは別原本。
 OR (cp.content->>'version' IS DISTINCT FROM '3' AND
 p->'before_source'->'checkpoint'->'ref'->>'digest' IS DISTINCT FROM
 cp.content_digest)
 OR (cp.content->>'version'='3' AND
 (p->'before_source'->'checkpoint'->'ref'->>'digest' IS NULL OR
 p->'before_source'->'checkpoint'->'ref'->>'digest' !~ '^[a-f0-9]{64}$'))
 OR cp.confirmed_watermark+1<>(p->'event_original'->>'d1')::bigint
 OR cp.applied_watermark<>cp.confirmed_watermark THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;

 -- 既legacy/undoには新defaultを補完しない。presentなら全consumed原本へ閉じる。
 IF cp.content->>'formatVersion'='nonplay-prefix-checkpoint-v1' THEN
 IF EXISTS(SELECT 1 FROM
 pg_catalog.jsonb_array_elements(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb)) b(value)
 WHERE NOT EXISTS(SELECT 1 FROM (SELECT a.*,e.id AS original_id,r.issuance_order AS generation_order
 FROM sync_fence.lifecycle_write_admissions a
 JOIN public.operation_events e ON e.tenant_id=a.tenant_id AND e.game_id=a.game_id
 AND e.id=a.source_event_id AND e.generation=a.internal_generation AND e.d1=a.source_d1
 JOIN public.event_slots slot ON (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.recording_generations r ON r.tenant_id=e.tenant_id AND r.game_id=e.game_id
 AND r.generation=e.generation
 JOIN public.recording_generations current_generation ON
 current_generation.tenant_id=r.tenant_id
 AND current_generation.game_id=r.game_id AND current_generation.generation=stamp.internal_generation
 JOIN sync_fence.writer_bindings original_binding
 ON (original_binding.tenant_id,original_binding.attempt_id,original_binding.phase_id)
 =(a.tenant_id,a.attempt_id,a.phase_id)
 WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id AND a.state='consumed'
 AND a.consumed_at IS NOT NULL AND e.ledger_kind='accepted'
 AND e.event_kind=CASE WHEN a.action='end' THEN 'game_end_declaration' ELSE
 'game_reopen' END
 AND a.action IN ('end','reopen') AND e.d2=a.source_d2 AND e.d5=a.d5
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND slot.confirmed_version=1
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND l.source_fingerprint=a.event_fingerprint AND e.xmin=a.xmin AND l.xmin=a.xmin
 AND a.tenant_id IS NOT DISTINCT FROM original_binding.tenant_id AND a.attempt_id IS NOT DISTINCT FROM original_binding.attempt_id AND a.phase_id IS NOT DISTINCT FROM original_binding.phase_id AND a.authority_id IS NOT DISTINCT FROM original_binding.authority_id AND a.control_instance IS NOT DISTINCT FROM original_binding.control_instance AND a.business_instance IS NOT DISTINCT FROM original_binding.business_instance AND a.restore_epoch IS NOT DISTINCT FROM original_binding.restore_epoch AND a.control_version IS NOT DISTINCT FROM original_binding.control_version AND a.issuer IS NOT DISTINCT FROM original_binding.issuer AND a.lease_id IS NOT DISTINCT FROM original_binding.lease_id AND a.device_id IS NOT DISTINCT FROM original_binding.device_id AND a.game_id IS NOT DISTINCT FROM original_binding.game_id AND a.wire_d4 IS NOT DISTINCT FROM original_binding.wire_d4 AND a.internal_generation IS NOT DISTINCT FROM original_binding.internal_generation AND a.recovery_generation IS NOT DISTINCT FROM original_binding.recovery_generation AND a.codec_version IS NOT DISTINCT FROM original_binding.codec_version AND a.request_fingerprint IS NOT DISTINCT FROM original_binding.request_fingerprint AND a.d5 IS NOT DISTINCT FROM original_binding.d5 AND a.event_fingerprint IS NOT DISTINCT FROM original_binding.event_fingerprint AND a.system_identifier IS NOT DISTINCT FROM original_binding.system_identifier AND a.database_oid IS NOT DISTINCT FROM original_binding.database_oid AND a.postmaster_started_at IS NOT DISTINCT FROM original_binding.postmaster_started_at AND a.backend_pid IS NOT DISTINCT FROM original_binding.backend_pid AND a.backend_start IS NOT DISTINCT FROM original_binding.backend_start AND a.transaction_id IS NOT DISTINCT FROM original_binding.transaction_id AND a.nonce_digest IS NOT DISTINCT FROM original_binding.nonce_digest AND a.expires_at IS NOT DISTINCT FROM original_binding.expires_at
 AND r.issuance_order<=current_generation.issuance_order
 AND (e.generation<>stamp.internal_generation OR e.d1<=cp.confirmed_watermark)
) a
 WHERE a.source_event_id=(b.value->'source'->>'eventId')::uuid
 AND a.frame_id=(b.value->>'frameId')::uuid
 AND a.action=b.value->>'action' AND a.wire_d4=b.value->'source'->>'generation'
 AND a.source_d1::text=b.value->'source'->>'d1'
 AND a.d5::text=b.value->'source'->>'d5'
 AND a.event_fingerprint=b.value->'source'->>'fingerprint'
 AND a.checkpoint_id::text=b.value->'checkpointBefore'->>'id'
 AND a.checkpoint_revision::text=b.value->'checkpointBefore'->>'revision'
 AND a.checkpoint_digest=b.value->'checkpointBefore'->>'digest'
 AND a.receipt_id::text=b.value->'kernel'->'request'->'event'->>'receiptId'
 AND a.source_event_id::text=b.value->'kernel'->'request'->'event'->>'eventId'
 AND b.value->'source'->>'gameId'=p_game_id::text
 AND a.preparation->'after_source'->'checkpoint'->'content'->'controlBridges'->-1
 =b.value
 AND a.preparation->'event_original'->'payload'=(SELECT e.payload FROM
 public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.id=a.source_event_id)))
 OR EXISTS(SELECT 1 FROM (SELECT a.*,e.id AS original_id,r.issuance_order AS generation_order
 FROM sync_fence.lifecycle_write_admissions a
 JOIN public.operation_events e ON e.tenant_id=a.tenant_id AND e.game_id=a.game_id
 AND e.id=a.source_event_id AND e.generation=a.internal_generation AND e.d1=a.source_d1
 JOIN public.event_slots slot ON (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.recording_generations r ON r.tenant_id=e.tenant_id AND r.game_id=e.game_id
 AND r.generation=e.generation
 JOIN public.recording_generations current_generation ON
 current_generation.tenant_id=r.tenant_id
 AND current_generation.game_id=r.game_id AND current_generation.generation=stamp.internal_generation
 JOIN sync_fence.writer_bindings original_binding
 ON (original_binding.tenant_id,original_binding.attempt_id,original_binding.phase_id)
 =(a.tenant_id,a.attempt_id,a.phase_id)
 WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id AND a.state='consumed'
 AND a.consumed_at IS NOT NULL AND e.ledger_kind='accepted'
 AND e.event_kind=CASE WHEN a.action='end' THEN 'game_end_declaration' ELSE
 'game_reopen' END
 AND a.action IN ('end','reopen') AND e.d2=a.source_d2 AND e.d5=a.d5
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND slot.confirmed_version=1
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND l.source_fingerprint=a.event_fingerprint AND e.xmin=a.xmin AND l.xmin=a.xmin
 AND a.tenant_id IS NOT DISTINCT FROM original_binding.tenant_id AND a.attempt_id IS NOT DISTINCT FROM original_binding.attempt_id AND a.phase_id IS NOT DISTINCT FROM original_binding.phase_id AND a.authority_id IS NOT DISTINCT FROM original_binding.authority_id AND a.control_instance IS NOT DISTINCT FROM original_binding.control_instance AND a.business_instance IS NOT DISTINCT FROM original_binding.business_instance AND a.restore_epoch IS NOT DISTINCT FROM original_binding.restore_epoch AND a.control_version IS NOT DISTINCT FROM original_binding.control_version AND a.issuer IS NOT DISTINCT FROM original_binding.issuer AND a.lease_id IS NOT DISTINCT FROM original_binding.lease_id AND a.device_id IS NOT DISTINCT FROM original_binding.device_id AND a.game_id IS NOT DISTINCT FROM original_binding.game_id AND a.wire_d4 IS NOT DISTINCT FROM original_binding.wire_d4 AND a.internal_generation IS NOT DISTINCT FROM original_binding.internal_generation AND a.recovery_generation IS NOT DISTINCT FROM original_binding.recovery_generation AND a.codec_version IS NOT DISTINCT FROM original_binding.codec_version AND a.request_fingerprint IS NOT DISTINCT FROM original_binding.request_fingerprint AND a.d5 IS NOT DISTINCT FROM original_binding.d5 AND a.event_fingerprint IS NOT DISTINCT FROM original_binding.event_fingerprint AND a.system_identifier IS NOT DISTINCT FROM original_binding.system_identifier AND a.database_oid IS NOT DISTINCT FROM original_binding.database_oid AND a.postmaster_started_at IS NOT DISTINCT FROM original_binding.postmaster_started_at AND a.backend_pid IS NOT DISTINCT FROM original_binding.backend_pid AND a.backend_start IS NOT DISTINCT FROM original_binding.backend_start AND a.transaction_id IS NOT DISTINCT FROM original_binding.transaction_id AND a.nonce_digest IS NOT DISTINCT FROM original_binding.nonce_digest AND a.expires_at IS NOT DISTINCT FROM original_binding.expires_at
 AND r.issuance_order<=current_generation.issuance_order
 AND (e.generation<>stamp.internal_generation OR e.d1<=cp.confirmed_watermark)
) a WHERE NOT EXISTS(
 SELECT 1 FROM pg_catalog.jsonb_array_elements(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb)) b(value)
 WHERE b.value->'source'->>'eventId'=a.source_event_id::text))
 OR EXISTS(SELECT 1 FROM public.operation_events control_event
 JOIN public.recording_generations control_generation ON
 (control_generation.tenant_id,control_generation.game_id,control_generation.generation)
 =(control_event.tenant_id,control_event.game_id,control_event.generation)
 JOIN public.recording_generations selected_generation ON
 selected_generation.tenant_id=control_event.tenant_id
 AND selected_generation.game_id=control_event.game_id AND
 selected_generation.generation=stamp.internal_generation
 WHERE control_event.tenant_id=p_tenant_id AND control_event.game_id=p_game_id
 AND control_event.event_kind IN ('game_end_declaration','game_reopen')
 AND control_event.ledger_kind='accepted' AND control_event.replaced_at IS NULL
 AND control_event.retired_at IS NULL
 AND control_generation.issuance_order<=selected_generation.issuance_order
 AND (control_event.generation<>stamp.internal_generation OR
 control_event.d1<=cp.confirmed_watermark)
 AND NOT EXISTS(SELECT 1 FROM
 pg_catalog.jsonb_array_elements(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb)) b(value)
 WHERE b.value->'source'->>'eventId'=control_event.id::text))
 OR EXISTS(SELECT 1 FROM (SELECT count(*) AS n,count(DISTINCT
 value->'source'->>'eventId') AS unique_n
 FROM pg_catalog.jsonb_array_elements(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb)))
 duplicate_controls
 WHERE n<>unique_n)
 OR EXISTS(SELECT 1 FROM (
 SELECT a.generation_order,a.source_d1,
 lag(a.generation_order) OVER(ORDER BY b.ordinality) AS previous_generation,
 lag(a.source_d1) OVER(ORDER BY b.ordinality) AS previous_d1
 FROM pg_catalog.jsonb_array_elements(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb))
 WITH ORDINALITY b(value,ordinality)
 JOIN (SELECT a.*,e.id AS original_id,r.issuance_order AS generation_order
 FROM sync_fence.lifecycle_write_admissions a
 JOIN public.operation_events e ON e.tenant_id=a.tenant_id AND e.game_id=a.game_id
 AND e.id=a.source_event_id AND e.generation=a.internal_generation AND e.d1=a.source_d1
 JOIN public.event_slots slot ON (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.recording_generations r ON r.tenant_id=e.tenant_id AND r.game_id=e.game_id
 AND r.generation=e.generation
 JOIN public.recording_generations current_generation ON
 current_generation.tenant_id=r.tenant_id
 AND current_generation.game_id=r.game_id AND current_generation.generation=stamp.internal_generation
 JOIN sync_fence.writer_bindings original_binding
 ON (original_binding.tenant_id,original_binding.attempt_id,original_binding.phase_id)
 =(a.tenant_id,a.attempt_id,a.phase_id)
 WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id AND a.state='consumed'
 AND a.consumed_at IS NOT NULL AND e.ledger_kind='accepted'
 AND e.event_kind=CASE WHEN a.action='end' THEN 'game_end_declaration' ELSE
 'game_reopen' END
 AND a.action IN ('end','reopen') AND e.d2=a.source_d2 AND e.d5=a.d5
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND slot.confirmed_version=1
 AND l.kind='accepted' AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND l.source_fingerprint=a.event_fingerprint AND e.xmin=a.xmin AND l.xmin=a.xmin
 AND a.tenant_id IS NOT DISTINCT FROM original_binding.tenant_id AND a.attempt_id IS NOT DISTINCT FROM original_binding.attempt_id AND a.phase_id IS NOT DISTINCT FROM original_binding.phase_id AND a.authority_id IS NOT DISTINCT FROM original_binding.authority_id AND a.control_instance IS NOT DISTINCT FROM original_binding.control_instance AND a.business_instance IS NOT DISTINCT FROM original_binding.business_instance AND a.restore_epoch IS NOT DISTINCT FROM original_binding.restore_epoch AND a.control_version IS NOT DISTINCT FROM original_binding.control_version AND a.issuer IS NOT DISTINCT FROM original_binding.issuer AND a.lease_id IS NOT DISTINCT FROM original_binding.lease_id AND a.device_id IS NOT DISTINCT FROM original_binding.device_id AND a.game_id IS NOT DISTINCT FROM original_binding.game_id AND a.wire_d4 IS NOT DISTINCT FROM original_binding.wire_d4 AND a.internal_generation IS NOT DISTINCT FROM original_binding.internal_generation AND a.recovery_generation IS NOT DISTINCT FROM original_binding.recovery_generation AND a.codec_version IS NOT DISTINCT FROM original_binding.codec_version AND a.request_fingerprint IS NOT DISTINCT FROM original_binding.request_fingerprint AND a.d5 IS NOT DISTINCT FROM original_binding.d5 AND a.event_fingerprint IS NOT DISTINCT FROM original_binding.event_fingerprint AND a.system_identifier IS NOT DISTINCT FROM original_binding.system_identifier AND a.database_oid IS NOT DISTINCT FROM original_binding.database_oid AND a.postmaster_started_at IS NOT DISTINCT FROM original_binding.postmaster_started_at AND a.backend_pid IS NOT DISTINCT FROM original_binding.backend_pid AND a.backend_start IS NOT DISTINCT FROM original_binding.backend_start AND a.transaction_id IS NOT DISTINCT FROM original_binding.transaction_id AND a.nonce_digest IS NOT DISTINCT FROM original_binding.nonce_digest AND a.expires_at IS NOT DISTINCT FROM original_binding.expires_at
 AND r.issuance_order<=current_generation.issuance_order
 AND (e.generation<>stamp.internal_generation OR e.d1<=cp.confirmed_watermark)
) a ON a.source_event_id::text=b.value->'source'->>'eventId'
 ) ordered_controls WHERE previous_generation>generation_order
 OR (previous_generation=generation_order AND previous_d1>=source_d1))
 THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 IF pg_catalog.jsonb_array_length(COALESCE(cp.content->'content'->'controlBridges','[]'::jsonb))>0 AND NOT EXISTS(
 SELECT 1 FROM sync_fence.game_lifecycle_heads lifecycle_head WHERE lifecycle_head.tenant_id=p_tenant_id
 AND lifecycle_head.game_id=p_game_id
 AND lifecycle_head.last_control_event_id::text=(cp.content->'content'->'controlBridges'->-1)->'source'->>'eventId'
 AND lifecycle_head.is_finished=((cp.content->'content'->'controlBridges'->-1)->>'action'='end')
 ) THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 END IF;

 before_cp:=p->'before_source'->'checkpoint'; after_cp:=p->'after_source'->'checkpoint';
 IF cp.content->>'version'='3' THEN
   expected_restored:=pg_catalog.jsonb_build_object('current',cp.content->'after',
    'rules',cp.content->'rules','rulesDigest',before_cp->'content'->'restored'->'rulesDigest',
    'layoutDigest',cp.content->'roster_digest','rosterDigest',cp.content->'roster_digest',
    'lineup',cp.content->'lineup','participants',cp.content->'participants',
    'runners',cp.content->'runners','responsibility',pg_catalog.jsonb_build_object('kind','no-change',
    'paStartSource',cp.content->'pa_start_source','previousPitcherId',NULL,
    'strikesAtChange',NULL,'ballsAtChange',NULL),
    'lastPlayEvaluation',cp.content->'t2');
   IF before_cp->'content'->'restored' IS DISTINCT FROM expected_restored THEN
 RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 ELSE
   IF cp.content->>'formatVersion' IS DISTINCT FROM 'nonplay-prefix-checkpoint-v1'
   OR before_cp IS DISTINCT FROM cp.content THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 END IF;
 SELECT e.* INTO STRICT own_event FROM public.operation_events e
 JOIN public.event_slots s ON (s.tenant_id,s.game_id,s.generation,s.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.generation=stamp.internal_generation AND e.id=(p->>'event_id')::uuid
 AND e.d5=stamp.d5 AND e.ledger_kind='accepted' AND l.kind='accepted'
 AND l.source_fingerprint=stamp.event_fingerprint AND l.retired_at IS NULL
 AND e.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND s.confirmed_version=1 AND NOT e.is_tombstone AND e.replaced_at IS NULL
 AND e.retired_at IS NULL AND e.import_batch_id IS NULL AND e.d2>=0;
 action:=p->'request'->>'action';
 IF action NOT IN ('end','reopen') OR own_event.event_kind IS DISTINCT FROM
 (CASE WHEN action='end' THEN 'game_end_declaration' ELSE 'game_reopen' END)
 OR own_event.payload->>'formatVersion' IS DISTINCT FROM 'native-game-lifecycle-v1'
 OR own_event.payload->>'action' IS DISTINCT FROM action
 OR NOT (
  (own_event.payload->'checkpointRef'->>'kind'='confirmed'
   AND ((own_event.payload->'checkpointRef')-'kind')=before_cp->'ref')
  OR (own_event.payload->'checkpointRef'->>'kind'='queued_predecessor'
   AND own_event.payload->'checkpointRef'=pg_catalog.jsonb_build_object(
    'kind','queued_predecessor','d4',stamp.wire_d4,'d1',own_event.d1-1,
    'd5',before_cp->'content'->'d1Head'->'source'->>'d5')
   AND before_cp->'content'->'d1Head'->'source'->>'gameId'=p_game_id::text
   AND before_cp->'content'->'d1Head'->'source'->>'generation'=stamp.wire_d4
   AND before_cp->'content'->'d1Head'->'source'->>'d1'=(own_event.d1-1)::text)
  OR (own_event.payload->'checkpointRef'->>'kind'='confirmed_prefix'
   AND own_event.payload->'checkpointRef'=pg_catalog.jsonb_build_object(
    'kind','confirmed_prefix','id',before_cp->'content'->'controlBridges'->-1
    ->'checkpointBefore'->>'id','revision',before_cp->'content'->'controlBridges'
    ->-1->'checkpointBefore'->>'revision','digest',before_cp->'content'
    ->'controlBridges'->-1->'checkpointBefore'->>'digest','d4',stamp.wire_d4,
    'd1',own_event.d1-1,'d5',before_cp->'content'->'d1Head'->'source'->>'d5')
   AND before_cp->'content'->'controlBridges'->-1->'source'
    =before_cp->'content'->'d1Head'->'source'
   AND before_cp->'content'->'d1Head'->'source'->>'gameId'=p_game_id::text
   AND before_cp->'content'->'d1Head'->'source'->>'generation'=stamp.wire_d4
   AND before_cp->'content'->'d1Head'->'source'->>'d1'=(own_event.d1-1)::text))
 OR NOT (
  (action='end' AND own_event.payload->'target'='null'::jsonb
   AND p->'request'->'target'='null'::jsonb)
  OR (action='reopen' AND
   ((own_event.payload->'target'->>'kind'='confirmed'
     AND (own_event.payload->'target')-'kind'=p->'request'->'target')
    OR (own_event.payload->'target'->>'kind'='queued_end'
     AND p->'request'->'target'=lifecycle->'active'
     AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
      COALESCE(before_cp->'content'->'controlBridges','[]'::jsonb)) b(value)
      WHERE b.value->>'action'='end'
      AND b.value->'source'->>'gameId'=p_game_id::text
      AND b.value->'source'->>'generation'=own_event.payload->'target'->>'d4'
      AND b.value->'source'->>'d1'=own_event.payload->'target'->>'d1'
      AND b.value->'source'->>'d5'=own_event.payload->'target'->>'d5'
      AND b.value->'source'->>'eventId'=own_event.payload->'target'->>'eventId'
      AND b.value->'kernel'->'request'->'event'->>'receiptId'
       =own_event.payload->'target'->>'receiptId'
      AND b.value->'kernel'->'response'->'value'->'lifecycle'->'active'
       =p->'request'->'target')))))
 OR own_event.payload->'event'->>'eventId' IS DISTINCT FROM own_event.id::text
 OR own_event.payload->'event'->>'receiptId' IS DISTINCT FROM p->>'receipt_id'
 OR p->>'source_fingerprint' IS DISTINCT FROM stamp.event_fingerprint
 OR p->'event_original'->>'event_kind' IS DISTINCT FROM own_event.event_kind
 OR p->'event_original'->'payload' IS DISTINCT FROM own_event.payload
 OR p->'event_original'->>'d4' IS DISTINCT FROM stamp.wire_d4
 OR p->'event_original'->>'game_id' IS DISTINCT FROM p_game_id::text
 OR p->'event_original'->>'d5' IS DISTINCT FROM own_event.d5::text
 OR (p->'event_original'->>'d1')::bigint IS DISTINCT FROM own_event.d1
 OR (p->'event_original'->>'d2')::bigint IS DISTINCT FROM own_event.d2
 OR p->'request'->'event'->>'eventId' IS DISTINCT FROM own_event.id::text
 OR p->'request'->'event'->>'receiptId' IS DISTINCT FROM p->>'receipt_id'
 OR p->'request'->'lifecycle' IS DISTINCT FROM lifecycle
 OR p->'request'->'current' IS DISTINCT FROM before_cp->'content'->'restored'->'current'
 OR p->'response'->'ok' IS DISTINCT FROM 'true'::jsonb
 OR p->'after_source'->'activeStack' IS DISTINCT FROM p->'before_source'->'activeStack'
 THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 IF action='end' THEN
   IF game_row.status<>'in_progress' OR
   p->'request'->'target' IS DISTINCT FROM 'null'::jsonb
   OR p->'response'->'value'->'current' IS DISTINCT FROM p->'request'->'current'
   THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
   next_lifecycle:=pg_catalog.jsonb_build_object('status','finished',
    'lastVersion',((lifecycle->>'lastVersion')::bigint+1)::text,
    'active',pg_catalog.jsonb_build_object('version',((lifecycle->>'lastVersion')::bigint+1)::text,
    'eventId',own_event.id::text,'receiptId',p->>'receipt_id'));
 ELSE
   IF game_row.status<>'finished' OR p->'request'->'target' IS DISTINCT FROM
 lifecycle->'active'
   OR p->'response'->'value'->'current' IS DISTINCT FROM
    pg_catalog.jsonb_set(p->'request'->'current','{stateFields,state.gameEnded}','false'::jsonb)
   THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
   next_lifecycle:=pg_catalog.jsonb_build_object('status','in_progress',
    'lastVersion',lifecycle->>'lastVersion','active',NULL);
 END IF;
 IF p->'response'->'value'->'lifecycle' IS DISTINCT FROM next_lifecycle THEN
 RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 expected_restored:=(before_cp->'content'->'restored')||pg_catalog.jsonb_build_object(
 'current',p->'response'->'value'->'current');
 expected_head:=pg_catalog.jsonb_build_object('eventId',own_event.id::text,'gameId',p_game_id::text,
 'generation',stamp.wire_d4,'d1',own_event.d1::text,'d5',own_event.d5::text,
 'fingerprint',stamp.event_fingerprint,'eventKind',own_event.event_kind);
 anchor_id:=before_cp->'content'->'origin'->>'eventId';
 IF pg_catalog.jsonb_array_length(p->'before_source'->'activeStack')>0 THEN
 anchor_id:=p->'before_source'->'activeStack'->0->'play'->'source'->>'eventId'; END IF;
 expected_bridge:=pg_catalog.jsonb_build_object('source',expected_head,'action',action,
 'anchorEventId',anchor_id,'beforeContext',before_cp->'content'->'restored',
 'afterContext',expected_restored,'kernel',pg_catalog.jsonb_build_object(
 'request',p->'request','response',p->'response'),'frameId',p->>'frame_id',
 'checkpointBefore',before_cp->'ref');
 expected_content:=before_cp->'content'||pg_catalog.jsonb_build_object(
 'd3',own_event.d1::text,'d1Head',pg_catalog.jsonb_build_object('kind','accepted-event','source',expected_head),
 'projectionHead',pg_catalog.jsonb_build_object('kind','d1-event','source',expected_head),
 'historyVersion',((before_cp->'content'->>'historyVersion')::bigint+1)::text,
 'restored',expected_restored,'controlBridges',
 COALESCE(before_cp->'content'->'controlBridges','[]'::jsonb)||pg_catalog.jsonb_build_array(expected_bridge));
 IF after_cp->'content' IS DISTINCT FROM expected_content
 OR after_cp->'ref'->>'id' IS DISTINCT FROM cp.id::text
 OR after_cp->'ref'->>'revision' IS DISTINCT FROM (cp.revision+1)::text
 OR after_cp->>'formatVersion' IS DISTINCT FROM 'nonplay-prefix-checkpoint-v1'
 THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;

 SELECT a.* INTO STRICT lifecycle_stamp FROM sync_fence.lifecycle_write_admissions a
 WHERE (a.tenant_id,a.attempt_id,a.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND a.transaction_id=own_xid AND a.state='evaluated'
 AND a.preparation_json=p_request_json AND a.preparation=p
 AND a.frame_id=(p->>'frame_id')::uuid AND a.frame_digest=p->>'frame_digest'
 AND a.source_event_id=own_event.id AND a.d5=own_event.d5 FOR UPDATE;
 UPDATE sync_fence.ordinary_pitch_checkpoints SET content=after_cp,
 content_digest=after_cp->'ref'->>'digest',revision=cp.revision+1,
 confirmed_watermark=own_event.d1,applied_watermark=own_event.d1,
 saved_at=pg_catalog.clock_timestamp()
 WHERE tenant_id=p_tenant_id AND game_id=p_game_id AND id=cp.id
 AND internal_generation=stamp.internal_generation AND revision=cp.revision
 AND content_digest=cp.content_digest AND state='current';
 IF NOT FOUND THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 UPDATE sync_fence.lifecycle_write_admissions SET state='consumed',consumed_at=pg_catalog.clock_timestamp()
 WHERE (tenant_id,attempt_id,phase_id)=(p_tenant_id,p_attempt_id,p_phase_id) AND
 state='evaluated';
 IF NOT FOUND THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 SELECT v.* INTO STRICT prior FROM sync_fence.stats_fact_versions v
 WHERE v.tenant_id=p_tenant_id AND v.game_id=p_game_id AND v.is_current
 AND v.invalidated_at IS NULL AND v.model_sha256='sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d'
 AND v.t5_artifact_set_sha256='28af30fd1b1300c805b7dcb243fc7b32ab9d6db9fc10c38bdcbc63fa85c3a0de'
 AND v.completion_state=CASE WHEN action='end' THEN 'current_open' ELSE
 'confirmed_ended' END FOR UPDATE;
 IF action='reopen' AND prior.id IS DISTINCT FROM h.active_stats_version_id THEN
 RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;

 -- 内容を再計算せず、保存済み唯一T5応答の全creditと実fact集合を双方向比較する。
 IF EXISTS(SELECT 1 FROM sync_fence.stats_primitive_sources s
 WHERE s.tenant_id=p_tenant_id AND s.game_id=p_game_id AND s.fact_version_id=prior.id
 AND s.evaluation_sha256 IS DISTINCT FROM pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 s.metric_states::text,'UTF8')),'hex')) OR EXISTS(
 WITH expected_credits AS (
  SELECT s.source_event_id,m.key AS metric_id,(c.value->>'player_id')::uuid AS player_id,
  c.ordinality-1 AS credit_ordinal,'available'::text AS state,(c.value->>'quantity')::numeric AS amount
  FROM sync_fence.stats_primitive_sources s
  CROSS JOIN LATERAL pg_catalog.jsonb_each(s.metric_states->'metrics') m
  CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(m.value->'credits') WITH ORDINALITY c
  WHERE s.tenant_id=p_tenant_id AND s.game_id=p_game_id AND s.fact_version_id=prior.id
 ), actual_credits AS (
  SELECT f.source_event_id,f.metric_id,f.player_id,f.credit_ordinal,f.state,f.amount
  FROM sync_fence.stats_primitive_facts f WHERE f.tenant_id=p_tenant_id AND f.game_id=p_game_id
  AND f.fact_version_id=prior.id
 )
 (SELECT * FROM expected_credits EXCEPT SELECT * FROM actual_credits)
 UNION ALL (SELECT * FROM actual_credits EXCEPT SELECT * FROM expected_credits)
 ) THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;

 SELECT * INTO STRICT source_health FROM (WITH canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=p_tenant_id AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=p_game_id
), canonical_undos AS (
 SELECT n.* FROM sync_fence.nonplay_write_admissions n
 JOIN canonical_scope scope ON (scope.tenant_id,scope.game_id)=(n.tenant_id,n.game_id)
 JOIN sync_fence.writer_bindings ub ON n.tenant_id IS NOT DISTINCT FROM ub.tenant_id AND n.attempt_id IS NOT DISTINCT FROM ub.attempt_id AND n.phase_id IS NOT DISTINCT FROM ub.phase_id AND n.authority_id IS NOT DISTINCT FROM ub.authority_id AND n.control_instance IS NOT DISTINCT FROM ub.control_instance AND n.business_instance IS NOT DISTINCT FROM ub.business_instance AND n.restore_epoch IS NOT DISTINCT FROM ub.restore_epoch AND n.control_version IS NOT DISTINCT FROM ub.control_version AND n.issuer IS NOT DISTINCT FROM ub.issuer AND n.lease_id IS NOT DISTINCT FROM ub.lease_id AND n.device_id IS NOT DISTINCT FROM ub.device_id AND n.game_id IS NOT DISTINCT FROM ub.game_id AND n.wire_d4 IS NOT DISTINCT FROM ub.wire_d4 AND n.internal_generation IS NOT DISTINCT FROM ub.internal_generation AND n.recovery_generation IS NOT DISTINCT FROM ub.recovery_generation AND n.codec_version IS NOT DISTINCT FROM ub.codec_version AND n.request_fingerprint IS NOT DISTINCT FROM ub.request_fingerprint AND n.d5 IS NOT DISTINCT FROM ub.d5 AND n.event_fingerprint IS NOT DISTINCT FROM ub.event_fingerprint AND n.system_identifier IS NOT DISTINCT FROM ub.system_identifier AND n.database_oid IS NOT DISTINCT FROM ub.database_oid AND n.postmaster_started_at IS NOT DISTINCT FROM ub.postmaster_started_at AND n.backend_pid IS NOT DISTINCT FROM ub.backend_pid AND n.backend_start IS NOT DISTINCT FROM ub.backend_start AND n.transaction_id IS NOT DISTINCT FROM ub.transaction_id AND n.nonce_digest IS NOT DISTINCT FROM ub.nonce_digest AND n.expires_at IS NOT DISTINCT FROM ub.expires_at
 JOIN public.operation_events u ON (u.tenant_id,u.game_id,u.id)=(n.tenant_id,n.game_id,n.source_event_id)
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 JOIN public.event_slots us ON (us.tenant_id,us.game_id,us.generation,us.d1)
  =(u.tenant_id,u.game_id,u.generation,u.d1) AND us.confirmed_version=1
 JOIN public.operation_events t ON (t.tenant_id,t.game_id,t.id)=(n.tenant_id,n.game_id,n.target_event_id)
 JOIN public.idempotency_ledger tl ON tl.tenant_id=t.tenant_id AND tl.d5=t.d5
 JOIN public.play_rows tp ON (tp.tenant_id,tp.game_id,tp.id)=(n.tenant_id,n.game_id,n.target_play_id)
  AND tp.source_event_id=t.id AND tp.hidden_at IS NOT NULL
 WHERE n.state='consumed' AND n.consumed_at IS NOT NULL
 AND n.preparation_json::jsonb=n.preparation
 AND n.frame_id=(n.preparation->>'frame_id')::uuid
 AND n.frame_digest=n.preparation->>'frame_digest'
 AND n.artifact_sha256=n.preparation->>'artifact_sha256'
 AND n.source_event_id=(n.preparation->>'event_id')::uuid
 AND n.target_event_id=(n.preparation->'target'->'source'->>'eventId')::uuid
 AND n.target_play_id=(n.preparation->'target'->>'playId')::uuid
 AND n.checkpoint_id=(n.preparation->'before_source'->'checkpoint'->'ref'->>'id')::uuid
 AND n.checkpoint_revision=(n.preparation->'before_source'->'checkpoint'->'ref'->>'revision')::bigint
 AND n.checkpoint_digest=n.preparation->'before_source'->'checkpoint'->'ref'->>'digest'
 AND u.event_kind='undo' AND u.ledger_kind='accepted' AND ul.kind='accepted'
 AND u.d5=n.d5 AND u.generation=n.internal_generation AND u.d1=n.source_d1
 AND u.d2 IS NULL AND u.state_diff IS NULL AND NOT u.is_tombstone
 AND u.replaced_at IS NULL AND u.retired_at IS NULL AND u.import_batch_id IS NULL
 AND NOT u.migration_unverified AND ul.retired_at IS NULL AND ul.import_batch_id IS NULL
 AND ul.source_fingerprint=n.event_fingerprint
 AND u.payload=n.preparation->'event_original'->'payload'
 AND u.payload->'calculation'->'response'=n.preparation->'response'
 AND u.payload->>'artifactSha256'=n.artifact_sha256
 AND u.target_generation=n.target_generation AND u.target_d1=n.target_d1
 AND t.event_kind='play_input' AND t.ledger_kind='accepted' AND tl.kind='accepted'
 AND t.generation=n.target_generation AND t.d1=n.target_d1
 AND t.replaced_at IS NULL AND t.retired_at IS NULL AND t.import_batch_id IS NULL
 AND NOT t.is_tombstone AND NOT t.migration_unverified
 AND tl.retired_at IS NULL AND tl.import_batch_id IS NULL
 AND tl.source_fingerprint=n.preparation->'target'->'source'->>'fingerprint'
 AND tp.import_batch_id IS NULL AND NOT tp.migration_unverified
), canonical_raw AS (
 SELECT slot.tenant_id,slot.game_id,slot.generation AS recording_generation,
   slot.d1,e.d2,slot.confirmed_version AS slot_version,e.id AS base_event_id,
   CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END AS source_event_id,
   p.id AS play_row_id,p.version AS play_row_version,
   current_event.d5,ledger.source_fingerprint,
   current_event.payload->>'formatVersion' AS native_variant,
   current_event.payload#>>'{calculation,artifactSha256}' AS artifact_sha256,
   COUNT(*) OVER (PARTITION BY slot.tenant_id,slot.game_id,slot.generation,slot.d1) AS match_count,
   CASE WHEN gen.retired_at IS NOT NULL THEN 'excluded_retired'
     WHEN e.id IS NULL OR current_event.id IS NULL THEN 'source_unavailable'
     WHEN e.event_kind='undo' AND NOT EXISTS (SELECT 1 FROM canonical_undos verified WHERE verified.source_event_id=current_event.id) THEN 'source_unavailable'
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN undo.source_event_id IS NOT NULL AND undo.source_event_id IS DISTINCT FROM NULL::uuid /* restore-undo-event */ THEN 'excluded_undo'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR (p.hidden_at IS NOT NULL AND NOT COALESCE(undo.source_event_id=NULL::uuid /* restore-undo-event */,false)) THEN 'source_unavailable'
     ELSE 'included' END AS preliminary_state
 FROM public.event_slots slot JOIN canonical_scope g
   ON g.tenant_id=slot.tenant_id AND g.game_id=slot.game_id
 JOIN public.recording_generations gen ON gen.tenant_id=slot.tenant_id
   AND gen.game_id=slot.game_id AND gen.generation=slot.generation
 LEFT JOIN public.operation_events e ON e.tenant_id=slot.tenant_id AND e.game_id=slot.game_id
   AND e.generation=slot.generation AND e.d1=slot.d1
   AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.ledger_kind='accepted'
 LEFT JOIN public.operation_events change ON change.tenant_id=slot.tenant_id AND change.game_id=slot.game_id
   AND change.target_generation=slot.generation AND change.target_d1=slot.d1
   AND change.expected_version=slot.confirmed_version-1 AND slot.confirmed_version>1
   AND change.ledger_kind='accepted' AND change.replaced_at IS NULL AND change.retired_at IS NULL
 LEFT JOIN public.operation_events current_event ON current_event.tenant_id=slot.tenant_id
   AND current_event.game_id=slot.game_id
   AND current_event.id=CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END
 LEFT JOIN public.idempotency_ledger ledger ON ledger.tenant_id=current_event.tenant_id
   AND ledger.d5=current_event.d5
 LEFT JOIN public.play_rows p ON p.tenant_id=current_event.tenant_id
   AND p.game_id=current_event.game_id AND p.source_event_id=current_event.id
 LEFT JOIN canonical_undos undo ON undo.tenant_id=current_event.tenant_id
   AND undo.game_id=current_event.game_id AND undo.target_event_id=current_event.id
   AND undo.target_play_id=p.id
), canonical_s AS (
 SELECT *,CASE WHEN match_count<>1 THEN 'source_unavailable'
               ELSE preliminary_state END AS source_state FROM canonical_raw
), canonical_health AS (
 SELECT g.tenant_id,g.game_id,1::bigint AS game_count,
   COUNT(*) FILTER (WHERE c.source_state='included') AS canonical_source_count,
   COUNT(*) FILTER (WHERE c.source_state='source_unavailable') AS unavailable_count,
   encode(sha256(convert_to(COALESCE(string_agg(
     jsonb_build_array(c.tenant_id,c.game_id,c.recording_generation,c.d1,c.d2,c.source_event_id,
       c.slot_version,c.play_row_id,c.play_row_version,c.source_fingerprint)::text,
     E'\n' ORDER BY c.tenant_id,c.game_id,c.d2,c.source_event_id)
     FILTER (WHERE c.source_state='included'),'accepted-play-slot-v1:empty'),'UTF8')),'hex')
     AS canonical_source_set_sha256
 FROM canonical_scope g LEFT JOIN canonical_s c
   ON c.tenant_id=g.tenant_id AND c.game_id=g.game_id
 GROUP BY g.tenant_id,g.game_id
)
SELECT COALESCE(ch.game_count,0) AS game_count,COALESCE(ch.canonical_source_count,0) AS canonical_source_count,COALESCE(ch.unavailable_count,0) AS unavailable_count,COALESCE(ch.canonical_source_set_sha256,encode(sha256(convert_to('accepted-play-slot-v1:empty','UTF8')),'hex')) AS canonical_source_set_sha256 FROM (VALUES(1)) singleton(n) LEFT JOIN canonical_health ch ON true) canonical_before;
 IF source_health.game_count<>1 OR source_health.unavailable_count<>0
 OR source_health.canonical_source_count<>prior.source_count
 OR source_health.canonical_source_set_sha256 IS DISTINCT FROM prior.source_set_sha256
 OR (SELECT count(*) FROM (WITH canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=p_tenant_id AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=p_game_id
), canonical_undos AS (
 SELECT n.* FROM sync_fence.nonplay_write_admissions n
 JOIN canonical_scope scope ON (scope.tenant_id,scope.game_id)=(n.tenant_id,n.game_id)
 JOIN sync_fence.writer_bindings ub ON n.tenant_id IS NOT DISTINCT FROM ub.tenant_id AND n.attempt_id IS NOT DISTINCT FROM ub.attempt_id AND n.phase_id IS NOT DISTINCT FROM ub.phase_id AND n.authority_id IS NOT DISTINCT FROM ub.authority_id AND n.control_instance IS NOT DISTINCT FROM ub.control_instance AND n.business_instance IS NOT DISTINCT FROM ub.business_instance AND n.restore_epoch IS NOT DISTINCT FROM ub.restore_epoch AND n.control_version IS NOT DISTINCT FROM ub.control_version AND n.issuer IS NOT DISTINCT FROM ub.issuer AND n.lease_id IS NOT DISTINCT FROM ub.lease_id AND n.device_id IS NOT DISTINCT FROM ub.device_id AND n.game_id IS NOT DISTINCT FROM ub.game_id AND n.wire_d4 IS NOT DISTINCT FROM ub.wire_d4 AND n.internal_generation IS NOT DISTINCT FROM ub.internal_generation AND n.recovery_generation IS NOT DISTINCT FROM ub.recovery_generation AND n.codec_version IS NOT DISTINCT FROM ub.codec_version AND n.request_fingerprint IS NOT DISTINCT FROM ub.request_fingerprint AND n.d5 IS NOT DISTINCT FROM ub.d5 AND n.event_fingerprint IS NOT DISTINCT FROM ub.event_fingerprint AND n.system_identifier IS NOT DISTINCT FROM ub.system_identifier AND n.database_oid IS NOT DISTINCT FROM ub.database_oid AND n.postmaster_started_at IS NOT DISTINCT FROM ub.postmaster_started_at AND n.backend_pid IS NOT DISTINCT FROM ub.backend_pid AND n.backend_start IS NOT DISTINCT FROM ub.backend_start AND n.transaction_id IS NOT DISTINCT FROM ub.transaction_id AND n.nonce_digest IS NOT DISTINCT FROM ub.nonce_digest AND n.expires_at IS NOT DISTINCT FROM ub.expires_at
 JOIN public.operation_events u ON (u.tenant_id,u.game_id,u.id)=(n.tenant_id,n.game_id,n.source_event_id)
 JOIN public.idempotency_ledger ul ON ul.tenant_id=u.tenant_id AND ul.d5=u.d5
 JOIN public.event_slots us ON (us.tenant_id,us.game_id,us.generation,us.d1)
  =(u.tenant_id,u.game_id,u.generation,u.d1) AND us.confirmed_version=1
 JOIN public.operation_events t ON (t.tenant_id,t.game_id,t.id)=(n.tenant_id,n.game_id,n.target_event_id)
 JOIN public.idempotency_ledger tl ON tl.tenant_id=t.tenant_id AND tl.d5=t.d5
 JOIN public.play_rows tp ON (tp.tenant_id,tp.game_id,tp.id)=(n.tenant_id,n.game_id,n.target_play_id)
  AND tp.source_event_id=t.id AND tp.hidden_at IS NOT NULL
 WHERE n.state='consumed' AND n.consumed_at IS NOT NULL
 AND n.preparation_json::jsonb=n.preparation
 AND n.frame_id=(n.preparation->>'frame_id')::uuid
 AND n.frame_digest=n.preparation->>'frame_digest'
 AND n.artifact_sha256=n.preparation->>'artifact_sha256'
 AND n.source_event_id=(n.preparation->>'event_id')::uuid
 AND n.target_event_id=(n.preparation->'target'->'source'->>'eventId')::uuid
 AND n.target_play_id=(n.preparation->'target'->>'playId')::uuid
 AND n.checkpoint_id=(n.preparation->'before_source'->'checkpoint'->'ref'->>'id')::uuid
 AND n.checkpoint_revision=(n.preparation->'before_source'->'checkpoint'->'ref'->>'revision')::bigint
 AND n.checkpoint_digest=n.preparation->'before_source'->'checkpoint'->'ref'->>'digest'
 AND u.event_kind='undo' AND u.ledger_kind='accepted' AND ul.kind='accepted'
 AND u.d5=n.d5 AND u.generation=n.internal_generation AND u.d1=n.source_d1
 AND u.d2 IS NULL AND u.state_diff IS NULL AND NOT u.is_tombstone
 AND u.replaced_at IS NULL AND u.retired_at IS NULL AND u.import_batch_id IS NULL
 AND NOT u.migration_unverified AND ul.retired_at IS NULL AND ul.import_batch_id IS NULL
 AND ul.source_fingerprint=n.event_fingerprint
 AND u.payload=n.preparation->'event_original'->'payload'
 AND u.payload->'calculation'->'response'=n.preparation->'response'
 AND u.payload->>'artifactSha256'=n.artifact_sha256
 AND u.target_generation=n.target_generation AND u.target_d1=n.target_d1
 AND t.event_kind='play_input' AND t.ledger_kind='accepted' AND tl.kind='accepted'
 AND t.generation=n.target_generation AND t.d1=n.target_d1
 AND t.replaced_at IS NULL AND t.retired_at IS NULL AND t.import_batch_id IS NULL
 AND NOT t.is_tombstone AND NOT t.migration_unverified
 AND tl.retired_at IS NULL AND tl.import_batch_id IS NULL
 AND tl.source_fingerprint=n.preparation->'target'->'source'->>'fingerprint'
 AND tp.import_batch_id IS NULL AND NOT tp.migration_unverified
), canonical_raw AS (
 SELECT slot.tenant_id,slot.game_id,slot.generation AS recording_generation,
   slot.d1,e.d2,slot.confirmed_version AS slot_version,e.id AS base_event_id,
   CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END AS source_event_id,
   p.id AS play_row_id,p.version AS play_row_version,
   current_event.d5,ledger.source_fingerprint,
   current_event.payload->>'formatVersion' AS native_variant,
   current_event.payload#>>'{calculation,artifactSha256}' AS artifact_sha256,
   COUNT(*) OVER (PARTITION BY slot.tenant_id,slot.game_id,slot.generation,slot.d1) AS match_count,
   CASE WHEN gen.retired_at IS NOT NULL THEN 'excluded_retired'
     WHEN e.id IS NULL OR current_event.id IS NULL THEN 'source_unavailable'
     WHEN e.event_kind='undo' AND NOT EXISTS (SELECT 1 FROM canonical_undos verified WHERE verified.source_event_id=current_event.id) THEN 'source_unavailable'
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN undo.source_event_id IS NOT NULL AND undo.source_event_id IS DISTINCT FROM NULL::uuid /* restore-undo-event */ THEN 'excluded_undo'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR (p.hidden_at IS NOT NULL AND NOT COALESCE(undo.source_event_id=NULL::uuid /* restore-undo-event */,false)) THEN 'source_unavailable'
     ELSE 'included' END AS preliminary_state
 FROM public.event_slots slot JOIN canonical_scope g
   ON g.tenant_id=slot.tenant_id AND g.game_id=slot.game_id
 JOIN public.recording_generations gen ON gen.tenant_id=slot.tenant_id
   AND gen.game_id=slot.game_id AND gen.generation=slot.generation
 LEFT JOIN public.operation_events e ON e.tenant_id=slot.tenant_id AND e.game_id=slot.game_id
   AND e.generation=slot.generation AND e.d1=slot.d1
   AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.ledger_kind='accepted'
 LEFT JOIN public.operation_events change ON change.tenant_id=slot.tenant_id AND change.game_id=slot.game_id
   AND change.target_generation=slot.generation AND change.target_d1=slot.d1
   AND change.expected_version=slot.confirmed_version-1 AND slot.confirmed_version>1
   AND change.ledger_kind='accepted' AND change.replaced_at IS NULL AND change.retired_at IS NULL
 LEFT JOIN public.operation_events current_event ON current_event.tenant_id=slot.tenant_id
   AND current_event.game_id=slot.game_id
   AND current_event.id=CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END
 LEFT JOIN public.idempotency_ledger ledger ON ledger.tenant_id=current_event.tenant_id
   AND ledger.d5=current_event.d5
 LEFT JOIN public.play_rows p ON p.tenant_id=current_event.tenant_id
   AND p.game_id=current_event.game_id AND p.source_event_id=current_event.id
 LEFT JOIN canonical_undos undo ON undo.tenant_id=current_event.tenant_id
   AND undo.game_id=current_event.game_id AND undo.target_event_id=current_event.id
   AND undo.target_play_id=p.id
), canonical_s AS (
 SELECT *,CASE WHEN match_count<>1 THEN 'source_unavailable'
               ELSE preliminary_state END AS source_state FROM canonical_raw
), canonical_health AS (
 SELECT g.tenant_id,g.game_id,1::bigint AS game_count,
   COUNT(*) FILTER (WHERE c.source_state='included') AS canonical_source_count,
   COUNT(*) FILTER (WHERE c.source_state='source_unavailable') AS unavailable_count,
   encode(sha256(convert_to(COALESCE(string_agg(
     jsonb_build_array(c.tenant_id,c.game_id,c.recording_generation,c.d1,c.d2,c.source_event_id,
       c.slot_version,c.play_row_id,c.play_row_version,c.source_fingerprint)::text,
     E'\n' ORDER BY c.tenant_id,c.game_id,c.d2,c.source_event_id)
     FILTER (WHERE c.source_state='included'),'accepted-play-slot-v1:empty'),'UTF8')),'hex')
     AS canonical_source_set_sha256
 FROM canonical_scope g LEFT JOIN canonical_s c
   ON c.tenant_id=g.tenant_id AND c.game_id=g.game_id
 GROUP BY g.tenant_id,g.game_id
)
SELECT s.* FROM sync_fence.stats_primitive_sources s
 JOIN canonical_s c ON c.tenant_id=s.tenant_id AND c.game_id=s.game_id
   AND c.source_event_id=s.source_event_id AND c.recording_generation=s.recording_generation
   AND c.d1=s.d1 AND c.d2=s.d2 AND c.slot_version=s.slot_version
   AND c.play_row_id=s.play_row_id AND c.play_row_version=s.play_row_version
   AND c.source_fingerprint=s.source_fingerprint AND c.artifact_sha256=s.artifact_sha256
   AND c.source_state='included'
WHERE s.tenant_id=p_tenant_id AND s.game_id=p_game_id AND s.fact_version_id=prior.id) original_members)<>prior.source_count
 OR (SELECT count(*) FROM sync_fence.stats_primitive_sources s
 WHERE s.tenant_id=p_tenant_id AND s.game_id=p_game_id
 AND s.fact_version_id=prior.id)<>prior.source_count
 THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 new_id:=pg_catalog.gen_random_uuid();
 UPDATE sync_fence.stats_fact_versions SET
 is_current=false,invalidated_at=pg_catalog.clock_timestamp()
 WHERE tenant_id=p_tenant_id AND game_id=p_game_id AND id=prior.id
 AND is_current AND invalidated_at IS NULL AND revision=prior.revision
 AND source_set_sha256=prior.source_set_sha256;
 IF NOT FOUND THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 INSERT INTO sync_fence.stats_fact_versions(
 tenant_id,game_id,id,model_sha256,rule_sha256,
 t5_artifact_set_sha256,source_set_sha256,source_count,revision,last_generation,last_d1,last_d2,
 updated_at,computed_metric_keys,is_current,completion_state,completion_receipt_id,
 public_pointer_receipt_id,created_at,invalidated_at)
 VALUES(prior.tenant_id,prior.game_id,new_id,prior.model_sha256,prior.rule_sha256,
 prior.t5_artifact_set_sha256,prior.source_set_sha256,prior.source_count,prior.revision+1,
 prior.last_generation,prior.last_d1,prior.last_d2,pg_catalog.clock_timestamp(),prior.computed_metric_keys,
 true,CASE WHEN action='end' THEN 'confirmed_ended' ELSE 'current_open' END,
 CASE WHEN action='end' THEN lifecycle_stamp.receipt_id ELSE NULL END,
 CASE WHEN action='end' THEN lifecycle_stamp.receipt_id ELSE NULL END,
 pg_catalog.clock_timestamp(),NULL);
 INSERT INTO sync_fence.stats_primitive_sources(tenant_id,game_id,fact_version_id,source_event_id,play_row_id,recording_generation,d1,d2,slot_version,play_row_version,provider_kind,attempt_id,phase_id,wire_d4,source_fingerprint,checkpoint_id,checkpoint_revision,checkpoint_digest,frame_digest,evaluation_sha256,artifact_sha256,rule_sha256,metric_states,computed_metric_keys,saved_at) SELECT original.tenant_id,original.game_id,new_id,original.source_event_id,original.play_row_id,original.recording_generation,original.d1,original.d2,original.slot_version,original.play_row_version,original.provider_kind,original.attempt_id,original.phase_id,original.wire_d4,original.source_fingerprint,original.checkpoint_id,original.checkpoint_revision,original.checkpoint_digest,original.frame_digest,original.evaluation_sha256,original.artifact_sha256,original.rule_sha256,original.metric_states,original.computed_metric_keys,original.saved_at FROM sync_fence.stats_primitive_sources original WHERE original.tenant_id=p_tenant_id AND original.game_id=p_game_id AND original.fact_version_id=prior.id;
 INSERT INTO sync_fence.stats_primitive_facts(tenant_id,game_id,fact_version_id,source_event_id,metric_id,player_id,credit_ordinal,state,amount) SELECT original.tenant_id,original.game_id,new_id,original.source_event_id,original.metric_id,original.player_id,original.credit_ordinal,original.state,original.amount FROM sync_fence.stats_primitive_facts original WHERE original.tenant_id=p_tenant_id AND original.game_id=p_game_id AND original.fact_version_id=prior.id;


 -- 内容を再計算せず、保存済み唯一T5応答の全creditと実fact集合を双方向比較する。
 IF EXISTS(SELECT 1 FROM sync_fence.stats_primitive_sources s
 WHERE s.tenant_id=p_tenant_id AND s.game_id=p_game_id AND s.fact_version_id=new_id
 AND s.evaluation_sha256 IS DISTINCT FROM pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 s.metric_states::text,'UTF8')),'hex')) OR EXISTS(
 WITH expected_credits AS (
  SELECT s.source_event_id,m.key AS metric_id,(c.value->>'player_id')::uuid AS player_id,
  c.ordinality-1 AS credit_ordinal,'available'::text AS state,(c.value->>'quantity')::numeric AS amount
  FROM sync_fence.stats_primitive_sources s
  CROSS JOIN LATERAL pg_catalog.jsonb_each(s.metric_states->'metrics') m
  CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(m.value->'credits') WITH ORDINALITY c
  WHERE s.tenant_id=p_tenant_id AND s.game_id=p_game_id AND s.fact_version_id=new_id
 ), actual_credits AS (
  SELECT f.source_event_id,f.metric_id,f.player_id,f.credit_ordinal,f.state,f.amount
  FROM sync_fence.stats_primitive_facts f WHERE f.tenant_id=p_tenant_id AND f.game_id=p_game_id
  AND f.fact_version_id=new_id
 )
 (SELECT * FROM expected_credits EXCEPT SELECT * FROM actual_credits)
 UNION ALL (SELECT * FROM actual_credits EXCEPT SELECT * FROM expected_credits)
 ) THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;

 INSERT INTO sync_fence.game_lifecycle_heads(tenant_id,game_id,last_version,is_finished,active_end_event_id,
 active_receipt_id,active_stats_version_id,last_control_event_id,updated_at)
 VALUES(p_tenant_id,p_game_id,(next_lifecycle->>'lastVersion')::bigint,action='end',
 CASE WHEN action='end' THEN own_event.id ELSE NULL END,
 CASE WHEN action='end' THEN lifecycle_stamp.receipt_id ELSE NULL END,
 CASE WHEN action='end' THEN new_id ELSE NULL
 END,own_event.id,pg_catalog.clock_timestamp())
 ON CONFLICT(tenant_id,game_id) DO UPDATE SET last_version=EXCLUDED.last_version,
 is_finished=EXCLUDED.is_finished,active_end_event_id=EXCLUDED.active_end_event_id,
 active_receipt_id=EXCLUDED.active_receipt_id,active_stats_version_id=EXCLUDED.active_stats_version_id,
 last_control_event_id=EXCLUDED.last_control_event_id,updated_at=EXCLUDED.updated_at;
 UPDATE public.games SET status=next_lifecycle->>'status'
 WHERE tenant_id=p_tenant_id AND id=p_game_id AND status=game_row.status
 AND trashed_at IS NULL AND import_batch_id IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object('eventId',own_event.id::text,
 'receiptId',lifecycle_stamp.receipt_id::text,'frameId',lifecycle_stamp.frame_id::text,
 'factVersionId',new_id::text,'lifecycle',next_lifecycle)::text;

END;
$lifecycle$;

ALTER FUNCTION sync_right_api.consume_game_lifecycle(uuid, uuid, uuid, bytea, uuid, uuid, text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.consume_game_lifecycle(uuid, uuid, uuid, bytea, uuid, uuid, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.consume_game_lifecycle(uuid, uuid, uuid, bytea, uuid, uuid, text) TO pitchlog_app;
