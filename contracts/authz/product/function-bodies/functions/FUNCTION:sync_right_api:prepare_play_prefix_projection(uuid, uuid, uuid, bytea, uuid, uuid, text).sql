-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:prepare_play_prefix_projection(uuid, uuid, uuid, bytea, uuid, uuid, text)

CREATE FUNCTION sync_right_api.prepare_play_prefix_projection(
p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_preparation_json text)
RETURNS TABLE(prepared boolean) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $ordinary$
DECLARE p jsonb; before_cp jsonb; after_cp jsonb; source_row record;
 stamp sync_fence.ordinary_pitch_write_admissions%ROWTYPE;
 current_cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 own_xid text; row_xmin text; previous_d1 bigint;
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
 IF p_preparation_json IS NULL THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
 p:=p_preparation_json::jsonb;
 IF pg_catalog.jsonb_typeof(p) IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.jsonb_object_keys(p) k)
 IS DISTINCT FROM ARRAY['artifact_sha256','checkpoint','frame_digest','frame_id',
 'history_entry','next_checkpoint','play_row','roster','source']::text[]
 THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
 before_cp:=p->'checkpoint'; after_cp:=p->'next_checkpoint';
 SELECT s.* INTO STRICT stamp FROM sync_fence.ordinary_pitch_write_admissions s
 JOIN sync_fence.writer_bindings b
 ON (b.tenant_id,b.attempt_id,b.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 JOIN sync_fence.writer_admissions a
 ON (a.tenant_id,a.attempt_id,a.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND s.state='right_verified' AND s.transaction_id=own_xid
 AND b.state='open' AND b.expires_at>pg_catalog.clock_timestamp()
 AND b.transaction_id=own_xid AND a.transaction_id=own_xid AND a.lease_id=b.lease_id
 AND a.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 AND s.tenant_id IS NOT DISTINCT FROM b.tenant_id AND s.attempt_id IS NOT DISTINCT FROM b.attempt_id AND s.phase_id IS NOT DISTINCT FROM b.phase_id AND s.authority_id IS NOT DISTINCT FROM b.authority_id AND s.control_instance IS NOT DISTINCT FROM b.control_instance AND s.business_instance IS NOT DISTINCT FROM b.business_instance AND s.restore_epoch IS NOT DISTINCT FROM b.restore_epoch AND s.control_version IS NOT DISTINCT FROM b.control_version AND s.issuer IS NOT DISTINCT FROM b.issuer AND s.lease_id IS NOT DISTINCT FROM b.lease_id AND s.device_id IS NOT DISTINCT FROM b.device_id AND s.game_id IS NOT DISTINCT FROM b.game_id AND s.wire_d4 IS NOT DISTINCT FROM b.wire_d4 AND s.internal_generation IS NOT DISTINCT FROM b.internal_generation AND s.recovery_generation IS NOT DISTINCT FROM b.recovery_generation AND s.codec_version IS NOT DISTINCT FROM b.codec_version AND s.request_fingerprint IS NOT DISTINCT FROM b.request_fingerprint AND s.d5 IS NOT DISTINCT FROM b.d5 AND s.event_fingerprint IS NOT DISTINCT FROM b.event_fingerprint AND s.system_identifier IS NOT DISTINCT FROM b.system_identifier AND s.database_oid IS NOT DISTINCT FROM b.database_oid AND s.postmaster_started_at IS NOT DISTINCT FROM b.postmaster_started_at AND s.backend_pid IS NOT DISTINCT FROM b.backend_pid AND s.backend_start IS NOT DISTINCT FROM b.backend_start AND s.transaction_id IS NOT DISTINCT FROM b.transaction_id AND s.nonce_digest IS NOT DISTINCT FROM b.nonce_digest AND s.expires_at IS NOT DISTINCT FROM b.expires_at FOR UPDATE OF s;
 SELECT e.* INTO STRICT source_row FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.id=(p->'source'->>'id')::uuid AND e.d5=stamp.d5
 AND e.generation=stamp.internal_generation AND e.ledger_kind='accepted'
 AND e.event_kind='play_input' AND NOT e.is_tombstone AND e.d1>0 AND e.d2 IS NOT NULL
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified;
 previous_d1:=source_row.d1-1;
 IF source_row.payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v2'
 OR source_row.payload->'calculation'->>'formatVersion' IS DISTINCT FROM
'play-prefix-calculation-v2'
 OR source_row.payload->'calculation'->>'artifactSha256' IS DISTINCT FROM
p->>'artifact_sha256'
 OR p->'source' IS DISTINCT FROM pg_catalog.jsonb_build_object(
 'id',source_row.id::text,'tenant_id',p_tenant_id::text,'game_id',p_game_id::text,
 'generation',source_row.generation::text,'d1',source_row.d1::text,
 'd2',source_row.d2::text,'d5',source_row.d5::text,
'source_fingerprint',stamp.event_fingerprint,'event_fingerprint',stamp.event_fingerprint)
 OR after_cp->'last_source' IS DISTINCT FROM p->'source'
 OR before_cp->>'state' IS DISTINCT FROM 'current' OR after_cp->>'state' IS
DISTINCT FROM 'current'
 OR before_cp->>'wire_d4' IS DISTINCT FROM stamp.wire_d4 OR after_cp->>'wire_d4'
IS DISTINCT FROM stamp.wire_d4
 OR (before_cp->>'confirmed_watermark')::bigint IS DISTINCT FROM previous_d1
 OR (before_cp->>'applied_watermark')::bigint IS DISTINCT FROM previous_d1
 OR (after_cp->>'confirmed_watermark')::bigint IS DISTINCT FROM source_row.d1
 OR (after_cp->>'applied_watermark')::bigint IS DISTINCT FROM source_row.d1
 OR (before_cp->>'internal_generation')::bigint IS DISTINCT FROM
stamp.internal_generation
 OR (after_cp->>'internal_generation')::bigint IS DISTINCT FROM
stamp.internal_generation
 OR (before_cp->>'recovery_generation')::bigint IS DISTINCT FROM
stamp.recovery_generation
 OR (after_cp->>'recovery_generation')::bigint IS DISTINCT FROM
stamp.recovery_generation
 OR after_cp->>'id' IS DISTINCT FROM before_cp->>'id'
 OR (after_cp->>'revision')::bigint IS DISTINCT FROM
(before_cp->>'revision')::bigint+1
 OR after_cp->>'history_version' IS DISTINCT FROM before_cp->>'history_version'
 OR after_cp->'prefix_ref'->>'generation' IS DISTINCT FROM stamp.wire_d4
 OR before_cp->'prefix_ref'->>'generation' IS DISTINCT FROM stamp.wire_d4
 OR after_cp->'prefix_ref'->>'tenantId' IS DISTINCT FROM p_tenant_id::text
 OR before_cp->'prefix_ref'->>'tenantId' IS DISTINCT FROM p_tenant_id::text
 OR after_cp->'prefix_ref'->>'gameId' IS DISTINCT FROM p_game_id::text
 OR before_cp->'prefix_ref'->>'gameId' IS DISTINCT FROM p_game_id::text
 OR (after_cp->'prefix_ref'->>'length')::bigint IS DISTINCT FROM
(before_cp->'prefix_ref'->>'length')::bigint+1
 OR before_cp->'after' IS DISTINCT FROM
source_row.payload->'calculation'->'request'->'t1'->'before'
 OR before_cp->'rules' IS DISTINCT FROM
source_row.payload->'calculation'->'request'->'rules'
 OR before_cp->'t2' IS DISTINCT FROM
source_row.payload->'calculation'->'request'->'source'->'t2'
 OR before_cp->'prefix_ref' IS DISTINCT FROM
(CASE WHEN before_cp->>'version'='1' THEN
source_row.payload->'calculation'->'response'->'value'->'previousPrefixRef'->'origin'
ELSE source_row.payload->'calculation'->'response'->'value'->'previousPrefixRef'
END)
 OR after_cp->'prefix_ref' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'nextPrefixRef'
 OR after_cp->'after' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'t1'->'after'
 OR after_cp->'rules' IS DISTINCT FROM before_cp->'rules'
 OR after_cp->'t2' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'t2'
 OR p->'history_entry' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'newHistoryEntry'
 OR p->'play_row'->>'source_event_id' IS DISTINCT FROM source_row.id::text
 OR p->'play_row'->>'game_id' IS DISTINCT FROM p_game_id::text
 OR p->'play_row'->>'tenant_id' IS DISTINCT FROM p_tenant_id::text
 OR NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l WHERE l.tenant_id=p_tenant_id
 AND l.d5=stamp.d5 AND l.kind='accepted' AND
l.source_fingerprint=stamp.event_fingerprint
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL)
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations r WHERE
r.tenant_id=p_tenant_id
 AND r.game_id=p_game_id AND r.generation=stamp.internal_generation AND
r.kind='normal'
 AND r.holder_device=stamp.device_id::text AND r.revoked_at IS NULL AND
r.retired_at IS NULL
 AND r.recovery_generation=stamp.recovery_generation
 AND r.confirmed_watermark=source_row.d1 AND r.applied_prefix=source_row.d1)
 THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;

 IF after_cp->>'version' IS DISTINCT FROM '2'
 OR after_cp->>'artifact_sha256' IS DISTINCT FROM p->>'artifact_sha256'
 OR after_cp->'pa_start_source' IS DISTINCT FROM (CASE
 WHEN source_row.payload->'calculation'->'response'->'value'->'t1'
 ->>'plateAppearanceEnded'='true'
 THEN pg_catalog.jsonb_build_object('kind','confirmed-play','id',source_row.id::text)
 ELSE source_row.payload->'calculation'->'request'->'source'
 ->'responsibility'->'paStartSource' END)
 OR after_cp->'bridge_origin' IS DISTINCT FROM (CASE WHEN before_cp->>'version'='1'
 THEN source_row.payload->'calculation'->'request'->'source'->'bridge'
 ELSE before_cp->'bridge_origin' END)
 OR after_cp->'storage_anchor'->>'id' IS DISTINCT FROM before_cp->>'id'
 OR after_cp->'storage_anchor'->>'history_epoch' IS DISTINCT FROM
