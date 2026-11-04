-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:consume_ordinary_projection(jsonb)

CREATE FUNCTION sync_right_api.consume_ordinary_projection(p_row jsonb)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $ordinary$
DECLARE s sync_fence.ordinary_pitch_write_admissions%ROWTYPE;
 own_xid text; row_xmin text; after_cp jsonb; source_row record; bootstrap boolean;
 saved_clock timestamptz;
BEGIN
 IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT
FROM 'pitchlog_sync_right_fn_owner'
 OR pg_catalog.pg_trigger_depth()<>1
 OR p_row->>'tenant_id' IS DISTINCT FROM
NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')
 THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 saved_clock:=pg_catalog.clock_timestamp();
 SELECT a.* INTO STRICT s FROM sync_fence.ordinary_pitch_write_admissions a
 JOIN sync_fence.writer_bindings b
 ON (a.tenant_id,a.attempt_id,a.phase_id)=(b.tenant_id,b.attempt_id,b.phase_id)
 JOIN sync_fence.writer_admissions wa
 ON (wa.tenant_id,wa.attempt_id,wa.phase_id)=(b.tenant_id,b.attempt_id,b.phase_id)
 WHERE a.tenant_id=(p_row->>'tenant_id')::uuid AND a.game_id=(p_row->>'game_id')::uuid
 AND a.source_event_id=(p_row->>'source_event_id')::uuid AND
a.play_row_id=(p_row->>'id')::uuid
 AND a.state='evaluated' AND a.consumed_at IS NULL AND a.transaction_id=own_xid
 AND b.state='open' AND b.expires_at>pg_catalog.clock_timestamp()
 AND b.transaction_id=own_xid AND wa.transaction_id=own_xid
 AND wa.lease_id=b.lease_id
 AND wa.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND a.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND b.backend_pid=pg_catalog.pg_backend_pid()
 AND b.postmaster_started_at=pg_catalog.pg_postmaster_start_time()
 AND b.database_oid=(SELECT d.oid::text FROM pg_catalog.pg_database d
 WHERE d.datname=pg_catalog.current_database())
 AND a.tenant_id IS NOT DISTINCT FROM b.tenant_id AND a.attempt_id IS NOT DISTINCT FROM b.attempt_id AND a.phase_id IS NOT DISTINCT FROM b.phase_id AND a.authority_id IS NOT DISTINCT FROM b.authority_id AND a.control_instance IS NOT DISTINCT FROM b.control_instance AND a.business_instance IS NOT DISTINCT FROM b.business_instance AND a.restore_epoch IS NOT DISTINCT FROM b.restore_epoch AND a.control_version IS NOT DISTINCT FROM b.control_version AND a.issuer IS NOT DISTINCT FROM b.issuer AND a.lease_id IS NOT DISTINCT FROM b.lease_id AND a.device_id IS NOT DISTINCT FROM b.device_id AND a.game_id IS NOT DISTINCT FROM b.game_id AND a.wire_d4 IS NOT DISTINCT FROM b.wire_d4 AND a.internal_generation IS NOT DISTINCT FROM b.internal_generation AND a.recovery_generation IS NOT DISTINCT FROM b.recovery_generation AND a.codec_version IS NOT DISTINCT FROM b.codec_version AND a.request_fingerprint IS NOT DISTINCT FROM b.request_fingerprint AND a.d5 IS NOT DISTINCT FROM b.d5 AND a.event_fingerprint IS NOT DISTINCT FROM b.event_fingerprint AND a.system_identifier IS NOT DISTINCT FROM b.system_identifier AND a.database_oid IS NOT DISTINCT FROM b.database_oid AND a.postmaster_started_at IS NOT DISTINCT FROM b.postmaster_started_at AND a.backend_pid IS NOT DISTINCT FROM b.backend_pid AND a.backend_start IS NOT DISTINCT FROM b.backend_start AND a.transaction_id IS NOT DISTINCT FROM b.transaction_id AND a.nonce_digest IS NOT DISTINCT FROM b.nonce_digest AND a.expires_at IS NOT DISTINCT FROM b.expires_at FOR UPDATE OF a;
 SELECT e.* INTO STRICT source_row FROM public.operation_events e
 WHERE e.tenant_id=s.tenant_id AND e.game_id=s.game_id AND e.id=s.source_event_id
 AND e.generation=s.internal_generation AND e.d1=s.source_d1 AND e.d2=s.source_d2
 AND e.d5=s.d5 AND e.ledger_kind='accepted' AND NOT e.is_tombstone
 AND e.event_kind='play_input'
 AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND e.import_batch_id IS NULL AND e.legacy_row_identifier IS NULL
 AND NOT e.migration_unverified
 AND e.payload->>'formatVersion'='ordinary-pitch-play-v1';
 IF EXISTS(SELECT 1 FROM sync_fence.first_ball_write_admissions f
 WHERE f.tenant_id=s.tenant_id AND f.game_id=s.game_id AND f.d5=s.d5
 AND f.state IN ('device_verified','right_verified','consumed'))
 OR NOT EXISTS(SELECT 1 FROM public.rg1_restore_gate g WHERE g.singleton_id=1
 AND g.state='open' AND g.recovery_generation=s.recovery_generation)
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations r WHERE
r.tenant_id=s.tenant_id
 AND r.game_id=s.game_id AND r.generation=s.internal_generation AND r.kind='normal'
 AND r.holder_device=s.device_id::text AND r.revoked_at IS NULL AND r.retired_at
