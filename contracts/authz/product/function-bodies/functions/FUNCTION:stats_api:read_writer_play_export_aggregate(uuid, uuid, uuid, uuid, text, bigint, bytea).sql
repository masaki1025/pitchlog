-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:read_writer_play_export_aggregate(uuid, uuid, uuid, uuid, text, bigint, bytea)

CREATE FUNCTION stats_api.read_writer_play_export_aggregate(p_attempt_id uuid,p_phase_id uuid,p_source_event_id uuid,p_fact_version_id uuid,p_source_set_sha256 text,p_revision bigint,p_binding_nonce bytea)
RETURNS TABLE(pitcher_pitch_count bigint,top_score jsonb,bottom_score jsonb,
  full_innings jsonb) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $export$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; p_game_id uuid;
  model_hash text := 'sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6';
  binding_device uuid; binding_generation bigint; binding_d5 uuid;
  event_accepted integer;
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
   OR tenant IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL
   OR p_source_event_id IS NULL OR p_fact_version_id IS NULL
   OR p_source_set_sha256 IS NULL OR p_source_set_sha256 !~ '^[a-f0-9]{64}$'
   OR p_revision IS NULL OR p_revision<1 OR p_binding_nonce IS NULL
   OR pg_catalog.octet_length(p_binding_nonce)<>32
   OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 THEN RAISE EXCEPTION 'play export writer boundary rejected'
   USING ERRCODE='42501'; END IF;
 SELECT b.game_id,b.device_id,b.internal_generation,b.d5
   INTO STRICT p_game_id,binding_device,binding_generation,binding_d5
 FROM sync_fence.writer_bindings b
 WHERE b.tenant_id=tenant AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id
   AND b.state='open' AND b.transaction_id=own_xid
   AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
   p_binding_nonce,binding_device,p_game_id);
 SELECT 1 INTO STRICT event_accepted FROM public.operation_events e
 WHERE e.tenant_id=tenant AND e.game_id=p_game_id AND e.id=p_source_event_id
   AND e.generation=binding_generation AND e.d5=binding_d5
   AND e.event_kind='play_input' AND e.ledger_kind='accepted'
   AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
   AND e.import_batch_id IS NULL AND NOT e.migration_unverified
   AND e.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 RETURN QUERY
 WITH canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=tenant AND g.hidden_at IS NULL AND g.trashed_at IS NULL
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
 AND n.checkpoint_digest=n.preparation->'storage'->'row'->>'content_digest'
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
   CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.effective_event_id ELSE CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END END AS source_event_id,
   p.id AS play_row_id,p.version AS play_row_version,
   current_event.d5,ledger.source_fingerprint,
   CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.payload->>'formatVersion' ELSE current_event.payload->>'formatVersion' END AS native_variant,
   CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.payload#>>'{calculation,artifactSha256}' ELSE current_event.payload#>>'{calculation,artifactSha256}' END AS artifact_sha256,
   COUNT(*) OVER (PARTITION BY slot.tenant_id,slot.game_id,slot.generation,slot.d1) AS match_count,
   CASE WHEN gen.retired_at IS NOT NULL THEN 'excluded_retired'
     WHEN e.id IS NULL OR current_event.id IS NULL THEN 'source_unavailable'
     WHEN p3h.capsule_id IS NOT NULL AND (
       p3c.id IS NULL OR p3c.source_set_digest IS DISTINCT FROM p3h.source_set_digest
       OR p3c.stats_version_id IS DISTINCT FROM p3h.stats_version_id
       OR (slot.d1<=p3c.watermark AND (
       p3i.d1 IS NULL OR p3i.original_event_id IS DISTINCT FROM e.id
       OR p3i.effective_event_id IS DISTINCT FROM
         (CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END)
       OR p3i.effective_play_row_id IS DISTINCT FROM p.id
       OR p3i.original_payload IS DISTINCT FROM e.payload
       OR p3i.play_row IS DISTINCT FROM pg_catalog.to_jsonb(p)
       OR p3i.payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v3'))
     ) THEN 'source_unavailable'
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
 LEFT JOIN sync_fence.p3_projection_heads p3h
   ON (p3h.tenant_id,p3h.game_id,p3h.internal_generation)
   =(slot.tenant_id,slot.game_id,slot.generation)
 LEFT JOIN sync_fence.p3_projection_capsules p3c
   ON (p3c.tenant_id,p3c.game_id,p3c.internal_generation,p3c.id)
   =(p3h.tenant_id,p3h.game_id,p3h.internal_generation,p3h.capsule_id)
 LEFT JOIN sync_fence.p3_projection_capsule_items p3i
   ON (p3i.tenant_id,p3i.game_id,p3i.internal_generation,p3i.capsule_id,p3i.d1)
   =(p3h.tenant_id,p3h.game_id,p3h.internal_generation,p3h.capsule_id,slot.d1)
 LEFT JOIN public.operation_events current_event ON current_event.tenant_id=slot.tenant_id
   AND current_event.game_id=slot.game_id
   AND current_event.id=CASE WHEN p3h.capsule_id IS NOT NULL AND slot.d1<=p3c.watermark THEN p3i.effective_event_id ELSE CASE WHEN slot.confirmed_version=1 THEN e.id ELSE change.id END END
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
), version_scope AS (
 SELECT v.* FROM sync_fence.stats_fact_versions v
 JOIN canonical_health h ON h.tenant_id=v.tenant_id AND h.game_id=v.game_id
 WHERE v.tenant_id=tenant AND v.game_id=p_game_id
   AND v.id=p_fact_version_id AND v.model_sha256=model_hash
   AND v.source_set_sha256=p_source_set_sha256 AND v.revision=p_revision
   AND v.is_current AND v.invalidated_at IS NULL
   AND v.completion_state='current_open'
   AND h.game_count=1 AND h.unavailable_count=0
   AND h.canonical_source_count=v.source_count
   AND h.canonical_source_set_sha256=v.source_set_sha256
), candidate_members AS (
 SELECT s.* FROM sync_fence.stats_primitive_sources s
 JOIN canonical_s c ON c.tenant_id=s.tenant_id AND c.game_id=s.game_id
   AND c.source_event_id=s.source_event_id AND c.recording_generation=s.recording_generation
   AND c.d1=s.d1 AND c.d2=s.d2 AND c.slot_version=s.slot_version
   AND c.play_row_id=s.play_row_id AND c.play_row_version=s.play_row_version
   AND c.source_fingerprint=s.source_fingerprint AND c.artifact_sha256=s.artifact_sha256
   AND c.source_state='included'
WHERE s.tenant_id=tenant AND s.game_id=p_game_id AND s.fact_version_id=p_fact_version_id
), source_members AS (
 SELECT s.* FROM candidate_members s JOIN version_scope v
   ON (v.tenant_id,v.game_id,v.id)=(s.tenant_id,s.game_id,s.fact_version_id)
), member_health AS (
 SELECT v.id,COUNT(s.source_event_id) AS actual_count,v.source_count
 FROM version_scope v LEFT JOIN source_members s
   ON (s.tenant_id,s.game_id,s.fact_version_id)=(v.tenant_id,v.game_id,v.id)
 GROUP BY v.id,v.source_count
), target AS (
 SELECT s.source_event_id,s.d2,p.pitcher_id
 FROM source_members s JOIN public.play_rows p
   ON (p.tenant_id,p.game_id,p.id)=(s.tenant_id,s.game_id,s.play_row_id)
 JOIN public.operation_events e
   ON (e.tenant_id,e.game_id,e.id)=
     (s.tenant_id,s.game_id,s.source_event_id)
 LEFT JOIN sync_fence.p3_projection_heads export_head
   ON (export_head.tenant_id,export_head.game_id,export_head.internal_generation)
     =(s.tenant_id,s.game_id,s.recording_generation)
 LEFT JOIN sync_fence.p3_projection_capsules export_p3
   ON (export_p3.tenant_id,export_p3.game_id,export_p3.internal_generation,export_p3.id)
     =(export_head.tenant_id,export_head.game_id,export_head.internal_generation,
       export_head.capsule_id)
 LEFT JOIN sync_fence.p3_projection_capsule_items export_item
   ON (export_item.tenant_id,export_item.game_id,export_item.internal_generation,
       export_item.capsule_id,export_item.d1,export_item.effective_event_id,
       export_item.effective_play_row_id)
     =(s.tenant_id,s.game_id,s.recording_generation,export_p3.id,s.d1,
       s.source_event_id,s.play_row_id)
 WHERE s.source_event_id=p_source_event_id AND p.event_kind IN ('pitch','non_pitch')
   AND p.source_event_id=s.source_event_id AND p.version=s.play_row_version
   AND ((p.event_kind='pitch' AND CASE WHEN export_p3.id IS NOT NULL AND s.d1<=export_p3.watermark THEN export_item.payload ELSE e.payload END#>>'{calculation,request,t1,pitchEventKind}'='pitch-event') OR (p.event_kind='non_pitch' AND CASE WHEN export_p3.id IS NOT NULL AND s.d1<=export_p3.watermark THEN export_item.payload ELSE e.payload END#>>'{calculation,request,t1,pitchEventKind}'='non-pitch-event'))
), bounded AS (
 SELECT s.*,CASE WHEN export_p3.id IS NOT NULL AND s.d1<=export_p3.watermark THEN export_item.payload ELSE e.payload END AS payload,p.event_kind,p.pitcher_id
 FROM source_members s JOIN target t
   ON (s.d2,s.source_event_id)<=(t.d2,t.source_event_id)
 JOIN public.operation_events e
   ON (e.tenant_id,e.game_id,e.id)=(s.tenant_id,s.game_id,s.source_event_id)
 JOIN public.play_rows p
   ON (p.tenant_id,p.game_id,p.id)=(s.tenant_id,s.game_id,s.play_row_id)
 LEFT JOIN sync_fence.p3_projection_heads export_head
   ON (export_head.tenant_id,export_head.game_id,export_head.internal_generation)
     =(s.tenant_id,s.game_id,s.recording_generation)
 LEFT JOIN sync_fence.p3_projection_capsules export_p3
   ON (export_p3.tenant_id,export_p3.game_id,export_p3.internal_generation,export_p3.id)
     =(export_head.tenant_id,export_head.game_id,export_head.internal_generation,
       export_head.capsule_id)
 LEFT JOIN sync_fence.p3_projection_capsule_items export_item
   ON (export_item.tenant_id,export_item.game_id,export_item.internal_generation,
       export_item.capsule_id,export_item.d1,export_item.effective_event_id,
       export_item.effective_play_row_id)
     =(s.tenant_id,s.game_id,s.recording_generation,export_p3.id,s.d1,
       s.source_event_id,s.play_row_id)
 WHERE p.version=s.play_row_version AND p.source_event_id=s.source_event_id
), raw_frame AS (
 SELECT b.*,b.payload#>>'{calculation,request,t1,before,stateFields,state.inning}'
     AS inning_text,
   b.payload#>>'{calculation,request,t1,before,stateFields,state.half}' AS half,
   CASE
    WHEN b.payload->>'formatVersion'='first-ball-play-v1' AND b.payload#>>'{calculation,formatVersion}'='first-ball-calculation-v1' AND b.payload#>>'{calculation,response,value,t2,kind}'='evaluated-no-end-condition' AND b.payload#>>'{calculation,response,value,t2,scope}' IS NULL THEN 'false'::jsonb
    WHEN b.payload->>'formatVersion'='ordinary-pitch-play-v1' AND b.payload#>>'{calculation,formatVersion}'='ordinary-pitch-calculation-v1' AND b.payload#>>'{calculation,response,value,t2,kind}'='evaluated-no-end-condition' AND b.payload#>>'{calculation,response,value,t2,scope}'='ordinary37' THEN b.payload#>'{calculation,response,value,t2,basis,halfCompleted}'
    WHEN b.payload->>'formatVersion'='play-prefix-play-v2' AND b.payload#>>'{calculation,formatVersion}'='play-prefix-calculation-v2' AND b.payload#>>'{calculation,response,value,t2,kind}'='evaluated-no-end-condition' AND b.payload#>>'{calculation,response,value,t2,scope}'='play-prefix-v2' THEN b.payload#>'{calculation,response,value,t2,basis,halfCompleted}'
    WHEN b.payload->>'formatVersion'='play-prefix-play-v3' AND b.payload#>>'{calculation,formatVersion}'='play-prefix-calculation-v3' AND b.payload#>>'{calculation,response,value,t2,kind}'='evaluated-end-condition' AND b.payload#>>'{calculation,response,value,t2,scope}'='play-prefix-v3' THEN b.payload#>'{calculation,response,value,t2,facts,halfCompleted}'
    WHEN b.payload->>'formatVersion'='play-prefix-play-v3' AND b.payload#>>'{calculation,formatVersion}'='nonplay-prefix-calculation-v1' AND b.payload#>>'{calculation,response,value,t2,kind}'='evaluated-end-condition' AND b.payload#>>'{calculation,response,value,t2,scope}'='play-prefix-v3' THEN b.payload#>'{calculation,response,value,t2,facts,halfCompleted}'
    ELSE NULL END AS complete_json,
   b.payload#>>'{calculation,request,t1,before,scoreboard,inningScores,away}'
     AS before_away,
   b.payload#>>'{calculation,response,value,t1,after,scoreboard,inningScores,away}'
     AS after_away,
   b.payload#>>'{calculation,request,t1,before,scoreboard,inningScores,home}'
     AS before_home,
   b.payload#>>'{calculation,response,value,t1,after,scoreboard,inningScores,home}'
     AS after_home,
   b.payload#>>'{calculation,request,t1,before,scoreboard,hits}' AS before_hits,
   b.payload#>>'{calculation,response,value,t1,after,scoreboard,hits}' AS after_hits,
   b.payload#>>'{calculation,request,t1,before,scoreboard,errors}' AS before_errors,
   b.payload#>>'{calculation,response,value,t1,after,scoreboard,errors}'
     AS after_errors,
   b.payload#>>'{calculation,request,t1,before,scoreboard,strikeouts}'
     AS before_strikeouts,
   b.payload#>>'{calculation,response,value,t1,after,scoreboard,strikeouts}'
     AS after_strikeouts,
   b.payload#>>'{calculation,request,t1,before,scoreboard,walks}' AS before_walks,
   b.payload#>>'{calculation,response,value,t1,after,scoreboard,walks}' AS after_walks
 FROM bounded b
), checked_frame AS (
 SELECT r.*,
   r.inning_text ~ '^[1-9][0-9]{0,17}$' AND r.half IN ('top','bottom')
   AND r.complete_json IN ('true'::jsonb,'false'::jsonb)
   AND r.before_away ~ '^(0|[1-9][0-9]{0,17})$'
   AND r.after_away ~ '^(0|[1-9][0-9]{0,17})$'
   AND r.before_home ~ '^(0|[1-9][0-9]{0,17})$'
   AND r.after_home ~ '^(0|[1-9][0-9]{0,17})$'
   AND r.before_hits ~ '^(0|[1-9][0-9]{0,17})$'
   AND r.after_hits ~ '^(0|[1-9][0-9]{0,17})$'
   AND r.before_errors ~ '^(0|[1-9][0-9]{0,17})$'
   AND r.after_errors ~ '^(0|[1-9][0-9]{0,17})$'
   AND r.before_strikeouts ~ '^(0|[1-9][0-9]{0,17})$'
   AND r.after_strikeouts ~ '^(0|[1-9][0-9]{0,17})$'
   AND r.before_walks ~ '^(0|[1-9][0-9]{0,17})$'
   AND r.after_walks ~ '^(0|[1-9][0-9]{0,17})$' AS shape_ok
 FROM raw_frame r
), score_delta AS (
 SELECT c.source_event_id,c.d2,c.event_kind,c.pitcher_id,c.fact_version_id,
   CASE WHEN shape_ok THEN inning_text::bigint END AS inning,
   half,CASE WHEN shape_ok THEN complete_json='true'::jsonb END AS completed,
   CASE WHEN shape_ok THEN after_away::bigint-before_away::bigint END AS away_runs,
   CASE WHEN shape_ok THEN after_home::bigint-before_home::bigint END AS home_runs,
   CASE WHEN shape_ok THEN after_hits::bigint-before_hits::bigint END AS hits,
   CASE WHEN shape_ok THEN after_errors::bigint-before_errors::bigint END AS errors,
   CASE WHEN shape_ok THEN after_strikeouts::bigint-before_strikeouts::bigint
   END AS strikeouts,
   CASE WHEN shape_ok THEN after_walks::bigint-before_walks::bigint END AS walks,
   shape_ok
 FROM checked_frame c
), score_health AS (
 SELECT COUNT(*)=COUNT(*) FILTER (WHERE shape_ok AND inning>0 AND inning<=100000
   AND away_runs>=0 AND home_runs>=0 AND hits>=0 AND errors>=0
   AND strikeouts>=0 AND walks>=0
   AND ((half='top' AND home_runs=0) OR (half='bottom' AND away_runs=0))) AS valid
 FROM score_delta
), score_rows AS (
 SELECT half,inning,
   SUM(CASE WHEN half='top' THEN away_runs ELSE home_runs END)::bigint AS runs,
   BOOL_OR(completed) AS completed,
   SUM(hits)::bigint AS hits,SUM(errors)::bigint AS errors,
   SUM(strikeouts)::bigint AS strikeouts,SUM(walks)::bigint AS walks
 FROM score_delta GROUP BY half,inning
), score_totals AS (
 SELECT COALESCE(SUM(hits) FILTER (WHERE half='top'),0)::bigint AS top_hits,
   COALESCE(SUM(errors) FILTER (WHERE half='bottom'),0)::bigint AS top_errors,
   COALESCE(SUM(strikeouts) FILTER (WHERE half='top'),0)::bigint AS top_strikeouts,
   COALESCE(SUM(walks) FILTER (WHERE half='top'),0)::bigint AS top_walks,
   COALESCE(SUM(hits) FILTER (WHERE half='bottom'),0)::bigint AS bottom_hits,
   COALESCE(SUM(errors) FILTER (WHERE half='top'),0)::bigint AS bottom_errors,
   COALESCE(SUM(strikeouts) FILTER (WHERE half='bottom'),0)::bigint
     AS bottom_strikeouts,
   COALESCE(SUM(walks) FILTER (WHERE half='bottom'),0)::bigint AS bottom_walks
 FROM score_rows
), legacy_cells AS (
 SELECT half,LEAST(inning,12) AS slot,SUM(runs)::bigint AS runs,
   BOOL_OR(completed) AS completed
 FROM score_rows GROUP BY half,LEAST(inning,12)
), legacy_arrays AS (
 SELECT side.half,
   pg_catalog.jsonb_agg(CASE WHEN c.runs>0 OR c.completed
     THEN pg_catalog.to_jsonb(c.runs)
     ELSE '""'::jsonb END ORDER BY i.n) AS cells
 FROM (VALUES('top'),('bottom')) side(half)
 CROSS JOIN pg_catalog.generate_series(1,12) i(n)
 LEFT JOIN legacy_cells c ON c.half=side.half AND c.slot=i.n
 GROUP BY side.half
), all_innings AS (
 SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
   'inning',i.n,'half',side.half,
   'state',CASE WHEN r.inning IS NULL THEN 'unplayed'
     WHEN r.completed THEN 'completed' ELSE 'in-progress' END,
   'runs',CASE WHEN r.inning IS NULL THEN NULL ELSE r.runs END
 ) ORDER BY i.n,side.ord) AS value
 FROM pg_catalog.generate_series(1,(SELECT MAX(inning)::int FROM score_rows)) i(n)
 CROSS JOIN (VALUES('top',1),('bottom',2)) side(half,ord)
 LEFT JOIN score_rows r ON r.inning=i.n AND r.half=side.half
), source_metric AS (
 SELECT b.source_event_id,b.event_kind,b.pitcher_id,b.tenant_id,b.game_id,
   b.fact_version_id,
   ((b.event_kind='pitch' AND b.payload#>>'{calculation,request,t1,pitchEventKind}'='pitch-event') OR (b.event_kind='non_pitch' AND b.payload#>>'{calculation,request,t1,pitchEventKind}'='non-pitch-event')) AS kind_bound,
   b.computed_metric_keys @> ARRAY['pitch_count']::text[] AS computed,
   b.evaluation_sha256=pg_catalog.encode(pg_catalog.sha256(
     pg_catalog.convert_to(b.metric_states::text,'UTF8')),'hex') AS bound,
   b.metric_states#>>'{metrics,pitch_count,state}' AS state,
   b.metric_states#>>'{metrics,pitch_count,value}' AS metric_value,
   b.metric_states#>'{metrics,pitch_count,credits}' AS saved_credits
 FROM bounded b
), pitch_source_health AS (
 SELECT m.source_event_id,m.event_kind,m.pitcher_id,m.kind_bound,
   m.computed,m.bound,
   m.state,m.metric_value,m.saved_credits,
   COUNT(f.source_event_id) AS credits,
   BOOL_AND(f.state='available' AND f.amount=1
     AND f.player_id=m.pitcher_id AND f.credit_ordinal=0) AS valid_fact
 FROM source_metric m LEFT JOIN sync_fence.stats_primitive_facts f
   ON (f.tenant_id,f.game_id,f.fact_version_id,f.source_event_id)
    =(m.tenant_id,m.game_id,m.fact_version_id,m.source_event_id)
   AND f.metric_id='pitch_count'
 GROUP BY m.source_event_id,m.event_kind,m.pitcher_id,m.kind_bound,
   m.computed,m.bound,
   m.state,m.metric_value,m.saved_credits
), pitcher_total AS (
 SELECT COALESCE(SUM(f.amount),0)::bigint AS value,
   BOOL_AND(COALESCE(h.kind_bound AND h.computed AND h.bound
     AND h.state='available'
     AND h.event_kind IN ('pitch','non_pitch')
     AND CASE WHEN h.metric_value='0' THEN
       h.saved_credits='[]'::jsonb AND h.credits=0
     WHEN h.metric_value='1' THEN
       h.saved_credits=pg_catalog.jsonb_build_array(
         pg_catalog.jsonb_build_object('player_id',h.pitcher_id::text,
           'quantity','1'))
       AND h.credits=1 AND h.valid_fact
     ELSE false END,false)) AS valid
 FROM pitch_source_health h CROSS JOIN target t
 LEFT JOIN sync_fence.stats_primitive_facts f
   ON f.source_event_id=h.source_event_id AND f.fact_version_id=p_fact_version_id
   AND f.tenant_id=tenant AND f.game_id=p_game_id
   AND f.metric_id='pitch_count' AND f.player_id=t.pitcher_id
)
SELECT p.value AS pitcher_pitch_count,
  a.cells || pg_catalog.jsonb_build_array(
    z.top_hits,z.top_errors,z.top_strikeouts,z.top_walks)
    AS top_score,
  b.cells || pg_catalog.jsonb_build_array(
    z.bottom_hits,z.bottom_errors,z.bottom_strikeouts,z.bottom_walks)
    AS bottom_score,
  f.value AS full_innings
FROM target t CROSS JOIN member_health h CROSS JOIN score_health sh
CROSS JOIN pitcher_total p CROSS JOIN score_totals z CROSS JOIN all_innings f
JOIN legacy_arrays a ON a.half='top'
JOIN legacy_arrays b ON b.half='bottom'
WHERE h.actual_count=h.source_count AND sh.valid AND p.valid
  AND p.value>=0 AND f.value IS NOT NULL;
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
   p_binding_nonce,binding_device,p_game_id);
END;
$export$;
ALTER FUNCTION stats_api.read_writer_play_export_aggregate(uuid,uuid,uuid,uuid,text,bigint,bytea) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.read_writer_play_export_aggregate(uuid,uuid,uuid,uuid,text,bigint,bytea) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION stats_api.read_writer_play_export_aggregate(uuid,uuid,uuid,uuid,text,bigint,bytea) TO pitchlog_app;
