-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:prepare_nonplay_undo(uuid, uuid, uuid, bytea, uuid, uuid, text)

CREATE FUNCTION sync_right_api.prepare_nonplay_undo(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_request_json text)
RETURNS TABLE(prepared boolean) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $nonplay$
DECLARE stamp sync_fence.nonplay_write_admissions%ROWTYPE; own_xid text; p jsonb;
 cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; before_cp jsonb; after_cp jsonb; expected_content jsonb; target_id uuid; own_event public.operation_events%ROWTYPE; target_event public.operation_events%ROWTYPE; target_play public.play_rows%ROWTYPE;
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

 IF stamp.state<>'right_verified' OR p->'frame_id' IS NULL
 OR p->'before_source'->'checkpoint'->'ref' IS NULL
 OR p->'after_source'->'checkpoint'->'ref' IS NULL THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation AND c.state='current'
 FOR UPDATE;
 before_cp:=p->'before_source'->'checkpoint';
 after_cp:=p->'after_source'->'checkpoint';
 target_id:=(p->'target'->'source'->>'eventId')::uuid;
 SELECT e.* INTO STRICT own_event FROM public.operation_events e
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.event_slots s ON (s.tenant_id,s.game_id,s.generation,s.d1)
 =(e.tenant_id,e.game_id,e.generation,e.d1)
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.id=(p->>'event_id')::uuid AND e.d5=stamp.d5
 AND e.generation=stamp.internal_generation AND e.event_kind='undo'
 AND e.ledger_kind='accepted' AND l.kind='accepted'
 AND l.source_fingerprint=stamp.event_fingerprint AND l.retired_at IS NULL
 AND l.import_batch_id IS NULL AND e.d2 IS NULL AND e.state_diff IS NULL
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND NOT e.migration_unverified FOR SHARE OF e;
 SELECT e.* INTO STRICT target_event FROM public.operation_events e
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.id=target_id
 AND e.ledger_kind='accepted' AND e.event_kind='play_input'
 AND l.kind='accepted' AND l.source_fingerprint=p->'target'->'source'->>'fingerprint'
 AND e.generation=own_event.target_generation AND e.d1=own_event.target_d1
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL AND NOT e.is_tombstone
 AND NOT e.migration_unverified FOR SHARE OF e;
 IF (cp.content->>'version' IS DISTINCT FROM '3' AND cp.content IS DISTINCT FROM
before_cp)
 OR pg_catalog.to_jsonb(cp) IS DISTINCT FROM p->'storage'->'row'
 OR own_event.payload->'calculation'->'response' IS DISTINCT FROM p->'response'
 OR own_event.payload->'expectedCheckpoint' IS DISTINCT FROM before_cp->'ref'
 OR own_event.payload->>'artifactSha256' IS DISTINCT FROM p->>'artifact_sha256'
 OR own_event.d1 IS DISTINCT FROM (before_cp->'content'->>'d3')::bigint+1
 OR own_event.payload->'calculation'->'request'->'current' IS DISTINCT FROM
 before_cp->'content'->'restored'->'current'
 OR p->'target' IS DISTINCT FROM before_cp->'content'->'activeHead'
 OR p->'after_source'->'activeStack' IS DISTINCT FROM
 (p->'before_source'->'activeStack')-0
 OR after_cp->'content'->'restored' IS DISTINCT FROM
 p->'before_source'->'activeStack'->0->'beforeContext'
 OR after_cp->'content'->'nextPhysicalPlayNumber' IS DISTINCT FROM
 before_cp->'content'->'nextPhysicalPlayNumber'
 OR (after_cp->'ref'->>'revision')::bigint<>cp.revision+1
 OR (after_cp->'content'->>'activeDepth')::bigint<>
 (before_cp->'content'->>'activeDepth')::bigint-1
 THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 SELECT r.* INTO STRICT target_play FROM public.play_rows r
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id
 AND r.id=(p->'target'->>'playId')::uuid AND r.source_event_id=target_event.id
 AND r.hidden_at IS NULL AND r.import_batch_id IS NULL
 AND NOT r.migration_unverified FOR UPDATE;
 IF target_play.play_number IS DISTINCT FROM