before_cp->>'history_version'
 OR after_cp->'prefix_ref'->>'version' IS DISTINCT FROM '2'
 OR after_cp->'prefix_ref'->>'scope' IS DISTINCT FROM 'play-prefix-v2'
 OR after_cp->'runners' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'runners'
 OR after_cp->'participants' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'participants'
 OR after_cp->'projection_snapshot'->'play_row' IS DISTINCT FROM p->'play_row'
 OR pg_catalog.jsonb_typeof(after_cp->'projection_snapshot'->'play_runners') IS
DISTINCT FROM 'array'
 OR pg_catalog.jsonb_array_length(after_cp->'projection_snapshot'->'play_runners')
 IS DISTINCT FROM pg_catalog.jsonb_array_length(
 source_row.payload->'calculation'->'request'->'source'->'runners')
 OR source_row.state_diff IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'newHistoryEntry'->'difference'
 OR source_row.payload->'calculation'->'request'->'playIdentity' IS DISTINCT FROM
pg_catalog.jsonb_build_object('eventId',source_row.id::text,'d5',source_row.d5::text,
 'playId',p->'play_row'->>'id')
 OR source_row.payload->'calculation'->'request'->'source'->'responsibility'->>'kind'
 IS DISTINCT FROM 'no-change'
 THEN RAISE EXCEPTION 'play prefix preparation rejected' USING ERRCODE='42501';
