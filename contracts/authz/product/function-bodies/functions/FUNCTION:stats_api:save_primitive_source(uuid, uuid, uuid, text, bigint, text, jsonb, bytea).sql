-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:save_primitive_source(uuid, uuid, uuid, text, bigint, text, jsonb, bytea)

CREATE FUNCTION stats_api.save_primitive_source(p_attempt_id uuid,p_phase_id uuid,p_source_event_id uuid,p_model_sha256 text,p_expected_revision bigint,p_expected_source_set_sha256 text,p_evaluation_json jsonb,p_binding_nonce bytea)
RETURNS TABLE(fact_version_id uuid,source_event_id uuid,model_sha256 text,source_set_sha256 text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $stats$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; p_game_id uuid; p_player_id uuid; p_fact_version_id uuid; p_revision bigint; p_source_set_sha256 text;
 binding sync_fence.writer_bindings%ROWTYPE; event_row public.operation_events%ROWTYPE;
 saved_play public.play_rows%ROWTYPE; checkpoint sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 series sync_fence.stats_fact_versions%ROWTYPE; prior_source sync_fence.stats_primitive_sources%ROWTYPE;
 stamp jsonb; pa_value jsonb; variant text; provider text; checkpoint_id uuid; checkpoint_revision bigint; checkpoint_digest text; frame_digest text;
 current_source record; health record; previous_health record; audit record;
 rule_hash text; eval_hash text; metric record; credit jsonb; amount_sum numeric; credit_ordinal bigint; new_keys text[]; had_series boolean;
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR tenant IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_source_event_id IS NULL
 OR p_binding_nonce IS NULL OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 OR p_model_sha256 IS DISTINCT FROM 'sha256:f358df32f54bedfecb2866436e718c7bd6ece514798fe4de2325022d38a09422'
 OR p_expected_revision IS NULL OR p_expected_revision<0
 OR ((p_expected_revision=0) IS DISTINCT FROM (p_expected_source_set_sha256 IS NULL))
 OR (p_expected_source_set_sha256 IS NOT NULL AND p_expected_source_set_sha256 !~ '^[a-f0-9]{64}$')
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 SELECT b.* INTO STRICT binding FROM sync_fence.writer_bindings b
 WHERE b.tenant_id=tenant AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id
 AND b.state='open' AND b.transaction_id=own_xid AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,p_binding_nonce,binding.device_id,binding.game_id);
 p_game_id:=binding.game_id;
 IF NOT EXISTS(SELECT 1 FROM public.games g WHERE g.tenant_id=tenant AND g.id=p_game_id
 AND g.status='in_progress' AND g.hidden_at IS NULL AND g.trashed_at IS NULL) THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 SELECT e.* INTO STRICT event_row FROM public.operation_events e
 WHERE e.tenant_id=tenant AND e.game_id=p_game_id AND e.id=p_source_event_id
 AND e.generation=binding.internal_generation AND e.d5=binding.d5
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified
 AND e.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 variant:=event_row.payload->>'formatVersion';
 IF event_row.payload#>'{calculation,response,ok}' IS DISTINCT FROM 'true'::jsonb
 OR event_row.payload#>>'{calculation,formatVersion}' IS DISTINCT FROM (CASE variant
 WHEN 'first-ball-play-v1' THEN 'first-ball-calculation-v1'
 WHEN 'ordinary-pitch-play-v1' THEN 'ordinary-pitch-calculation-v1'
 WHEN 'play-prefix-play-v2' THEN 'play-prefix-calculation-v2'
 WHEN 'play-prefix-play-v3' THEN 'play-prefix-calculation-v3' END)
 OR variant NOT IN ('first-ball-play-v1','ordinary-pitch-play-v1','play-prefix-play-v2','play-prefix-play-v3')
 OR variant IS NULL THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 IF variant='first-ball-play-v1' THEN
  SELECT pg_catalog.to_jsonb(s) INTO STRICT stamp FROM sync_fence.first_ball_write_admissions s
  JOIN sync_fence.writer_bindings b USING(tenant_id,attempt_id,phase_id)
  JOIN sync_fence.writer_admissions wa USING(tenant_id,attempt_id,phase_id)
  WHERE s.tenant_id=tenant AND s.attempt_id=p_attempt_id AND s.phase_id=p_phase_id
  AND s.state='consumed' AND s.consumed_at IS NOT NULL AND s.source_event_id=p_source_event_id
  AND s.transaction_id=own_xid AND s.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
  AND wa.transaction_id=own_xid AND wa.lease_id=b.lease_id
  AND wa.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
  AND s.tenant_id IS NOT DISTINCT FROM b.tenant_id AND s.attempt_id IS NOT DISTINCT FROM b.attempt_id AND s.phase_id IS NOT DISTINCT FROM b.phase_id AND s.authority_id IS NOT DISTINCT FROM b.authority_id AND s.control_instance IS NOT DISTINCT FROM b.control_instance AND s.business_instance IS NOT DISTINCT FROM b.business_instance AND s.restore_epoch IS NOT DISTINCT FROM b.restore_epoch AND s.control_version IS NOT DISTINCT FROM b.control_version AND s.issuer IS NOT DISTINCT FROM b.issuer AND s.lease_id IS NOT DISTINCT FROM b.lease_id AND s.device_id IS NOT DISTINCT FROM b.device_id AND s.game_id IS NOT DISTINCT FROM b.game_id AND s.wire_d4 IS NOT DISTINCT FROM b.wire_d4 AND s.internal_generation IS NOT DISTINCT FROM b.internal_generation AND s.recovery_generation IS NOT DISTINCT FROM b.recovery_generation AND s.codec_version IS NOT DISTINCT FROM b.codec_version AND s.request_fingerprint IS NOT DISTINCT FROM b.request_fingerprint AND s.d5 IS NOT DISTINCT FROM b.d5 AND s.event_fingerprint IS NOT DISTINCT FROM b.event_fingerprint AND s.system_identifier IS NOT DISTINCT FROM b.system_identifier AND s.database_oid IS NOT DISTINCT FROM b.database_oid AND s.postmaster_started_at IS NOT DISTINCT FROM b.postmaster_started_at AND s.backend_pid IS NOT DISTINCT FROM b.backend_pid AND s.backend_start IS NOT DISTINCT FROM b.backend_start AND s.transaction_id IS NOT DISTINCT FROM b.transaction_id AND s.nonce_digest IS NOT DISTINCT FROM b.nonce_digest AND s.expires_at IS NOT DISTINCT FROM b.expires_at;
  IF EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_write_admissions o
   WHERE o.tenant_id=tenant AND o.attempt_id=p_attempt_id AND o.phase_id=p_phase_id
   AND o.state IN ('device_verified','right_verified','evaluated','consumed')) THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  checkpoint_id:=NULL; checkpoint_revision:=NULL; checkpoint_digest:=NULL; frame_digest:=NULL;
  provider:='first_ball';
 ELSE
  SELECT pg_catalog.to_jsonb(s) INTO STRICT stamp FROM sync_fence.ordinary_pitch_write_admissions s
  JOIN sync_fence.writer_bindings b USING(tenant_id,attempt_id,phase_id)
  JOIN sync_fence.writer_admissions wa USING(tenant_id,attempt_id,phase_id)
  WHERE s.tenant_id=tenant AND s.attempt_id=p_attempt_id AND s.phase_id=p_phase_id
  AND s.state='consumed' AND s.consumed_at IS NOT NULL AND s.source_event_id=p_source_event_id
  AND s.transaction_id=own_xid AND s.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
  AND wa.transaction_id=own_xid AND wa.lease_id=b.lease_id
  AND wa.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
  AND s.tenant_id IS NOT DISTINCT FROM b.tenant_id AND s.attempt_id IS NOT DISTINCT FROM b.attempt_id AND s.phase_id IS NOT DISTINCT FROM b.phase_id AND s.authority_id IS NOT DISTINCT FROM b.authority_id AND s.control_instance IS NOT DISTINCT FROM b.control_instance AND s.business_instance IS NOT DISTINCT FROM b.business_instance AND s.restore_epoch IS NOT DISTINCT FROM b.restore_epoch AND s.control_version IS NOT DISTINCT FROM b.control_version AND s.issuer IS NOT DISTINCT FROM b.issuer AND s.lease_id IS NOT DISTINCT FROM b.lease_id AND s.device_id IS NOT DISTINCT FROM b.device_id AND s.game_id IS NOT DISTINCT FROM b.game_id AND s.wire_d4 IS NOT DISTINCT FROM b.wire_d4 AND s.internal_generation IS NOT DISTINCT FROM b.internal_generation AND s.recovery_generation IS NOT DISTINCT FROM b.recovery_generation AND s.codec_version IS NOT DISTINCT FROM b.codec_version AND s.request_fingerprint IS NOT DISTINCT FROM b.request_fingerprint AND s.d5 IS NOT DISTINCT FROM b.d5 AND s.event_fingerprint IS NOT DISTINCT FROM b.event_fingerprint AND s.system_identifier IS NOT DISTINCT FROM b.system_identifier AND s.database_oid IS NOT DISTINCT FROM b.database_oid AND s.postmaster_started_at IS NOT DISTINCT FROM b.postmaster_started_at AND s.backend_pid IS NOT DISTINCT FROM b.backend_pid AND s.backend_start IS NOT DISTINCT FROM b.backend_start AND s.transaction_id IS NOT DISTINCT FROM b.transaction_id AND s.nonce_digest IS NOT DISTINCT FROM b.nonce_digest AND s.expires_at IS NOT DISTINCT FROM b.expires_at;
  IF EXISTS(SELECT 1 FROM sync_fence.first_ball_write_admissions f
   WHERE f.tenant_id=tenant AND f.attempt_id=p_attempt_id AND f.phase_id=p_phase_id
   AND f.state IN ('device_verified','right_verified','consumed')) THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  SELECT c.* INTO STRICT checkpoint FROM sync_fence.ordinary_pitch_checkpoints c
  WHERE c.tenant_id=tenant AND c.game_id=p_game_id AND c.internal_generation=binding.internal_generation
  AND c.id=(stamp->>'checkpoint_id')::uuid AND c.state='current'
  AND c.content=stamp->'next_checkpoint_content' AND c.content_digest=stamp->'next_checkpoint_content'->>'content_digest'
  AND c.revision=(stamp->'next_checkpoint_content'->>'revision')::bigint
  AND c.history_version=(stamp->'next_checkpoint_content'->>'history_version')::bigint
  AND c.confirmed_watermark=event_row.d1 AND c.applied_watermark=event_row.d1
  AND c.saved_at=(stamp->>'consumed_at')::timestamptz
  AND c.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
  IF stamp->>'artifact_sha256' IS DISTINCT FROM event_row.payload#>>'{calculation,artifactSha256}'
  OR stamp->>'frame_digest' IS NULL OR stamp->>'frame_digest' !~ '^[a-f0-9]{64}$'
  OR stamp->>'source_d1' IS DISTINCT FROM event_row.d1::text
  OR stamp->>'source_d2' IS DISTINCT FROM event_row.d2::text
  THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  checkpoint_id:=checkpoint.id; checkpoint_revision:=checkpoint.revision;
  checkpoint_digest:=checkpoint.content_digest; frame_digest:=stamp->>'frame_digest'; provider:='ordinary';
 END IF;
 SELECT p.* INTO STRICT saved_play FROM public.play_rows p
 WHERE p.tenant_id=tenant AND p.game_id=p_game_id AND p.source_event_id=p_source_event_id
 AND p.id=(stamp->>'play_row_id')::uuid AND p.hidden_at IS NULL
 AND p.import_batch_id IS NULL AND p.legacy_row_identifier IS NULL AND NOT p.migration_unverified
 AND p.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 IF provider='ordinary' AND pg_catalog.to_jsonb(saved_play) IS DISTINCT FROM stamp->'expected_play_row'
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l WHERE l.tenant_id=tenant
 AND l.d5=binding.d5 AND l.kind='accepted' AND l.source_fingerprint=binding.event_fingerprint
 AND l.retired_at IS NULL AND l.import_batch_id IS NULL
 AND l.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric))
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations r WHERE r.tenant_id=tenant AND r.game_id=p_game_id
 AND r.generation=binding.internal_generation AND r.kind='normal' AND r.holder_device=binding.device_id::text
 AND r.revoked_at IS NULL AND r.retired_at IS NULL AND r.recovery_generation=binding.recovery_generation
 AND r.confirmed_watermark=event_row.d1 AND r.applied_prefix=event_row.d1)
 OR NOT EXISTS(SELECT 1 FROM public.rg1_restore_gate g WHERE g.singleton_id=1 AND g.state='open'
 AND g.recovery_generation=binding.recovery_generation)
 OR NOT EXISTS(SELECT 1 FROM public.trusted_devices d WHERE d.tenant_id=tenant AND d.device_id=binding.device_id AND d.revoked_at IS NULL)
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 SELECT * INTO STRICT current_source FROM (WITH canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=tenant AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=p_game_id
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
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR p.hidden_at IS NOT NULL THEN 'source_unavailable'
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
SELECT c.* FROM canonical_s c WHERE c.source_event_id=p_source_event_id AND c.source_state='included') canonical_current;
 IF current_source.recording_generation IS DISTINCT FROM event_row.generation
 OR current_source.d1 IS DISTINCT FROM event_row.d1 OR current_source.d2 IS DISTINCT FROM event_row.d2
 OR current_source.slot_version IS DISTINCT FROM 1::bigint
 OR current_source.play_row_id IS DISTINCT FROM saved_play.id OR current_source.play_row_version IS DISTINCT FROM saved_play.version
 OR current_source.source_fingerprint IS DISTINCT FROM binding.event_fingerprint
 OR current_source.artifact_sha256 IS DISTINCT FROM event_row.payload#>>'{calculation,artifactSha256}'
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 SELECT * INTO STRICT health FROM (WITH canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=tenant AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=p_game_id
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
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR p.hidden_at IS NOT NULL THEN 'source_unavailable'
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
SELECT COALESCE(ch.game_count,0) AS game_count,COALESCE(ch.canonical_source_count,0) AS canonical_source_count,COALESCE(ch.unavailable_count,0) AS unavailable_count,COALESCE(ch.canonical_source_set_sha256,encode(sha256(convert_to('accepted-play-slot-v1:empty','UTF8')),'hex')) AS canonical_source_set_sha256 FROM (VALUES(1)) singleton(n) LEFT JOIN canonical_health ch ON true) canonical_current_health;
 IF health.game_count IS DISTINCT FROM 1::bigint OR health.unavailable_count IS DISTINCT FROM 0::bigint
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;

 -- rootはこのenvelopeを実frameの唯一T5生成値/token identityへ同scope束縛する。
 IF p_evaluation_json IS NULL OR pg_catalog.jsonb_typeof(p_evaluation_json) IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k COLLATE "C") FROM pg_catalog.jsonb_object_keys(p_evaluation_json) k)
 IS DISTINCT FROM ARRAY['metrics','native_rule_sha256','pa_row','pending','selected','source_event_id']::text[]
 OR p_evaluation_json->'selected' IS DISTINCT FROM 'true'::jsonb
 OR p_evaluation_json->>'source_event_id' IS DISTINCT FROM p_source_event_id::text
 OR pg_catalog.jsonb_typeof(p_evaluation_json->'native_rule_sha256') IS DISTINCT FROM 'string'
 OR p_evaluation_json->>'native_rule_sha256' !~ '^[a-f0-9]{64}$'
 OR p_evaluation_json->'pending' IS DISTINCT FROM
 '{"named_category":{"state":"decision_pending","decision_id":"D02","value":null},"appearances":{"state":"decision_pending","decision_id":"D03","value":null},"batters_faced":{"state":"decision_pending","decision_id":"D04","value":null},"ops":{"state":"decision_pending","decision_id":"D05","value":null}}'::jsonb
 OR pg_catalog.jsonb_typeof(p_evaluation_json->'metrics') IS DISTINCT FROM 'object'
 OR (SELECT pg_catalog.array_agg(k ORDER BY k COLLATE "C") FROM pg_catalog.jsonb_object_keys(p_evaluation_json->'metrics') k)
 IS DISTINCT FROM ARRAY['ab','bb','catcher_interference_reached','doubles','fielding_errors','h','hbp','hits_allowed','home_runs_allowed','hr','k','pa','pitch_count','pitcher_bb','pitcher_hbp','pitcher_k','pitching_outs','rbi','runner_interference_reached','runs','runs_allowed','sf','sh','stolen_bases','total_bases','triples']::text[]
 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 pa_value:=p_evaluation_json->'pa_row';
 IF pa_value IS DISTINCT FROM 'null'::jsonb THEN
  IF pg_catalog.jsonb_typeof(pa_value) IS DISTINCT FROM 'object'
  OR (SELECT pg_catalog.array_agg(k ORDER BY k COLLATE "C") FROM pg_catalog.jsonb_object_keys(pa_value) k)
   IS DISTINCT FROM ARRAY['batter_id','counts_as_ab','half','hit_kind','inning','ordinal_for_batter','pa_id','rbi','rbi_state','reached_by','result_display']::text[]
  OR event_row.payload#>'{calculation,response,value,t1,plateAppearanceEnded}' IS DISTINCT FROM 'true'::jsonb
  OR pg_catalog.jsonb_typeof(pa_value->'pa_id') IS DISTINCT FROM 'string'
  OR pa_value->>'pa_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  OR pg_catalog.jsonb_typeof(pa_value->'batter_id') IS DISTINCT FROM 'string'
  OR pa_value->>'batter_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  OR pg_catalog.jsonb_typeof(pa_value->'ordinal_for_batter') IS DISTINCT FROM 'string'
  OR pa_value->>'ordinal_for_batter' !~ '^[1-9][0-9]*$' OR pg_catalog.length(pa_value->>'ordinal_for_batter')>20
  OR pg_catalog.jsonb_typeof(pa_value->'inning') IS DISTINCT FROM 'string'
  OR pa_value->>'inning' !~ '^[1-9][0-9]*$' OR pg_catalog.length(pa_value->>'inning')>20
  OR pg_catalog.jsonb_typeof(pa_value->'half') IS DISTINCT FROM 'string'
  OR pa_value->>'half' NOT IN ('top','bottom')
  OR pg_catalog.jsonb_typeof(pa_value->'result_display') IS DISTINCT FROM 'string'
  OR pg_catalog.jsonb_typeof(pa_value->'counts_as_ab') IS DISTINCT FROM 'boolean'
  OR pg_catalog.jsonb_typeof(pa_value->'hit_kind') IS DISTINCT FROM 'string'
  OR pa_value->>'hit_kind' NOT IN ('none','single','double','triple','home_run')
  OR pg_catalog.jsonb_typeof(pa_value->'reached_by') IS DISTINCT FROM 'string'
  OR pa_value->'rbi_state' IS DISTINCT FROM p_evaluation_json#>'{metrics,rbi,state}'
  OR pa_value->'rbi' IS DISTINCT FROM p_evaluation_json#>'{metrics,rbi,value}'
  OR pg_catalog.length(pa_value->>'rbi')>128
  THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 END IF;
 rule_hash:=p_evaluation_json->>'native_rule_sha256';
 IF variant IN ('play-prefix-play-v2','play-prefix-play-v3') AND rule_hash IS DISTINCT FROM
 event_row.payload#>>'{calculation,request,source,rulesDigest}' THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 FOR metric IN SELECT key,value FROM pg_catalog.jsonb_each(p_evaluation_json->'metrics') LOOP
  IF pg_catalog.jsonb_typeof(metric.value) IS DISTINCT FROM 'object'
  OR (SELECT pg_catalog.array_agg(k ORDER BY k COLLATE "C") FROM pg_catalog.jsonb_object_keys(metric.value) k)
   IS DISTINCT FROM ARRAY['credits','display','reason','state','value']::text[]
  OR pg_catalog.jsonb_typeof(metric.value->'credits') IS DISTINCT FROM 'array'
  OR pg_catalog.jsonb_array_length(metric.value->'credits')>4
  THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  IF metric.value->>'state'='available' THEN
   IF pg_catalog.jsonb_typeof(metric.value->'value') IS DISTINCT FROM 'string'
   OR metric.value->>'value' !~ '^(0|[1-9][0-9]*)$'
   OR metric.value->'display' IS DISTINCT FROM metric.value->'value'
   OR metric.value->'reason' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
   amount_sum:=0;
   FOR credit IN SELECT value FROM pg_catalog.jsonb_array_elements(metric.value->'credits') LOOP
    IF pg_catalog.jsonb_typeof(credit) IS DISTINCT FROM 'object'
    OR (SELECT pg_catalog.array_agg(k ORDER BY k COLLATE "C") FROM pg_catalog.jsonb_object_keys(credit) k)
     IS DISTINCT FROM ARRAY['player_id','quantity']::text[]
    OR pg_catalog.jsonb_typeof(credit->'player_id') IS DISTINCT FROM 'string'
    OR credit->>'player_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    OR pg_catalog.jsonb_typeof(credit->'quantity') IS DISTINCT FROM 'string'
    OR credit->>'quantity' !~ '^[1-9][0-9]*$'
    THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
    amount_sum:=amount_sum+(credit->>'quantity')::numeric;
   END LOOP;
   IF amount_sum IS DISTINCT FROM (metric.value->>'value')::numeric
   OR (SELECT COUNT(DISTINCT x->>'player_id') FROM pg_catalog.jsonb_array_elements(metric.value->'credits') x)
      IS DISTINCT FROM pg_catalog.jsonb_array_length(metric.value->'credits')::bigint
   THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  ELSIF metric.value->>'state'='source_unavailable' THEN
   IF metric.value->'value' IS DISTINCT FROM 'null'::jsonb OR metric.value->'display' IS DISTINCT FROM 'null'::jsonb
   OR metric.value->>'reason' NOT IN ('MISSING_OBSERVATION','MISSING_ATTRIBUTION')
   OR metric.value->>'reason' IS NULL OR pg_catalog.jsonb_array_length(metric.value->'credits')<>0
   THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  ELSE RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 END LOOP;
 SELECT COALESCE(pg_catalog.array_agg(key ORDER BY key),'{}'::text[]) INTO new_keys
 FROM pg_catalog.jsonb_each(p_evaluation_json->'metrics') WHERE value->>'state'='available';
 eval_hash:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_evaluation_json::text,'UTF8')),'hex');

 SELECT v.* INTO series FROM sync_fence.stats_fact_versions v
 WHERE v.tenant_id=tenant AND v.game_id=p_game_id AND v.model_sha256=p_model_sha256
 AND v.is_current AND v.invalidated_at IS NULL FOR UPDATE;
 had_series:=FOUND;
 IF had_series THEN
  IF series.completion_state IS DISTINCT FROM 'current_open' OR series.rule_sha256 IS DISTINCT FROM rule_hash
  OR series.t5_artifact_set_sha256 IS DISTINCT FROM '3e2e03e605025f10aea5a449e1faa673bf34880bd88b5af84462a945054a40bf' THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  SELECT s.* INTO prior_source FROM sync_fence.stats_primitive_sources s
  WHERE s.tenant_id=tenant AND s.game_id=p_game_id AND s.fact_version_id=series.id AND s.source_event_id=p_source_event_id;
  IF FOUND THEN
   -- 同TXの同qualified source/evalだけを再掲。別TXの旧admissionは上段で拒否済み。
   IF prior_source.attempt_id IS DISTINCT FROM p_attempt_id OR prior_source.phase_id IS DISTINCT FROM p_phase_id
   OR prior_source.evaluation_sha256 IS DISTINCT FROM eval_hash OR prior_source.metric_states IS DISTINCT FROM p_evaluation_json
   OR prior_source.slot_version IS DISTINCT FROM current_source.slot_version
   OR prior_source.play_row_version IS DISTINCT FROM saved_play.version
   OR prior_source.source_fingerprint IS DISTINCT FROM binding.event_fingerprint
   OR prior_source.artifact_sha256 IS DISTINCT FROM current_source.artifact_sha256
   THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
   IF series.revision IS DISTINCT FROM p_expected_revision+1 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
   IF p_expected_revision=0 THEN
    IF series.source_count<>1 OR p_expected_source_set_sha256 IS NOT NULL THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
   ELSE
    SELECT * INTO STRICT previous_health FROM (WITH canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=tenant AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=p_game_id
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
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR p.hidden_at IS NOT NULL THEN 'source_unavailable'
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
 FROM canonical_scope g LEFT JOIN (SELECT * FROM canonical_s WHERE source_event_id IS DISTINCT FROM p_source_event_id) c
   ON c.tenant_id=g.tenant_id AND c.game_id=g.game_id
 GROUP BY g.tenant_id,g.game_id
)
SELECT COALESCE(ch.game_count,0) AS game_count,COALESCE(ch.canonical_source_count,0) AS canonical_source_count,COALESCE(ch.unavailable_count,0) AS unavailable_count,COALESCE(ch.canonical_source_set_sha256,encode(sha256(convert_to('accepted-play-slot-v1:empty','UTF8')),'hex')) AS canonical_source_set_sha256 FROM (VALUES(1)) singleton(n) LEFT JOIN canonical_health ch ON true) idempotent_previous_health;
    IF previous_health.game_count IS DISTINCT FROM 1::bigint
    OR previous_health.unavailable_count IS DISTINCT FROM 0::bigint
    OR previous_health.canonical_source_count IS DISTINCT FROM series.source_count-1
    OR previous_health.canonical_source_set_sha256 IS DISTINCT FROM p_expected_source_set_sha256
    THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
   END IF;
   p_fact_version_id:=series.id; p_revision:=series.revision; p_source_set_sha256:=series.source_set_sha256;
   p_player_id:=(event_row.payload#>>'{participants,pitcherId}')::uuid;
   SELECT * INTO STRICT audit FROM (WITH requested_metrics(metric_id) AS (VALUES ('pitch_count'), ('pa'), ('ab'), ('h'), ('hr'), ('bb'), ('hbp'), ('k'), ('sh'), ('sf'), ('catcher_interference_reached'), ('runner_interference_reached'), ('doubles'), ('triples'), ('total_bases'), ('runs'), ('rbi'), ('stolen_bases'), ('pitching_outs'), ('pitcher_k'), ('pitcher_bb'), ('pitcher_hbp'), ('hits_allowed'), ('home_runs_allowed'), ('fielding_errors'), ('runs_allowed')),
canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=tenant AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=p_game_id
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
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR p.hidden_at IS NOT NULL THEN 'source_unavailable'
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
, version_scope AS (
 SELECT v.* FROM sync_fence.stats_fact_versions v
 JOIN public.games g ON g.tenant_id=v.tenant_id AND g.id=v.game_id
 JOIN canonical_scope visible_game ON visible_game.tenant_id=v.tenant_id
   AND visible_game.game_id=v.game_id
 WHERE v.tenant_id=tenant AND v.model_sha256=p_model_sha256
   AND v.is_current=true AND v.invalidated_at IS NULL
   AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND v.game_id=p_game_id AND v.id=p_fact_version_id
   AND v.source_set_sha256=p_source_set_sha256 AND v.revision=p_revision
), source_members AS (
 SELECT s.* FROM sync_fence.stats_primitive_sources s
 JOIN version_scope v ON v.tenant_id=s.tenant_id AND v.game_id=s.game_id
   AND v.id=s.fact_version_id
 JOIN canonical_s c ON c.tenant_id=s.tenant_id AND c.game_id=s.game_id
   AND c.source_event_id=s.source_event_id AND c.recording_generation=s.recording_generation
   AND c.d1=s.d1 AND c.d2=s.d2 AND c.slot_version=s.slot_version
   AND c.play_row_id=s.play_row_id AND c.play_row_version=s.play_row_version
   AND c.source_fingerprint=s.source_fingerprint AND c.artifact_sha256=s.artifact_sha256
   AND c.source_state='included'
), scope_health AS (
 SELECT v.tenant_id,v.game_id,v.id,v.source_count,
   COUNT(s.source_event_id) AS actual_source_count
 FROM version_scope v LEFT JOIN source_members s ON s.tenant_id=v.tenant_id
   AND s.game_id=v.game_id AND s.fact_version_id=v.id
 GROUP BY v.tenant_id,v.game_id,v.id,v.source_count
), binding_health AS (
 SELECT h.*,
   (ch.game_id IS NULL OR h.source_count<>h.actual_source_count
    OR ch.unavailable_count>0 OR ch.canonical_source_count<>h.actual_source_count
    OR v.source_set_sha256<>ch.canonical_source_set_sha256) AS invalid
 FROM scope_health h JOIN version_scope v
   ON v.tenant_id=h.tenant_id AND v.game_id=h.game_id AND v.id=h.id
 LEFT JOIN canonical_health ch ON ch.tenant_id=h.tenant_id AND ch.game_id=h.game_id
), selected AS (
 SELECT s.tenant_id,s.game_id,CAST(p_player_id AS uuid) AS player_id,m.metric_id,
   CASE WHEN EXISTS (SELECT 1 FROM binding_health WHERE invalid)
     OR EXISTS (SELECT 1 FROM canonical_health ch LEFT JOIN version_scope bound_version
       ON bound_version.tenant_id=ch.tenant_id AND bound_version.game_id=ch.game_id
       WHERE bound_version.id IS NULL)
     OR NOT (m.metric_id=ANY(s.computed_metric_keys))
     OR COUNT(*) FILTER (WHERE f.source_event_id IS NOT NULL AND (f.state<>'available' OR f.amount IS NULL))>0
     THEN NULL ELSE COALESCE(SUM(f.amount),0) END AS amount,
   CASE WHEN EXISTS (SELECT 1 FROM binding_health WHERE invalid)
     OR EXISTS (SELECT 1 FROM canonical_health ch LEFT JOIN version_scope bound_version
       ON bound_version.tenant_id=ch.tenant_id AND bound_version.game_id=ch.game_id
       WHERE bound_version.id IS NULL)
     OR NOT (m.metric_id=ANY(s.computed_metric_keys))
     OR COUNT(*) FILTER (WHERE f.source_event_id IS NOT NULL AND (f.state<>'available' OR f.amount IS NULL))>0
     THEN 'source_unavailable' ELSE 'available' END AS state,
   s.source_event_id,s.d2
 FROM source_members s CROSS JOIN requested_metrics m
 LEFT JOIN sync_fence.stats_primitive_facts f ON f.tenant_id=s.tenant_id AND f.game_id=s.game_id
   AND f.fact_version_id=s.fact_version_id AND f.source_event_id=s.source_event_id
   AND f.metric_id=m.metric_id AND f.player_id=p_player_id
 GROUP BY s.tenant_id,s.game_id,s.fact_version_id,s.source_event_id,s.d2,
   s.computed_metric_keys,m.metric_id
)
SELECT v.id AS fact_version_id,v.revision,v.source_set_sha256,v.model_sha256,
 v.source_count,(SELECT COUNT(*) FROM selected) AS row_count,
 pg_current_snapshot()::text AS transaction_id,v.completion_state,
 h.actual_source_count,ch.canonical_source_count,ch.unavailable_count,
 ch.canonical_source_set_sha256
FROM version_scope v JOIN scope_health h
 ON h.tenant_id=v.tenant_id AND h.game_id=v.game_id AND h.id=v.id
JOIN canonical_health ch ON ch.tenant_id=v.tenant_id AND ch.game_id=v.game_id) idempotent_counts;
    IF audit.fact_version_id IS NULL OR audit.model_sha256 IS DISTINCT FROM p_model_sha256
 OR audit.completion_state IS DISTINCT FROM 'current_open'
 OR audit.source_count IS DISTINCT FROM audit.actual_source_count
 OR audit.source_count IS DISTINCT FROM audit.canonical_source_count
 OR audit.unavailable_count IS DISTINCT FROM 0::bigint
 OR audit.source_set_sha256 IS DISTINCT FROM audit.canonical_source_set_sha256
 OR audit.row_count IS DISTINCT FROM audit.source_count*26
 OR (SELECT COUNT(*) FROM sync_fence.stats_primitive_sources s WHERE s.tenant_id=tenant
 AND s.game_id=p_game_id AND s.fact_version_id=p_fact_version_id) IS DISTINCT FROM audit.source_count

 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 -- 内容を再計算せず、保存済み唯一T5応答の全creditと実fact集合を双方向比較する。
 IF EXISTS(SELECT 1 FROM sync_fence.stats_primitive_sources s
 WHERE s.tenant_id=tenant AND s.game_id=p_game_id AND s.fact_version_id=p_fact_version_id
 AND s.evaluation_sha256 IS DISTINCT FROM pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 s.metric_states::text,'UTF8')),'hex')) OR EXISTS(
 WITH expected_credits AS (
  SELECT s.source_event_id,m.key AS metric_id,(c.value->>'player_id')::uuid AS player_id,
  c.ordinality-1 AS credit_ordinal,'available'::text AS state,(c.value->>'quantity')::numeric AS amount
  FROM sync_fence.stats_primitive_sources s
  CROSS JOIN LATERAL pg_catalog.jsonb_each(s.metric_states->'metrics') m
  CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(m.value->'credits') WITH ORDINALITY c
  WHERE s.tenant_id=tenant AND s.game_id=p_game_id AND s.fact_version_id=p_fact_version_id
 ), actual_credits AS (
  SELECT f.source_event_id,f.metric_id,f.player_id,f.credit_ordinal,f.state,f.amount
  FROM sync_fence.stats_primitive_facts f WHERE f.tenant_id=tenant AND f.game_id=p_game_id
  AND f.fact_version_id=p_fact_version_id
 )
 (SELECT * FROM expected_credits EXCEPT SELECT * FROM actual_credits)
 UNION ALL (SELECT * FROM actual_credits EXCEPT SELECT * FROM expected_credits)
 ) THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;

   PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,p_binding_nonce,binding.device_id,binding.game_id);
 RETURN QUERY SELECT series.id,p_source_event_id,p_model_sha256,series.source_set_sha256;
   RETURN;
  END IF;
  IF series.revision IS DISTINCT FROM p_expected_revision OR series.source_set_sha256 IS DISTINCT FROM p_expected_source_set_sha256
  THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  SELECT * INTO STRICT previous_health FROM (WITH canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=tenant AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=p_game_id
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
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR p.hidden_at IS NOT NULL THEN 'source_unavailable'
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
 FROM canonical_scope g LEFT JOIN (SELECT * FROM canonical_s WHERE source_event_id IS DISTINCT FROM p_source_event_id) c
   ON c.tenant_id=g.tenant_id AND c.game_id=g.game_id
 GROUP BY g.tenant_id,g.game_id
)
SELECT COALESCE(ch.game_count,0) AS game_count,COALESCE(ch.canonical_source_count,0) AS canonical_source_count,COALESCE(ch.unavailable_count,0) AS unavailable_count,COALESCE(ch.canonical_source_set_sha256,encode(sha256(convert_to('accepted-play-slot-v1:empty','UTF8')),'hex')) AS canonical_source_set_sha256 FROM (VALUES(1)) singleton(n) LEFT JOIN canonical_health ch ON true) previous_canonical_health;
  IF previous_health.game_count IS DISTINCT FROM 1::bigint OR previous_health.unavailable_count IS DISTINCT FROM 0::bigint
  OR previous_health.canonical_source_count IS DISTINCT FROM series.source_count
  OR previous_health.canonical_source_set_sha256 IS DISTINCT FROM series.source_set_sha256
  OR health.canonical_source_count IS DISTINCT FROM series.source_count+1
  THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 ELSE
  IF p_expected_revision<>0 OR p_expected_source_set_sha256 IS NOT NULL OR health.canonical_source_count<>1
  THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
  INSERT INTO sync_fence.stats_fact_versions(tenant_id,game_id,id,model_sha256,rule_sha256,
  t5_artifact_set_sha256,source_set_sha256,source_count,revision,last_generation,last_d1,last_d2,updated_at,
  computed_metric_keys,is_current,completion_state,completion_receipt_id,public_pointer_receipt_id,created_at,invalidated_at)
  VALUES(tenant,p_game_id,pg_catalog.gen_random_uuid(),p_model_sha256,rule_hash,'3e2e03e605025f10aea5a449e1faa673bf34880bd88b5af84462a945054a40bf',
  health.canonical_source_set_sha256,1,1,event_row.generation,event_row.d1,event_row.d2,pg_catalog.clock_timestamp(),
  new_keys,true,'current_open',NULL,NULL,pg_catalog.clock_timestamp(),NULL) RETURNING * INTO STRICT series;
 END IF;
 INSERT INTO sync_fence.stats_primitive_sources(tenant_id,game_id,fact_version_id,source_event_id,play_row_id,
 recording_generation,d1,d2,slot_version,play_row_version,provider_kind,attempt_id,phase_id,wire_d4,source_fingerprint,
 checkpoint_id,checkpoint_revision,checkpoint_digest,frame_digest,evaluation_sha256,artifact_sha256,rule_sha256,
 metric_states,computed_metric_keys,saved_at)
 VALUES(tenant,p_game_id,series.id,p_source_event_id,saved_play.id,event_row.generation,event_row.d1,event_row.d2,
 current_source.slot_version,saved_play.version,provider,p_attempt_id,p_phase_id,binding.wire_d4,binding.event_fingerprint,
 checkpoint_id,checkpoint_revision,checkpoint_digest,frame_digest,eval_hash,current_source.artifact_sha256,rule_hash,
 p_evaluation_json,new_keys,pg_catalog.clock_timestamp());
 FOR metric IN SELECT key,value FROM pg_catalog.jsonb_each(p_evaluation_json->'metrics') LOOP
  credit_ordinal:=0;
  FOR credit IN SELECT value FROM pg_catalog.jsonb_array_elements(metric.value->'credits') LOOP
   INSERT INTO sync_fence.stats_primitive_facts(tenant_id,game_id,fact_version_id,source_event_id,
   metric_id,player_id,credit_ordinal,state,amount)
   VALUES(tenant,p_game_id,series.id,p_source_event_id,metric.key,(credit->>'player_id')::uuid,
   credit_ordinal,'available',(credit->>'quantity')::numeric);
   credit_ordinal:=credit_ordinal+1;
  END LOOP;
 END LOOP;
 IF had_series THEN
  UPDATE sync_fence.stats_fact_versions v SET revision=v.revision+1,
  source_set_sha256=health.canonical_source_set_sha256,source_count=health.canonical_source_count,
  computed_metric_keys=ARRAY(SELECT x FROM pg_catalog.unnest(v.computed_metric_keys) x WHERE x=ANY(new_keys) ORDER BY x),
  last_generation=event_row.generation,last_d1=event_row.d1,last_d2=event_row.d2,updated_at=pg_catalog.clock_timestamp()
  WHERE v.tenant_id=tenant AND v.game_id=p_game_id AND v.id=series.id AND v.is_current AND v.invalidated_at IS NULL
  AND v.completion_state='current_open' AND v.revision=p_expected_revision AND v.source_set_sha256=p_expected_source_set_sha256
  AND v.model_sha256=p_model_sha256 AND v.rule_sha256=rule_hash AND v.t5_artifact_set_sha256='3e2e03e605025f10aea5a449e1faa673bf34880bd88b5af84462a945054a40bf'
  RETURNING * INTO STRICT series;
 END IF;
 p_fact_version_id:=series.id; p_revision:=series.revision; p_source_set_sha256:=series.source_set_sha256;
 p_player_id:=(event_row.payload#>>'{participants,pitcherId}')::uuid;
 SELECT * INTO STRICT audit FROM (WITH requested_metrics(metric_id) AS (VALUES ('pitch_count'), ('pa'), ('ab'), ('h'), ('hr'), ('bb'), ('hbp'), ('k'), ('sh'), ('sf'), ('catcher_interference_reached'), ('runner_interference_reached'), ('doubles'), ('triples'), ('total_bases'), ('runs'), ('rbi'), ('stolen_bases'), ('pitching_outs'), ('pitcher_k'), ('pitcher_bb'), ('pitcher_hbp'), ('hits_allowed'), ('home_runs_allowed'), ('fielding_errors'), ('runs_allowed')),
canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=tenant AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=p_game_id
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
     WHEN e.event_kind<>'play_input' THEN 'excluded_control'
     WHEN e.is_tombstone OR current_event.is_tombstone THEN 'excluded_tombstone'
     WHEN current_event.event_kind='play_delete' THEN 'excluded_delete'
     WHEN slot.d1>gen.confirmed_watermark OR slot.d1>gen.applied_prefix THEN 'source_unavailable'
     WHEN ledger.kind IS DISTINCT FROM 'accepted' OR ledger.retired_at IS NOT NULL
       OR p.id IS NULL OR p.hidden_at IS NOT NULL THEN 'source_unavailable'
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
, version_scope AS (
 SELECT v.* FROM sync_fence.stats_fact_versions v
 JOIN public.games g ON g.tenant_id=v.tenant_id AND g.id=v.game_id
 JOIN canonical_scope visible_game ON visible_game.tenant_id=v.tenant_id
   AND visible_game.game_id=v.game_id
 WHERE v.tenant_id=tenant AND v.model_sha256=p_model_sha256
   AND v.is_current=true AND v.invalidated_at IS NULL
   AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND v.game_id=p_game_id AND v.id=p_fact_version_id
   AND v.source_set_sha256=p_source_set_sha256 AND v.revision=p_revision
), source_members AS (
 SELECT s.* FROM sync_fence.stats_primitive_sources s
 JOIN version_scope v ON v.tenant_id=s.tenant_id AND v.game_id=s.game_id
   AND v.id=s.fact_version_id
 JOIN canonical_s c ON c.tenant_id=s.tenant_id AND c.game_id=s.game_id
   AND c.source_event_id=s.source_event_id AND c.recording_generation=s.recording_generation
   AND c.d1=s.d1 AND c.d2=s.d2 AND c.slot_version=s.slot_version
   AND c.play_row_id=s.play_row_id AND c.play_row_version=s.play_row_version
   AND c.source_fingerprint=s.source_fingerprint AND c.artifact_sha256=s.artifact_sha256
   AND c.source_state='included'
), scope_health AS (
 SELECT v.tenant_id,v.game_id,v.id,v.source_count,
   COUNT(s.source_event_id) AS actual_source_count
 FROM version_scope v LEFT JOIN source_members s ON s.tenant_id=v.tenant_id
   AND s.game_id=v.game_id AND s.fact_version_id=v.id
 GROUP BY v.tenant_id,v.game_id,v.id,v.source_count
), binding_health AS (
 SELECT h.*,
   (ch.game_id IS NULL OR h.source_count<>h.actual_source_count
    OR ch.unavailable_count>0 OR ch.canonical_source_count<>h.actual_source_count
    OR v.source_set_sha256<>ch.canonical_source_set_sha256) AS invalid
 FROM scope_health h JOIN version_scope v
   ON v.tenant_id=h.tenant_id AND v.game_id=h.game_id AND v.id=h.id
 LEFT JOIN canonical_health ch ON ch.tenant_id=h.tenant_id AND ch.game_id=h.game_id
), selected AS (
 SELECT s.tenant_id,s.game_id,CAST(p_player_id AS uuid) AS player_id,m.metric_id,
   CASE WHEN EXISTS (SELECT 1 FROM binding_health WHERE invalid)
     OR EXISTS (SELECT 1 FROM canonical_health ch LEFT JOIN version_scope bound_version
       ON bound_version.tenant_id=ch.tenant_id AND bound_version.game_id=ch.game_id
       WHERE bound_version.id IS NULL)
     OR NOT (m.metric_id=ANY(s.computed_metric_keys))
     OR COUNT(*) FILTER (WHERE f.source_event_id IS NOT NULL AND (f.state<>'available' OR f.amount IS NULL))>0
     THEN NULL ELSE COALESCE(SUM(f.amount),0) END AS amount,
   CASE WHEN EXISTS (SELECT 1 FROM binding_health WHERE invalid)
     OR EXISTS (SELECT 1 FROM canonical_health ch LEFT JOIN version_scope bound_version
       ON bound_version.tenant_id=ch.tenant_id AND bound_version.game_id=ch.game_id
       WHERE bound_version.id IS NULL)
     OR NOT (m.metric_id=ANY(s.computed_metric_keys))
     OR COUNT(*) FILTER (WHERE f.source_event_id IS NOT NULL AND (f.state<>'available' OR f.amount IS NULL))>0
     THEN 'source_unavailable' ELSE 'available' END AS state,
   s.source_event_id,s.d2
 FROM source_members s CROSS JOIN requested_metrics m
 LEFT JOIN sync_fence.stats_primitive_facts f ON f.tenant_id=s.tenant_id AND f.game_id=s.game_id
   AND f.fact_version_id=s.fact_version_id AND f.source_event_id=s.source_event_id
   AND f.metric_id=m.metric_id AND f.player_id=p_player_id
 GROUP BY s.tenant_id,s.game_id,s.fact_version_id,s.source_event_id,s.d2,
   s.computed_metric_keys,m.metric_id
)
SELECT v.id AS fact_version_id,v.revision,v.source_set_sha256,v.model_sha256,
 v.source_count,(SELECT COUNT(*) FROM selected) AS row_count,
 pg_current_snapshot()::text AS transaction_id,v.completion_state,
 h.actual_source_count,ch.canonical_source_count,ch.unavailable_count,
 ch.canonical_source_set_sha256
FROM version_scope v JOIN scope_health h
 ON h.tenant_id=v.tenant_id AND h.game_id=v.game_id AND h.id=v.id
JOIN canonical_health ch ON ch.tenant_id=v.tenant_id AND ch.game_id=v.game_id) completed_counts;
  IF audit.fact_version_id IS NULL OR audit.model_sha256 IS DISTINCT FROM p_model_sha256
 OR audit.completion_state IS DISTINCT FROM 'current_open'
 OR audit.source_count IS DISTINCT FROM audit.actual_source_count
 OR audit.source_count IS DISTINCT FROM audit.canonical_source_count
 OR audit.unavailable_count IS DISTINCT FROM 0::bigint
 OR audit.source_set_sha256 IS DISTINCT FROM audit.canonical_source_set_sha256
 OR audit.row_count IS DISTINCT FROM audit.source_count*26
 OR (SELECT COUNT(*) FROM sync_fence.stats_primitive_sources s WHERE s.tenant_id=tenant
 AND s.game_id=p_game_id AND s.fact_version_id=p_fact_version_id) IS DISTINCT FROM audit.source_count

 THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;
 -- 内容を再計算せず、保存済み唯一T5応答の全creditと実fact集合を双方向比較する。
 IF EXISTS(SELECT 1 FROM sync_fence.stats_primitive_sources s
 WHERE s.tenant_id=tenant AND s.game_id=p_game_id AND s.fact_version_id=p_fact_version_id
 AND s.evaluation_sha256 IS DISTINCT FROM pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 s.metric_states::text,'UTF8')),'hex')) OR EXISTS(
 WITH expected_credits AS (
  SELECT s.source_event_id,m.key AS metric_id,(c.value->>'player_id')::uuid AS player_id,
  c.ordinality-1 AS credit_ordinal,'available'::text AS state,(c.value->>'quantity')::numeric AS amount
  FROM sync_fence.stats_primitive_sources s
  CROSS JOIN LATERAL pg_catalog.jsonb_each(s.metric_states->'metrics') m
  CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(m.value->'credits') WITH ORDINALITY c
  WHERE s.tenant_id=tenant AND s.game_id=p_game_id AND s.fact_version_id=p_fact_version_id
 ), actual_credits AS (
  SELECT f.source_event_id,f.metric_id,f.player_id,f.credit_ordinal,f.state,f.amount
  FROM sync_fence.stats_primitive_facts f WHERE f.tenant_id=tenant AND f.game_id=p_game_id
  AND f.fact_version_id=p_fact_version_id
 )
 (SELECT * FROM expected_credits EXCEPT SELECT * FROM actual_credits)
 UNION ALL (SELECT * FROM actual_credits EXCEPT SELECT * FROM expected_credits)
 ) THEN RAISE EXCEPTION 'stats primitive boundary rejected' USING ERRCODE='42501'; END IF;

 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,p_binding_nonce,binding.device_id,binding.game_id);
 RETURN QUERY SELECT series.id,p_source_event_id,p_model_sha256,series.source_set_sha256;

END;
$stats$;

ALTER FUNCTION stats_api.save_primitive_source(uuid, uuid, uuid, text, bigint, text, jsonb, bytea) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.save_primitive_source(uuid, uuid, uuid, text, bigint, text, jsonb, bytea) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION stats_api.save_primitive_source(uuid, uuid, uuid, text, bigint, text, jsonb, bytea) TO pitchlog_app;
