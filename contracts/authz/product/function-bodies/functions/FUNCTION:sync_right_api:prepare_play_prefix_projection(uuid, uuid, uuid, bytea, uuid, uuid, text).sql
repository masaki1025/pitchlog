-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:prepare_play_prefix_projection(uuid, uuid, uuid, bytea, uuid, uuid, text)

CREATE FUNCTION sync_right_api.prepare_play_prefix_projection(
p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_preparation_json text)
RETURNS TABLE(prepared boolean) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $dispatch$
BEGIN
 IF p_preparation_json::jsonb->'next_checkpoint'->>'formatVersion'='nonplay-normal-storage-v1' THEN
DECLARE p jsonb; before_cp jsonb; after_cp jsonb; source_row record;
 stamp sync_fence.ordinary_pitch_write_admissions%ROWTYPE;
 current_cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 own_xid text; row_xmin text; previous_d1 bigint; q jsonb; v jsonb; expected_cp jsonb; expected_head jsonb; expected_context jsonb;
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

 q:=source_row.payload->'calculation'->'request';
 v:=source_row.payload->'calculation'->'response'->'value';
 SELECT c.* INTO STRICT current_cp FROM sync_fence.ordinary_pitch_checkpoints c
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=stamp.internal_generation AND c.state='current' FOR UPDATE;
 expected_head:=pg_catalog.jsonb_build_object('eventId',source_row.id::text,
 'gameId',p_game_id::text,'generation',stamp.wire_d4,'d1',source_row.d1::text,
 'd5',source_row.d5::text,'fingerprint',stamp.event_fingerprint,'eventKind',
 'play_input');
 expected_context:=pg_catalog.jsonb_build_object('current',v->'t1'->'after',
 'rules',before_cp->'content'->'restored'->'rules',
 'rulesDigest',before_cp->'content'->'restored'->'rulesDigest',
 'layoutDigest',before_cp->'content'->'restored'->'layoutDigest',
 'rosterDigest',v->'rosterDigest','lineup',v->'lineup','participants',v->'participants',
 'runners',v->'runners','responsibility',v->'nextResponsibility','lastPlayEvaluation',
 v->'t2');
 IF before_cp->'content'->'restored' ? 'substitutionState' THEN
 IF pg_catalog.jsonb_typeof(
 after_cp->'checkpoint'->'content'->'restored'->'substitutionState')
 IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'play prefix admission rejected' USING ERRCODE='42501'; END IF;
 expected_context:=expected_context||pg_catalog.jsonb_build_object(
 'substitutionState',
 after_cp->'checkpoint'->'content'->'restored'->'substitutionState');
 ELSIF after_cp->'checkpoint'->'content'->'restored' ? 'substitutionState'
 THEN RAISE EXCEPTION 'play prefix admission rejected' USING ERRCODE='42501'; END IF;
 expected_cp:=before_cp->'content'||pg_catalog.jsonb_build_object(
 'd3',source_row.d1::text,'d1Head',pg_catalog.jsonb_build_object('kind',
 'accepted-event','source',expected_head),
 'projectionHead',pg_catalog.jsonb_build_object('kind','d1-event','source',
 expected_head),
 'activeHead',pg_catalog.jsonb_build_object('source',expected_head,'playId',
 p->'play_row'->>'id',
 'd2',source_row.d2::text,'physicalPlayNumber',p->'play_row'->>'play_number'),
 'activeDepth',((before_cp->'content'->>'activeDepth')::bigint+1)::text,
 'historyVersion',((before_cp->'content'->>'historyVersion')::bigint+1)::text,
 'nextPhysicalPlayNumber',
 ((before_cp->'content'->>'nextPhysicalPlayNumber')::bigint+1)::text,
 'restored',expected_context);
 IF source_row.payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v3'
 OR source_row.payload->'calculation'->>'formatVersion' IS DISTINCT FROM
 'nonplay-prefix-calculation-v1'
 OR source_row.payload->'calculation'->>'artifactSha256' IS DISTINCT FROM
 p->>'artifact_sha256'
 OR q->>'version' IS DISTINCT FROM 'nonplay-continuation-v1'
 OR q->'source'->'checkpoint' IS DISTINCT FROM before_cp
 OR q->'prefixRef' IS DISTINCT FROM before_cp->'ref'
 OR q->'rules' IS DISTINCT FROM before_cp->'content'->'restored'->'rules'
 OR q->'t1'->'before' IS DISTINCT FROM before_cp->'content'->'restored'->'current'
 OR q->'t1'->>'resultId' IS DISTINCT FROM 'batting-result.ball'
 OR q->'sourcePosition' IS DISTINCT FROM pg_catalog.jsonb_build_object(
 'd1',source_row.d1::text,'d2',source_row.d2::text,'appliedWatermark',previous_d1::text)
 OR q->'playIdentity' IS DISTINCT FROM pg_catalog.jsonb_build_object(
 'eventId',source_row.id::text,'d5',source_row.d5::text,'playId',p->'play_row'->>'id')
 OR v->'previousPrefixRef' IS DISTINCT FROM before_cp->'ref'
 OR v->'nextPrefixRef' IS DISTINCT FROM q->'nextCheckpoint'
 OR v->'playIdentity' IS DISTINCT FROM q->'playIdentity'
 OR v->'sourcePosition' IS DISTINCT FROM q->'sourcePosition'
 OR v->>'executionArtifactSha256' IS DISTINCT FROM p->>'artifact_sha256'
 OR before_cp->>'formatVersion' IS DISTINCT FROM 'nonplay-prefix-checkpoint-v1'
 OR before_cp->'content'->'scope' IS DISTINCT FROM pg_catalog.jsonb_build_object(
 'tenantId',p_tenant_id::text,'gameId',p_game_id::text,'generation',stamp.wire_d4)
 OR before_cp->'content'->>'executionArtifactSha256' IS DISTINCT FROM
 p->>'artifact_sha256'
 OR current_cp.content IS DISTINCT FROM before_cp OR current_cp.roster IS DISTINCT FROM
 p->'roster'
 OR current_cp.id::text IS DISTINCT FROM before_cp->'ref'->>'id'
 OR current_cp.revision::text IS DISTINCT FROM before_cp->'ref'->>'revision'
 OR current_cp.content_digest IS DISTINCT FROM before_cp->'ref'->>'digest'
 OR current_cp.confirmed_watermark IS DISTINCT FROM previous_d1
 OR current_cp.applied_watermark IS DISTINCT FROM previous_d1
 OR current_cp.recovery_generation IS DISTINCT FROM stamp.recovery_generation
 OR current_cp.history_version::text IS DISTINCT FROM
 before_cp->'content'->>'storageHistoryEpoch'
 OR before_cp->'content'->>'d3' IS DISTINCT FROM previous_d1::text
 OR after_cp->>'formatVersion' IS DISTINCT FROM 'nonplay-normal-storage-v1'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
 pg_catalog.jsonb_object_keys(after_cp) k)
 IS DISTINCT FROM ARRAY['checkpoint','formatVersion','projection_snapshot']::text[]
 OR after_cp->'checkpoint'->'content' IS DISTINCT FROM expected_cp
 OR (((after_cp->'checkpoint')-'content')-'ref') IS DISTINCT FROM
 ((before_cp-'content')-'ref')
 OR ((after_cp->'checkpoint'->'ref')-'digest') IS DISTINCT FROM
 pg_catalog.jsonb_build_object('id',current_cp.id::text,'revision',
 (current_cp.revision+1)::text)
 OR after_cp->'checkpoint'->'ref'->>'digest' !~ '^[a-f0-9]{64}$'
 OR p->'source' IS DISTINCT FROM pg_catalog.jsonb_build_object('id',source_row.id::text,
 'tenant_id',p_tenant_id::text,'game_id',p_game_id::text,'generation',
 source_row.generation::text,
 'd1',source_row.d1::text,'d2',source_row.d2::text,'d5',source_row.d5::text,
 'source_fingerprint',stamp.event_fingerprint,'event_fingerprint',
 stamp.event_fingerprint)
 OR p->'history_entry' IS DISTINCT FROM v->'newHistoryEntry'
 OR source_row.state_diff IS DISTINCT FROM v->'newHistoryEntry'->'difference'
 OR after_cp->'projection_snapshot'->'play_row' IS DISTINCT FROM p->'play_row'
 OR p->'play_row'->>'source_event_id' IS DISTINCT FROM source_row.id::text
 OR p->'play_row'->>'tenant_id' IS DISTINCT FROM p_tenant_id::text
 OR p->'play_row'->>'game_id' IS DISTINCT FROM p_game_id::text
 OR p->'play_row'->>'play_number' IS DISTINCT FROM
 before_cp->'content'->>'nextPhysicalPlayNumber'
 OR (p->'play_row'->>'play_number')::bigint IS DISTINCT FROM
 (SELECT COALESCE(pg_catalog.max(pr.play_number),0)+1 FROM public.play_rows pr
 WHERE pr.tenant_id=p_tenant_id AND pr.game_id=p_game_id)
 OR NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l WHERE l.tenant_id=p_tenant_id
 AND l.d5=stamp.d5 AND l.kind='accepted' AND
 l.source_fingerprint=stamp.event_fingerprint
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL)
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations g WHERE
 g.tenant_id=p_tenant_id
 AND g.game_id=p_game_id AND g.generation=stamp.internal_generation AND g.kind='normal'
 AND g.holder_device=stamp.device_id::text AND g.revoked_at IS NULL AND g.retired_at IS
 NULL
 AND g.recovery_generation=stamp.recovery_generation AND
 g.confirmed_watermark=source_row.d1
 AND g.applied_prefix=source_row.d1)
 OR EXISTS(SELECT 1 FROM sync_fence.first_ball_write_admissions f WHERE
 f.tenant_id=p_tenant_id
 AND f.game_id=p_game_id AND f.d5=stamp.d5 AND f.state IN ('device_verified',
 'right_verified','consumed'))
 THEN RAISE EXCEPTION 'play prefix admission rejected' USING ERRCODE='42501'; END IF;

 IF pg_catalog.jsonb_typeof(after_cp->'projection_snapshot') IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k)
 FROM pg_catalog.jsonb_object_keys(after_cp->'projection_snapshot') k)
 IS DISTINCT FROM ARRAY['play_row','play_runners']::text[]
 OR pg_catalog.jsonb_typeof(after_cp->'projection_snapshot'->'play_runners')
 IS DISTINCT FROM 'array'
 OR pg_catalog.jsonb_array_length(after_cp->'projection_snapshot'->'play_runners')
 IS DISTINCT FROM pg_catalog.jsonb_array_length(
 before_cp->'content'->'restored'->'runners')
 OR source_row.payload->'participants' IS DISTINCT FROM
 before_cp->'content'->'restored'->'participants'
 OR v->'beforeParticipants' IS DISTINCT FROM source_row.payload->'participants'
 OR v->'responsibility' IS DISTINCT FROM
 before_cp->'content'->'restored'->'responsibility'
 OR (before_cp->'content'->'restored'->'responsibility'->>'kind'
 IS DISTINCT FROM 'no-change' AND
 before_cp->'content'->'restored'->'responsibility'->>'kind'
 IS DISTINCT FROM 'changed-mid-plate-appearance')
 OR p->'play_row'->>'batter_id' IS DISTINCT FROM
 before_cp->'content'->'restored'->'participants'->>'batterId'
 OR p->'play_row'->>'pitcher_id' IS DISTINCT FROM
 before_cp->'content'->'restored'->'participants'->>'pitcherId'
 OR p->'play_row'->>'catcher_id' IS DISTINCT FROM
 before_cp->'content'->'restored'->'participants'->>'catcherId'
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
 source_row.payload->'calculation'->'request'->'source'->'checkpoint'->'content'->'restored'->'runners') m
 WHERE r->>'base'=m->>'base' AND r->>'runner_id'=m->>'runnerId'
 AND r->>'responsible_pitcher_id'=m->>'responsiblePitcherId'
 AND r->>'status'=(CASE
 WHEN source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'modality'='hold'
 THEN '継続'
 WHEN m->>'base'='1' AND source_row.payload->'calculation'->'response'
 ->'value'->'t1'->'runnerDefaultAdvance'->'first'->>'destination'='2' THEN '二進'
 WHEN m->>'base' IN ('1','2') AND source_row.payload->'calculation'
 ->'response'->'value'->'t1'->'runnerDefaultAdvance'
 ->(CASE m->>'base' WHEN '1' THEN 'first' ELSE 'second' END)
 ->>'destination'='3' THEN '三進'
 WHEN source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination'='4'
 THEN '本進' ELSE NULL END)
 AND r->>'status_source'=(CASE WHEN EXISTS(SELECT 1 FROM
 pg_catalog.jsonb_array_elements(CASE WHEN pg_catalog.jsonb_typeof(
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides')='array' THEN
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides' ELSE '[]'::jsonb END) o
 WHERE o->>'runnerBase'=m->>'base' AND o->>'destination'=
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination')
 THEN 'manual' ELSE 'auto' END)
 AND NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(CASE WHEN
 pg_catalog.jsonb_typeof(source_row.payload->'calculation'->'request'
 ->'t1'->'runnerAdvanceOverrides'->'overrides')='array' THEN
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides' ELSE '[]'::jsonb END) o
 WHERE o->>'runnerBase'=m->>'base' AND o->>'destination' IS DISTINCT FROM
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination')
 AND source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'modality'
 IN ('hold','optional','forced')))
 OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'outEffect'->'targets') target WHERE pg_catalog.jsonb_typeof(target)='object'
 AND target ? 'runner')
 THEN RAISE EXCEPTION 'play prefix admission rejected' USING ERRCODE='42501'; END IF;
 UPDATE sync_fence.ordinary_pitch_write_admissions a SET state='evaluated',
 checkpoint_id=current_cp.id,checkpoint_revision=current_cp.revision,
 checkpoint_digest=current_cp.content_digest,
 prefix_length=(before_cp->'content'->>'activeDepth')::bigint,
 frame_id=(p->>'frame_id')::uuid,frame_digest=p->>'frame_digest',
 artifact_sha256=p->>'artifact_sha256',
 source_event_id=source_row.id,source_d1=source_row.d1,source_d2=source_row.d2,
 play_row_id=(p->'play_row'->>'id')::uuid,checkpoint_content=before_cp,
 next_checkpoint_content=after_cp,
 roster_snapshot=p->'roster',history_entry=p->'history_entry',
 expected_play_row=p->'play_row'
 WHERE (a.tenant_id,a.attempt_id,a.phase_id)=(p_tenant_id,p_attempt_id,p_phase_id)
 AND a.state='right_verified' AND a.transaction_id=own_xid
 RETURNING a.xmin::text INTO row_xmin;
 IF NOT FOUND OR row_xmin::numeric IS DISTINCT FROM pg_catalog.mod(own_xid::numeric,
 4294967296::numeric)
 THEN RAISE EXCEPTION 'play prefix admission rejected' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT true;