END IF;

 IF source_row.payload->'calculation'->'request'->'source'
 ->'responsibility'->'paStartSource'
 IS DISTINCT FROM (CASE WHEN before_cp->>'version'='1' THEN
 pg_catalog.jsonb_build_object('kind','started-game','id',p_game_id::text)
 ELSE before_cp->'pa_start_source' END)
 OR EXISTS(SELECT 1 FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.generation=stamp.internal_generation AND e.d1<=previous_d1
 AND (e.ledger_kind<>'accepted' OR e.is_tombstone OR e.replaced_at IS NOT NULL
 OR e.retired_at IS NOT NULL OR e.import_batch_id IS NOT NULL
 OR e.legacy_row_identifier IS NOT NULL OR e.migration_unverified))
 OR EXISTS(SELECT 1 FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.generation=stamp.internal_generation AND e.d1<=previous_d1
 AND e.event_kind<>'play_input' AND e.d1>(CASE
 WHEN before_cp->>'version'='2'
 AND before_cp->'pa_start_source'->>'kind'='confirmed-play'
 THEN (SELECT z.d1 FROM public.operation_events z WHERE z.tenant_id=p_tenant_id
 AND z.game_id=p_game_id AND z.generation=stamp.internal_generation
 AND z.id=(before_cp->'pa_start_source'->>'id')::uuid) ELSE 0 END))
 OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
 after_cp->'projection_snapshot'->'play_runners') r WHERE
 (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.jsonb_object_keys(r) k)
 IS DISTINCT FROM ARRAY['base','id','import_batch_id','play_id',
 'responsible_pitcher_id','retired_at','runner_id','status','status_source','tenant_id']::text[]
 OR r->>'tenant_id' IS DISTINCT FROM p_tenant_id::text
 OR r->>'play_id' IS DISTINCT FROM p->'play_row'->>'id'
 OR r->>'id' IS NULL OR r->'retired_at' IS DISTINCT FROM 'null'::jsonb
 OR r->'import_batch_id' IS DISTINCT FROM 'null'::jsonb
 OR NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
 source_row.payload->'calculation'->'request'->'source'->'runners') m
 WHERE r->>'base'=m->>'base' AND r->>'runner_id'=m->>'runnerId'
 AND r->>'responsible_pitcher_id'=m->>'responsiblePitcherId'
 AND r->>'status'='継続' AND r->>'status_source'='auto'
 AND source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'modality'='hold'
 AND source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->'destination'='null'::jsonb))
 THEN RAISE EXCEPTION 'play prefix source or runners rejected'
 USING ERRCODE='42501'; END IF;
 SELECT c.* INTO current_cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation FOR UPDATE;
 IF FOUND THEN
  IF current_cp.content IS DISTINCT FROM before_cp OR current_cp.roster IS