(p->'target'->>'physicalPlayNumber')::bigint
 OR (SELECT pg_catalog.max(r.play_number)+1 FROM public.play_rows r
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id) IS DISTINCT FROM
 (before_cp->'content'->>'nextPhysicalPlayNumber')::bigint
 OR EXISTS(SELECT 1 FROM sync_fence.nonplay_write_admissions n WHERE n.tenant_id=p_tenant_id
 AND n.game_id=p_game_id AND n.state='consumed' AND n.target_event_id=target_id)
 THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 -- 新版の全metaは元contentから閉じた変更集合だけで構成する。
 expected_content:=(before_cp->'content')||pg_catalog.jsonb_build_object(
 'd3',own_event.d1::text,'d1Head',pg_catalog.jsonb_build_object(
 'kind','accepted-event','source',after_cp->'content'->'projectionHead'->'source'),
 'projectionHead',pg_catalog.jsonb_build_object('kind','d1-event','source',
 pg_catalog.jsonb_build_object('eventId',own_event.id::text,'gameId',p_game_id::text,
 'generation',stamp.wire_d4,'d1',own_event.d1::text,'d5',own_event.d5::text,
 'fingerprint',stamp.event_fingerprint,'eventKind','undo')),
 'activeHead',CASE WHEN pg_catalog.jsonb_array_length(
 p->'after_source'->'activeStack')=0 THEN 'null'::jsonb ELSE
 p->'after_source'->'activeStack'->0->'play' END,
 'activeDepth',pg_catalog.jsonb_array_length(p->'after_source'->'activeStack')::text,
 'historyVersion',((before_cp->'content'->>'historyVersion')::bigint+1)::text,
 'restored',p->'before_source'->'activeStack'->0->'beforeContext');
 IF after_cp->'content' IS DISTINCT FROM expected_content
 OR after_cp->'ref'->>'id' IS DISTINCT FROM before_cp->'ref'->>'id'
 OR p->>'source_fingerprint' IS DISTINCT FROM stamp.event_fingerprint
 OR p->'event_original'->'payload' IS DISTINCT FROM own_event.payload
 OR p->'event_original'->>'d4' IS DISTINCT FROM stamp.wire_d4
 OR p->'event_original'->>'game_id' IS DISTINCT FROM p_game_id::text
 OR p->'event_original'->>'d5' IS DISTINCT FROM own_event.d5::text
 OR (p->'event_original'->>'d1')::bigint IS DISTINCT FROM own_event.d1
 OR p->'event_original'->'target_reference'->>'game' IS DISTINCT FROM p_game_id::text
 OR (p->'event_original'->'target_reference'->>'d1')::bigint IS DISTINCT FROM
 target_event.d1
 OR p->'event_original'->'target_reference'->>'d4' IS DISTINCT FROM
 p->'target'->'source'->>'generation'
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations old
 JOIN public.recording_generations cur ON cur.tenant_id=old.tenant_id
 AND cur.game_id=old.game_id WHERE old.tenant_id=p_tenant_id AND old.game_id=p_game_id
 AND old.generation=target_event.generation AND old.kind='normal' AND cur.kind='normal'
 AND cur.generation=stamp.internal_generation
 AND old.issuance_order<=cur.issuance_order)
 THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 IF cp.content->>'version'='3' AND (
 before_cp->'content'->'restored'->'current' IS DISTINCT FROM cp.content->'after'
 OR before_cp->'content'->'restored'->'rules' IS DISTINCT FROM cp.content->'rules'
 OR before_cp->'content'->'restored'->'lineup' IS DISTINCT FROM cp.content->'lineup'
 OR before_cp->'content'->'restored'->'participants' IS DISTINCT FROM
 cp.content->'participants'
 OR before_cp->'content'->'restored'->'runners' IS DISTINCT FROM cp.content->'runners'
 OR before_cp->'content'->'restored'->'lastPlayEvaluation' IS DISTINCT FROM
 cp.content->'t2'
 OR cp.content->'last_source'->>'id' IS DISTINCT FROM target_event.id::text
 OR (before_cp->'ref'->>'id')::uuid IS DISTINCT FROM cp.id
 OR (before_cp->'ref'->>'revision')::bigint IS DISTINCT FROM cp.revision
 ) THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 UPDATE sync_fence.nonplay_write_admissions SET state='evaluated',frame_id=(p->>'frame_id')::uuid,
 frame_digest=p->>'frame_digest',artifact_sha256=p->>'artifact_sha256',
 source_event_id=own_event.id,source_d1=own_event.d1,target_event_id=target_id,
 target_generation=target_event.generation,target_d1=target_event.d1,
 target_play_id=target_play.id,checkpoint_digest=cp.content_digest,
 checkpoint_id=cp.id,checkpoint_revision=cp.revision,
 preparation_json=p_request_json,preparation=p
 WHERE (tenant_id,attempt_id,phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND state='right_verified' AND transaction_id=own_xid;
 IF NOT FOUND THEN RAISE EXCEPTION 'nonplay prefix rejected' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT true;

END;
$nonplay$;

ALTER FUNCTION sync_right_api.prepare_nonplay_undo(uuid, uuid, uuid, bytea, uuid, uuid, text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.prepare_nonplay_undo(uuid, uuid, uuid, bytea, uuid, uuid, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.prepare_nonplay_undo(uuid, uuid, uuid, bytea, uuid, uuid, text) TO pitchlog_app;