IS NULL
 AND r.recovery_generation=s.recovery_generation AND r.confirmed_watermark=s.source_d1
 AND r.applied_prefix=s.source_d1)
 OR NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l
 WHERE l.tenant_id=s.tenant_id AND l.d5=s.d5 AND l.kind='accepted'
 AND l.source_fingerprint=s.event_fingerprint AND l.retired_at IS NULL
 AND l.import_batch_id IS NULL) THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.trusted_devices d WHERE d.tenant_id=s.tenant_id
 AND d.device_id=s.device_id AND d.revoked_at IS NULL FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
 IF s.expected_play_row IS DISTINCT FROM p_row THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
 bootstrap:=NOT EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=s.tenant_id AND c.game_id=s.game_id
 AND c.internal_generation=s.internal_generation);
 after_cp:=s.next_checkpoint_content;
 INSERT INTO
sync_fence.ordinary_pitch_checkpoints(tenant_id,game_id,internal_generation,id,
 revision,history_version,recovery_generation,confirmed_watermark,applied_watermark,
 content_digest,content,roster,state,saved_at)
 VALUES(s.tenant_id,s.game_id,s.internal_generation,s.checkpoint_id,
(after_cp->>'revision')::bigint,(after_cp->>'history_version')::bigint,s.recovery_generation,
s.source_d1,s.source_d1,after_cp->>'content_digest',after_cp,s.roster_snapshot,
'current',saved_clock)
 ON CONFLICT(tenant_id,game_id,internal_generation) DO UPDATE
 SET revision=EXCLUDED.revision,confirmed_watermark=EXCLUDED.confirmed_watermark,
 applied_watermark=EXCLUDED.applied_watermark,content_digest=EXCLUDED.content_digest,
 content=EXCLUDED.content,roster=EXCLUDED.roster,saved_at=EXCLUDED.saved_at
 WHERE ordinary_pitch_checkpoints.id=s.checkpoint_id
 AND ordinary_pitch_checkpoints.revision=s.checkpoint_revision
 AND ordinary_pitch_checkpoints.content_digest=s.checkpoint_digest
 AND ordinary_pitch_checkpoints.content=s.checkpoint_content
 AND ordinary_pitch_checkpoints.state='current';
 IF NOT FOUND THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
 IF bootstrap AND s.source_d1=2 AND s.prefix_length=1 THEN
 INSERT INTO sync_fence.ordinary_pitch_history(tenant_id,game_id,internal_generation,
 history_version,source_event_id,d1,d2,entry)
 SELECT e.tenant_id,e.game_id,e.generation,(after_cp->>'history_version')::bigint,
e.id,e.d1,e.d2,pg_catalog.jsonb_build_object('kind','confirmed-play','difference',e.state_diff)
 FROM public.operation_events e
 WHERE e.tenant_id=s.tenant_id AND e.game_id=s.game_id
 AND e.id=(s.checkpoint_content->'last_source'->>'id')::uuid
 AND e.d1=1 AND e.payload->>'formatVersion'='first-ball-play-v1';
 IF NOT FOUND THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
 END IF;
 INSERT INTO sync_fence.ordinary_pitch_history(tenant_id,game_id,internal_generation,
 history_version,source_event_id,d1,d2,entry)
VALUES(s.tenant_id,s.game_id,s.internal_generation,(after_cp->>'history_version')::bigint,
 s.source_event_id,s.source_d1,s.source_d2,s.history_entry);
 UPDATE sync_fence.ordinary_pitch_write_admissions a SET state='consumed',
 consumed_at=saved_clock
 WHERE (a.tenant_id,a.attempt_id,a.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 AND a.transaction_id=own_xid AND a.state='evaluated' AND a.frame_id=s.frame_id
 RETURNING a.xmin::text INTO row_xmin;
 IF NOT FOUND OR row_xmin::numeric IS DISTINCT FROM
pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
END;
$ordinary$;

ALTER FUNCTION sync_right_api.consume_ordinary_projection(jsonb) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.consume_ordinary_projection(jsonb) FROM PUBLIC,pitchlog_app;