DISTINCT FROM p->'roster'
  OR current_cp.state IS DISTINCT FROM 'current' OR current_cp.content_digest IS
DISTINCT FROM before_cp->>'content_digest'
  THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
 ELSE
  IF previous_d1 NOT IN (0,1) THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
  IF previous_d1=0 AND EXISTS(SELECT 1 FROM public.operation_events e
   WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id AND e.id IS DISTINCT
FROM source_row.id)
   THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
  IF previous_d1=1 AND NOT EXISTS(SELECT 1 FROM public.operation_events e
   JOIN public.play_rows pr ON pr.tenant_id=e.tenant_id AND pr.source_event_id=e.id
   WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
   AND e.id=(before_cp->'last_source'->>'id')::uuid AND
e.generation=stamp.internal_generation
   AND e.d1=1 AND e.ledger_kind='accepted' AND NOT e.is_tombstone
   AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
   AND e.payload->>'formatVersion'='first-ball-play-v1'
   AND before_cp->'after'=e.payload->'calculation'->'response'->'value'->'t1'->'after'
   AND before_cp->'t2'=e.payload->'calculation'->'response'->'value'->'t2')
   THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM sync_fence.first_ball_write_admissions f
 WHERE f.tenant_id=p_tenant_id AND f.game_id=p_game_id AND f.d5=stamp.d5
 AND f.state IN ('device_verified','right_verified','consumed')) THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501';
END IF;
 UPDATE sync_fence.ordinary_pitch_write_admissions s SET state='evaluated',
checkpoint_id=(before_cp->>'id')::uuid,checkpoint_revision=(before_cp->>'revision')::bigint,
checkpoint_digest=before_cp->>'content_digest',prefix_length=(before_cp->'prefix_ref'->>'length')::bigint,
frame_id=(p->>'frame_id')::uuid,frame_digest=p->>'frame_digest',artifact_sha256=p->>'artifact_sha256',
 source_event_id=source_row.id,source_d1=source_row.d1,source_d2=source_row.d2,
 play_row_id=(p->'play_row'->>'id')::uuid,checkpoint_content=before_cp,
next_checkpoint_content=after_cp,roster_snapshot=p->'roster',history_entry=p->'history_entry',
 expected_play_row=p->'play_row'
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND s.state='right_verified' AND s.transaction_id=own_xid
 RETURNING s.xmin::text INTO row_xmin;
 IF NOT FOUND OR row_xmin::numeric IS DISTINCT FROM
pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 THEN RAISE EXCEPTION 'ordinary pitch admission rejected' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT true;
END;
$ordinary$;

ALTER FUNCTION sync_right_api.prepare_play_prefix_projection(uuid, uuid, uuid, bytea, uuid, uuid, text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.prepare_play_prefix_projection(uuid, uuid, uuid, bytea, uuid, uuid, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.prepare_play_prefix_projection(uuid, uuid, uuid, bytea, uuid, uuid, text) TO pitchlog_app;