END;

 ELSE
BEGIN
 IF p_preparation_json::jsonb->'next_checkpoint'->>'version'='3' THEN
DECLARE p jsonb; batted_obs jsonb; before_cp jsonb; after_cp jsonb; source_row record;
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
 IF source_row.payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v3'
 OR source_row.payload->'calculation'->>'formatVersion' IS DISTINCT FROM
'play-prefix-calculation-v3'
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
source_row.payload->'calculation'->'response'->'value'->'previousPrefixRef'
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

 IF before_cp->>'version' IS DISTINCT FROM '3' OR after_cp->>'version' IS DISTINCT
FROM '3'
 OR before_cp->'source_origin' IS DISTINCT FROM after_cp->'source_origin'
 OR before_cp->'source_origin' IS DISTINCT FROM before_cp->'prefix_ref'->'origin'
 OR after_cp->'source_origin' IS DISTINCT FROM after_cp->'prefix_ref'->'origin'
 OR before_cp->'lineup' IS DISTINCT FROM after_cp->'lineup'
 OR after_cp->'lineup' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'lineup'
 OR before_cp->'roster_source_digest' IS DISTINCT FROM
after_cp->'roster_source_digest'
 OR after_cp->'roster_digest' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'rosterDigest'
 OR after_cp->'participants' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'participants'
 OR before_cp->'participants' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'beforeParticipants'
 OR before_cp->'participants' IS DISTINCT FROM
source_row.payload->'calculation'->'request'->'source'->'participants'
 OR after_cp->'pa_start_source' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'nextResponsibility'->'paStartSource'
 OR after_cp->'runners' IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'runners'
 OR after_cp->'previous_prefix_ref' IS DISTINCT FROM before_cp->'prefix_ref'
 OR before_cp->'storage_anchor' IS DISTINCT FROM after_cp->'storage_anchor'
 OR after_cp->'storage_anchor'->>'id' IS DISTINCT FROM before_cp->>'id'
 OR after_cp->'storage_anchor'->>'history_epoch' IS DISTINCT FROM
before_cp->>'history_version'
 OR after_cp->'prefix_ref'->>'version' IS DISTINCT FROM '3'
 OR after_cp->'prefix_ref'->>'scope' IS DISTINCT FROM 'play-prefix-v3'
 OR after_cp->'projection_snapshot'->'play_row' IS DISTINCT FROM p->'play_row'
 OR pg_catalog.jsonb_typeof(after_cp->'projection_snapshot'->'play_runners') IS
DISTINCT FROM 'array'
 OR p->'play_row'->>'batter_id' IS DISTINCT FROM
before_cp->'participants'->>'batterId'
 OR p->'play_row'->>'pitcher_id' IS DISTINCT FROM
before_cp->'participants'->>'pitcherId'
 OR p->'play_row'->>'catcher_id' IS DISTINCT FROM
before_cp->'participants'->>'catcherId'
 OR before_cp->'source_origin'->>'eventId' IS DISTINCT FROM
 (SELECT r.record_json::jsonb->>'start_request_id' FROM
sync_right_api.read_lineup_started_origin(
p_tenant_id,p_game_id,stamp.internal_generation) r)
 OR EXISTS(SELECT 1 FROM public.operation_events e WHERE e.tenant_id=p_tenant_id AND
e.game_id=p_game_id
 AND e.generation=stamp.internal_generation AND e.d1<=previous_d1
 AND (e.ledger_kind<>'accepted' OR e.is_tombstone OR e.replaced_at IS NOT NULL OR
e.retired_at IS NOT NULL
 OR e.import_batch_id IS NOT NULL OR e.migration_unverified OR
e.legacy_row_identifier IS NOT NULL OR e.event_kind<>'play_input'))
 THEN RAISE EXCEPTION 'lineup source mismatch' USING ERRCODE='42501'; END IF;

 IF pg_catalog.jsonb_array_length(after_cp->'projection_snapshot'->'play_runners')
 IS DISTINCT FROM
pg_catalog.jsonb_array_length(source_row.payload->'calculation'->'request'->'source'->'runners')
 OR source_row.state_diff IS DISTINCT FROM
source_row.payload->'calculation'->'response'->'value'->'newHistoryEntry'->'difference'
 OR source_row.payload->'calculation'->'request'->'playIdentity' IS DISTINCT FROM
 pg_catalog.jsonb_build_object('eventId',source_row.id::text,'d5',source_row.d5::text,'playId',p->'play_row'->>'id')
 OR
source_row.payload->'calculation'->'request'->'source'->'responsibility'->>'kind' IS
DISTINCT FROM 'no-change'
 OR
source_row.payload->'calculation'->'request'->'source'->'responsibility'
->'paStartSource' IS DISTINCT FROM before_cp->'pa_start_source'
 OR (CASE WHEN source_row.payload->'calculation'->'request'->'t1' ? 'runnerObservation' THEN false ELSE (EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
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
 AND r->>'status'=(CASE
 WHEN source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'modality'='hold'
 THEN '継続'
 WHEN m->>'base'='1' AND source_row.payload->'calculation'->'response'
 ->'value'->'t1'->'runnerDefaultAdvance'->'first'->>'destination'='2' THEN '二進'
 WHEN m->>'base' IN ('1','2') AND source_row.payload->'calculation'
 ->'response'->'value'->'t1'->'runnerDefaultAdvance'
 ->(CASE m->>'base' WHEN '1' THEN 'first' ELSE 'second' END)
 ->>'destination'='3' THEN '三進'
 WHEN source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination'='4'
 THEN '本進' ELSE NULL END)
 AND r->>'status_source'=(CASE WHEN EXISTS(SELECT 1 FROM
 pg_catalog.jsonb_array_elements(CASE WHEN pg_catalog.jsonb_typeof(
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides')='array' THEN
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides' ELSE '[]'::jsonb END) o
 WHERE o->>'runnerBase'=m->>'base' AND o->>'destination'=
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination')
 THEN 'manual' ELSE 'auto' END)
 AND NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(CASE WHEN
 pg_catalog.jsonb_typeof(source_row.payload->'calculation'->'request'
 ->'t1'->'runnerAdvanceOverrides'->'overrides')='array' THEN
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides' ELSE '[]'::jsonb END) o
 WHERE o->>'runnerBase'=m->>'base' AND o->>'destination' IS DISTINCT FROM
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination')
 AND source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'modality'
 IN ('hold','optional','forced')))
 OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'outEffect'->'targets') target WHERE pg_catalog.jsonb_typeof(target)='object'
 AND target ? 'runner')) END)
 THEN RAISE EXCEPTION 'lineup physical source rejected' USING ERRCODE='42501'; END IF;
 IF source_row.payload->'calculation'->'request'->'t1' ? 'runnerObservation' THEN
  DECLARE rp_t1 jsonb; rp_per jsonb; rp_by jsonb; rp_before_set jsonb;
   rp_rows jsonb; rp_targets jsonb; rp_before jsonb; rp_observed jsonb;
   rp_record jsonb; rp_effect jsonb; rp_slot text; rp_status text;
   rp_target_count bigint; rp_out_count bigint:=0;
  BEGIN
   rp_t1:=source_row.payload->'calculation'->'request'->'t1';
   rp_per:=rp_t1->'runnerObservation'->'perPitch';
   rp_before_set:=source_row.payload->'calculation'->'request'->'source'->'runners';
   rp_rows:=after_cp->'projection_snapshot'->'play_runners';
   rp_targets:=source_row.payload->'calculation'->'response'->'value'->'t1'
    ->'outEffect'->'targets';
   IF pg_catalog.jsonb_typeof(rp_t1->'runnerObservation') IS DISTINCT FROM 'object'
    OR rp_t1->'runnerObservation' IS DISTINCT FROM
     source_row.payload->'observations'->'runnerObservation'
    OR pg_catalog.jsonb_typeof(rp_per) IS DISTINCT FROM 'object'
    OR rp_t1->>'eventKind' IS DISTINCT FROM rp_per->>'kind'
    OR rp_t1->>'resultId' IS DISTINCT FROM rp_per->>'resultId'
    OR rp_t1->>'pitchEventKind' IS DISTINCT FROM rp_per->>'pitchEventKind'
    OR pg_catalog.jsonb_typeof(rp_before_set) IS DISTINCT FROM 'array'
    OR pg_catalog.jsonb_typeof(rp_rows) IS DISTINCT FROM 'array'
    OR pg_catalog.jsonb_typeof(rp_targets) IS DISTINCT FROM 'array'
    THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
   IF pg_catalog.jsonb_array_length(rp_before_set) NOT BETWEEN 1 AND 3
    OR pg_catalog.jsonb_array_length(rp_rows)<>
     pg_catalog.jsonb_array_length(rp_before_set)
    OR (SELECT pg_catalog.count(DISTINCT m->>'base') FROM
     pg_catalog.jsonb_array_elements(rp_before_set) m)<>
     pg_catalog.jsonb_array_length(rp_before_set)
    THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
   IF rp_per->'runnerEventPayload'->>'kind'='runner-event'
    AND rp_per->'runnerAdvanceOverridesByRunner'->>'kind'='not-applied'
    AND rp_per->'runnerEventPayload'->>'event_kind' IN
     ('strategy-category.steal','pitcher-pickoff-destination.first',
      'pitcher-pickoff-destination.second','pitcher-pickoff-destination.third',
      'catcher-pickoff-destination.first','catcher-pickoff-destination.second',
      'catcher-pickoff-destination.third') THEN
    rp_by:=rp_per->'runnerEventPayload'->'by_runner';
    IF (rp_per->'runnerEventPayload'->>'event_kind'='strategy-category.steal'
      AND ((rp_per->>'kind'='runner-event' AND
       rp_per->>'resultId'='strategy-category.steal' AND
       rp_per->>'pitchEventKind'='non-pitch-event') OR
       (rp_per->>'kind'='batting-result' AND
       rp_per->>'resultId' IN ('batting-result.ball',
        'batting-result.called-pitch','batting-result.swinging-strike',
        'batting-result.walk','batting-result.hit-by-pitch',
        'batting-result.called-strikeout','batting-result.swinging-strikeout',
        'batting-result.k3','batting-result.foul') AND
       rp_per->>'resultId' IS NOT DISTINCT FROM
        rp_t1->'runnerObservation'->>'primaryResultId' AND
       rp_per->>'pitchEventKind'='pitch-event')))
     OR (rp_per->'runnerEventPayload'->>'event_kind'<>'strategy-category.steal'
      AND rp_per->>'kind'='runner-event' AND
      rp_per->>'resultId'=rp_per->'runnerEventPayload'->>'event_kind' AND
      rp_per->>'pitchEventKind'='non-pitch-event') THEN
     NULL;
    ELSE RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
   ELSIF rp_per->'runnerEventPayload'->>'kind'='not-applicable'
    AND rp_per->'runnerAdvanceOverridesByRunner'->>'kind'='overridden'
    AND ((rp_per->>'kind'='batting-result' AND
     rp_per->>'resultId'='batting-result.strikeout-double-play' AND
     rp_per->>'pitchEventKind'='pitch-event') OR
     (rp_per->>'kind'='secondary-result' AND
      ((rp_per->>'resultId' IN
       ('secondary-result.wild-pitch','secondary-result.passed-ball')
       AND rp_per->>'pitchEventKind'='pitch-event') OR
       (rp_per->>'resultId'='secondary-result.balk' AND
        rp_per->>'pitchEventKind'='non-pitch-event')))) THEN
    rp_by:=rp_per->'runnerAdvanceOverridesByRunner'->'by_runner';
   ELSE RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
   IF pg_catalog.jsonb_typeof(rp_by) IS DISTINCT FROM 'object'
    OR (SELECT pg_catalog.count(*) FROM pg_catalog.jsonb_object_keys(rp_by))<>
     pg_catalog.jsonb_array_length(rp_before_set)
    THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
   FOR rp_before IN SELECT value FROM pg_catalog.jsonb_array_elements(rp_before_set)
   LOOP
    rp_slot:=CASE rp_before->>'base' WHEN '1' THEN 'first'
     WHEN '2' THEN 'second' WHEN '3' THEN 'third' ELSE NULL END;
    IF rp_slot IS NULL OR pg_catalog.jsonb_typeof(rp_before) IS DISTINCT FROM 'object'
     THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
    rp_observed:=rp_by->rp_slot;
    rp_effect:=source_row.payload->'calculation'->'response'->'value'->'t1'
     ->'runnerDefaultAdvance'->rp_slot;
    SELECT pg_catalog.count(*),(pg_catalog.jsonb_agg(value))->0
    INTO rp_target_count,rp_record
    FROM pg_catalog.jsonb_array_elements(rp_rows) value
    WHERE value->>'base'=rp_before->>'base';
    IF rp_target_count<>1 OR pg_catalog.jsonb_typeof(rp_observed) IS DISTINCT FROM
     'object' OR pg_catalog.jsonb_typeof(rp_effect) IS DISTINCT FROM 'object'
     OR rp_observed->'runner' IS DISTINCT FROM pg_catalog.jsonb_build_object(
      'kind','official','player_id',rp_before->>'runnerId')
     OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
      pg_catalog.jsonb_object_keys(rp_record) k) IS DISTINCT FROM
      ARRAY['base','id','import_batch_id','play_id','responsible_pitcher_id',
       'retired_at','runner_id','status','status_source','tenant_id']::text[]
     OR rp_record->>'tenant_id' IS DISTINCT FROM p_tenant_id::text
     OR rp_record->>'play_id' IS DISTINCT FROM p->'play_row'->>'id'
     OR rp_record->>'runner_id' IS DISTINCT FROM rp_before->>'runnerId'
     OR rp_record->>'responsible_pitcher_id' IS DISTINCT FROM
      rp_before->>'responsiblePitcherId'
     OR rp_record->'retired_at' IS DISTINCT FROM 'null'::jsonb
     OR rp_record->'import_batch_id' IS DISTINCT FROM 'null'::jsonb
     OR rp_record->>'id' IS NULL
     THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
    SELECT pg_catalog.count(*) INTO rp_target_count FROM
     pg_catalog.jsonb_array_elements(rp_targets) target
     WHERE target=pg_catalog.jsonb_build_object('runner',rp_before->>'base');
    IF rp_observed->>'kind'='hold' THEN
     IF rp_target_count<>0 OR rp_effect->>'modality' IS DISTINCT FROM 'hold'
      OR rp_effect->'destination' IS DISTINCT FROM 'null'::jsonb
      OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
       pg_catalog.jsonb_object_keys(rp_observed) k) IS DISTINCT FROM
       ARRAY['kind','runner']::text[]
      THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
     rp_status:='継続';
     IF rp_record->>'status_source' IS DISTINCT FROM 'auto'
      THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
    ELSIF rp_observed->>'kind'='safe-advance' THEN
     IF rp_target_count<>0 OR (rp_effect->>'modality' IS DISTINCT FROM 'optional'
      AND rp_effect->>'modality' IS DISTINCT FROM 'forced')
      OR rp_effect->>'destination' IS DISTINCT FROM
       CASE rp_observed->>'destination' WHEN 'second' THEN '2'
        WHEN 'third' THEN '3' WHEN 'home' THEN '4' ELSE NULL END
      OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
       pg_catalog.jsonb_object_keys(rp_observed) k) IS DISTINCT FROM
       ARRAY['destination','kind','runner']::text[]
      THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
     rp_status:=CASE rp_before->>'base' WHEN '1' THEN (CASE rp_effect->>'destination' WHEN '2' THEN '二進' WHEN '3' THEN '三進' WHEN '4' THEN '本進' ELSE NULL END) WHEN '2' THEN (CASE rp_effect->>'destination' WHEN '3' THEN '三進' WHEN '4' THEN '本進' ELSE NULL END) WHEN '3' THEN (CASE rp_effect->>'destination' WHEN '4' THEN '本進' ELSE NULL END) ELSE NULL END;
     IF rp_record->>'status_source' IS DISTINCT FROM 'manual'
      THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
    ELSIF rp_observed->>'kind'='out' THEN
     IF rp_target_count<>1 OR rp_observed->>'attempted_base' IS NULL
      OR rp_observed->>'attempted_base' NOT IN
      ('first','second','third','home')
      OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
       pg_catalog.jsonb_object_keys(rp_observed) k) IS DISTINCT FROM
       ARRAY['attempted_base','kind','out_kind','runner']::text[]
      THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
     rp_status:=CASE rp_observed->>'out_kind' WHEN 'force-out' THEN '封殺' WHEN 'pitcher-pickoff-out' THEN '投手牽制死' WHEN 'catcher-pickoff-out' THEN '捕手牽制死' WHEN 'caught-stealing' THEN '盗塁死' WHEN 'running-out' THEN '走塁死' ELSE NULL END;
     rp_out_count:=rp_out_count+1;
     IF rp_record->>'status_source' IS DISTINCT FROM 'manual'
      THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
    ELSE RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
    IF rp_status IS NULL OR rp_record->>'status' IS DISTINCT FROM rp_status
     THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
   END LOOP;
   IF rp_out_count IS DISTINCT FROM (SELECT pg_catalog.count(*) FROM
    pg_catalog.jsonb_array_elements(rp_targets) target
    WHERE pg_catalog.jsonb_typeof(target)='object')
    OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(rp_targets) target
     WHERE pg_catalog.jsonb_typeof(target)='object' AND
     (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
      pg_catalog.jsonb_object_keys(target) k) IS DISTINCT FROM ARRAY['runner']::text[])
    THEN RAISE EXCEPTION 'runner physical evidence rejected' USING ERRCODE='42501'; END IF;
  END;
 END IF;


 -- 新安打だけの閉分岐。旧writer/原本/nonce検査は変更しない。
 batted_obs:=source_row.payload->'observations';
 IF source_row.payload->'calculation'->'request'->'t1'->>'resultId'
 IN ('batting-result.single','batting-result.double',
 'batting-result.triple','batting-result.home-run')
 OR batted_obs ? 'battedBall' THEN
  IF pg_catalog.jsonb_typeof(batted_obs) IS DISTINCT FROM 'object'
  OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
  pg_catalog.jsonb_object_keys(batted_obs) k)
  IS DISTINCT FROM ARRAY['battedBall','battingSide','course','interferenceRuling',
  'officialScoringPayload','pitchSpeed','pitchTypeKey','resultId',
  'runnerAdvanceOverridesByRunner','stance','thirdOutObservation','thirdOutTimingByRunner']::text[]
  OR pg_catalog.jsonb_typeof(batted_obs->'resultId') IS DISTINCT FROM 'string'
  OR batted_obs->>'resultId' NOT IN ('batting-result.single','batting-result.double',
  'batting-result.triple','batting-result.home-run')
  OR batted_obs->>'resultId' IS DISTINCT FROM
  source_row.payload->'calculation'->'request'->'t1'->>'resultId'
  OR batted_obs->'officialScoringPayload' IS DISTINCT FROM
  '{"kind":"no-error","errorCount":"0","fielders":[]}'::jsonb
  OR batted_obs->'interferenceRuling' IS DISTINCT FROM '{"kind":"not-required"}'::jsonb
  OR (
   batted_obs->'runnerAdvanceOverridesByRunner' IS DISTINCT FROM
   '{"kind":"not-applied","overrides":[]}'::jsonb
   AND batted_obs->'runnerAdvanceOverridesByRunner' IS DISTINCT FROM
   source_row.payload->'calculation'->'request'->'t1'->'runnerAdvanceOverrides')
  OR (
   batted_obs->'runnerAdvanceOverridesByRunner' =
   '{"kind":"not-applied","overrides":[]}'::jsonb
   AND source_row.payload->'calculation'->'request'->'t1'
   ->>'runnerAdvanceOverrides' IS DISTINCT FROM 'not-applied')
  OR batted_obs->'thirdOutObservation' IS DISTINCT FROM '{"kind":"none"}'::jsonb
  OR batted_obs->'thirdOutTimingByRunner' IS DISTINCT FROM '{}'::jsonb
  OR source_row.payload->'calculation'->'request'->'t1'->>'officialScoringPayload'
  IS DISTINCT FROM 'no-error'
  OR source_row.payload->'calculation'->'request'->'t1'->>'interferenceRuling'
  IS DISTINCT FROM 'not-required'
  OR source_row.payload->'calculation'->'request'->'t1'->>'thirdOutObservation'
  IS DISTINCT FROM 'none'
  OR pg_catalog.jsonb_typeof(batted_obs->'battedBall') IS DISTINCT FROM 'object'
  OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM
  pg_catalog.jsonb_object_keys(batted_obs->'battedBall') k)
  IS DISTINCT FROM ARRAY['hitX','hitY','rawFielderPosition','resolvedFielderId',
  'strengthKey','typeKey']::text[]
  OR p->'play_row'->>'event_kind' IS DISTINCT FROM 'pitch'
  OR p->'play_row'->>'batting_result_key' IS DISTINCT FROM batted_obs->>'resultId'
  OR p->'play_row'->>'pitch_type_key' IS DISTINCT FROM batted_obs->>'pitchTypeKey'
  OR p->'play_row'->'raw_fielder_position' IS DISTINCT FROM
  batted_obs->'battedBall'->'rawFielderPosition'
  OR p->'play_row'->'resolved_fielder_id' IS DISTINCT FROM
  batted_obs->'battedBall'->'resolvedFielderId'
  OR p->'play_row'->'batted_ball_type' IS DISTINCT FROM
  batted_obs->'battedBall'->'typeKey'
  OR p->'play_row'->'batted_ball_strength' IS DISTINCT FROM
  batted_obs->'battedBall'->'strengthKey'
  OR (batted_obs->'battedBall'->'hitX'='null'::jsonb AND
  p->'play_row'->'hit_x' IS DISTINCT FROM 'null'::jsonb)
  OR (batted_obs->'battedBall'->'hitY'='null'::jsonb AND
  p->'play_row'->'hit_y' IS DISTINCT FROM 'null'::jsonb)
  OR (batted_obs->'battedBall'->'hitX'<>'null'::jsonb AND
  (pg_catalog.jsonb_typeof(batted_obs->'battedBall'->'hitX') IS DISTINCT FROM 'string'
  OR NOT ((batted_obs->'battedBall'->>'hitX')::numeric BETWEEN 0 AND 1)
  OR (p->'play_row'->>'hit_x')::double precision IS DISTINCT FROM
  (batted_obs->'battedBall'->>'hitX')::double precision))
  OR (batted_obs->'battedBall'->'hitY'<>'null'::jsonb AND
  (pg_catalog.jsonb_typeof(batted_obs->'battedBall'->'hitY') IS DISTINCT FROM 'string'
  OR NOT ((batted_obs->'battedBall'->>'hitY')::numeric BETWEEN 0 AND 1)
  OR (p->'play_row'->>'hit_y')::double precision IS DISTINCT FROM
  (batted_obs->'battedBall'->>'hitY')::double precision))
  OR NOT EXISTS(SELECT 1 FROM public.tenant_vocabularies v
  WHERE v.tenant_id=p_tenant_id AND v.key=batted_obs->>'pitchTypeKey'
  AND v.category='pitch_type' AND NOT v.disabled)
  OR NOT EXISTS(SELECT 1 FROM public.admin_vocabularies v
  WHERE v.key=batted_obs->>'resultId' AND v.category='batting_result'
  AND NOT v.disabled)
  OR (batted_obs->'battedBall'->'typeKey'<>'null'::jsonb AND NOT EXISTS(
  SELECT 1 FROM public.admin_vocabularies v
  WHERE v.key=batted_obs->'battedBall'->>'typeKey' AND v.category='batted_ball'
  AND NOT v.disabled))
  OR (batted_obs->'battedBall'->'strengthKey'<>'null'::jsonb AND NOT EXISTS(
  SELECT 1 FROM public.admin_vocabularies v
  WHERE v.key=batted_obs->'battedBall'->>'strengthKey' AND v.category='batted_ball'
  AND NOT v.disabled))
  OR (batted_obs->'battedBall'->'resolvedFielderId'<>'null'::jsonb AND NOT EXISTS(
   SELECT 1 FROM pg_catalog.jsonb_array_elements(p->'roster'->'teams') team,
   LATERAL pg_catalog.jsonb_array_elements(team->'participants') player
   WHERE team->>'side'=(CASE before_cp->'after'->'stateFields'->>'state.half'
   WHEN 'top' THEN 'home' WHEN 'bottom' THEN 'away' ELSE '' END)
   AND player->'player'->>'player_id'=batted_obs->'battedBall'->>'resolvedFielderId'
   AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(player->'roles') role
   WHERE role->>'kind'='fielding')))
  THEN RAISE EXCEPTION 'batted hit physical source rejected'
  USING ERRCODE='42501'; END IF;
 END IF;
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

 ELSE
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
 AND r->>'status'=(CASE
 WHEN source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'modality'='hold'
 THEN '継続'
 WHEN m->>'base'='1' AND source_row.payload->'calculation'->'response'
 ->'value'->'t1'->'runnerDefaultAdvance'->'first'->>'destination'='2' THEN '二進'
 WHEN m->>'base' IN ('1','2') AND source_row.payload->'calculation'
 ->'response'->'value'->'t1'->'runnerDefaultAdvance'
 ->(CASE m->>'base' WHEN '1' THEN 'first' ELSE 'second' END)
 ->>'destination'='3' THEN '三進'
 WHEN source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination'='4'
 THEN '本進' ELSE NULL END)
 AND r->>'status_source'=(CASE WHEN EXISTS(SELECT 1 FROM
 pg_catalog.jsonb_array_elements(CASE WHEN pg_catalog.jsonb_typeof(
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides')='array' THEN
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides' ELSE '[]'::jsonb END) o
 WHERE o->>'runnerBase'=m->>'base' AND o->>'destination'=
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination')
 THEN 'manual' ELSE 'auto' END)
 AND NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(CASE WHEN
 pg_catalog.jsonb_typeof(source_row.payload->'calculation'->'request'
 ->'t1'->'runnerAdvanceOverrides'->'overrides')='array' THEN
 source_row.payload->'calculation'->'request'->'t1'
 ->'runnerAdvanceOverrides'->'overrides' ELSE '[]'::jsonb END) o
 WHERE o->>'runnerBase'=m->>'base' AND o->>'destination' IS DISTINCT FROM
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'destination')
 AND source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'runnerDefaultAdvance'->(CASE m->>'base' WHEN '1' THEN 'first'
 WHEN '2' THEN 'second' WHEN '3' THEN 'third' END)->>'modality'
 IN ('hold','optional','forced')))
 OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(
 source_row.payload->'calculation'->'response'->'value'->'t1'
 ->'outEffect'->'targets') target WHERE pg_catalog.jsonb_typeof(target)='object'
 AND target ? 'runner')
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

 END IF;
END;

 END IF;
END;
$dispatch$;

ALTER FUNCTION sync_right_api.prepare_play_prefix_projection(uuid, uuid, uuid, bytea, uuid, uuid, text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.prepare_play_prefix_projection(uuid, uuid, uuid, bytea, uuid, uuid, text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.prepare_play_prefix_projection(uuid, uuid, uuid, bytea, uuid, uuid, text) TO pitchlog_app;
