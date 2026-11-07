-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:persist_writer_pitcher_entry(uuid, uuid, uuid, bytea)

CREATE FUNCTION stats_api.persist_writer_pitcher_entry(
 p_attempt_id uuid,p_phase_id uuid,p_source_event_id uuid,p_binding_nonce bytea)
RETURNS TABLE(proof_sha256 text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $d03_writer$
#variable_conflict use_column
DECLARE v_tenant uuid; v_xid text; v_binding sync_fence.writer_bindings%ROWTYPE;
 v_event public.operation_events%ROWTYPE; v_event_xmin xid;
 v_source sync_fence.stats_primitive_sources%ROWTYPE;
 v_receipt sync_fence.substitution_write_receipts%ROWTYPE;
 v_cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE; v_frame jsonb;
 v_payload jsonb; v_value jsonb;
 v_before jsonb; v_after jsonb; v_bl jsonb; v_al jsonb;
 v_origin text; v_slot bigint; v_artifact text; v_fingerprint text;
 v_changed text; v_half_completed boolean; v_detected boolean; v_lock boolean;
 v_outcome text; v_xmark text; v_entry jsonb; v_proof jsonb;
 v_digest text; v_context text;
BEGIN
 v_tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 v_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR v_tenant IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL
 OR p_source_event_id IS NULL OR p_binding_nonce IS NULL
 OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR pg_catalog.current_setting('transaction_read_only')<>'off'
 THEN RAISE EXCEPTION 'pitcher entry writer rejected' USING ERRCODE='42501'; END IF;
 SELECT b.* INTO STRICT v_binding FROM sync_fence.writer_bindings b
 WHERE b.tenant_id=v_tenant AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id
 AND b.state='open' AND b.transaction_id=v_xid
 AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(v_tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,v_binding.device_id,v_binding.game_id);
 SELECT e.* INTO STRICT v_event FROM public.operation_events e
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 JOIN public.event_slots s ON (s.tenant_id,s.game_id,s.generation,s.d1)=
 (e.tenant_id,e.game_id,e.generation,e.d1)
 WHERE e.tenant_id=v_tenant AND e.game_id=v_binding.game_id
 AND e.id=p_source_event_id AND e.generation=v_binding.internal_generation
 AND e.d5=v_binding.d5 AND e.ledger_kind='accepted'
 AND e.event_kind IN ('play_input','substitution') AND NOT e.is_tombstone
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND NOT e.migration_unverified AND l.kind='accepted' AND l.retired_at IS NULL
 AND l.import_batch_id IS NULL AND l.source_fingerprint=v_binding.event_fingerprint
 AND s.confirmed_version=1
 AND e.xmin::text::numeric=pg_catalog.mod(v_xid::numeric,4294967296::numeric)
 AND l.xmin=e.xmin AND s.xmin=e.xmin;
 -- ROWTYPEにsystem列は無い。同TXで物理表のxminを明示取得する。
 SELECT e.xmin INTO STRICT v_event_xmin FROM public.operation_events e
 WHERE e.tenant_id=v_tenant AND e.game_id=v_binding.game_id
 AND e.id=p_source_event_id
 AND e.xmin::text::numeric=pg_catalog.mod(v_xid::numeric,4294967296::numeric);
 v_slot:=1; v_fingerprint:=v_binding.event_fingerprint;
 IF v_event.event_kind='play_input' THEN
  SELECT s.* INTO STRICT v_source FROM sync_fence.stats_primitive_sources s
  JOIN sync_fence.stats_fact_versions v ON (v.tenant_id,v.game_id,v.id)=
   (s.tenant_id,s.game_id,s.fact_version_id)
  WHERE s.tenant_id=v_tenant AND s.game_id=v_event.game_id
  AND s.source_event_id=v_event.id
  AND s.attempt_id=p_attempt_id AND s.phase_id=p_phase_id
  AND s.recording_generation=v_event.generation AND s.d1=v_event.d1
  AND s.d2=v_event.d2 AND s.wire_d4=v_binding.wire_d4
  AND s.source_fingerprint=v_fingerprint AND s.slot_version=v_slot
  AND v.is_current AND v.invalidated_at IS NULL AND v.completion_state='current_open'
  AND v.model_sha256='sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6' AND v.revision>=1 AND v.source_count>=1
  AND v.source_set_sha256 ~ '^[a-f0-9]{64}$'
  AND s.xmin=v_event_xmin AND v.xmin=v_event_xmin;
  v_payload:=v_event.payload;
  v_before:=v_payload#>'{calculation,request,t1,before,stateFields}';
  v_after:=v_payload#>'{calculation,response,value,t1,after,stateFields}';
  IF v_payload->>'formatVersion' IN ('first-ball-play-v1','ordinary-pitch-play-v1',
      'play-prefix-play-v2') AND v_before->>'state.half' IS NOT NULL
    AND v_before->>'state.half'=v_after->>'state.half'
    AND v_before->>'state.inning'=v_after->>'state.inning' THEN
    PERFORM sync_fence_api.assert_writer_binding(v_tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,v_binding.device_id,v_binding.game_id);
 RETURN QUERY SELECT NULL::text; RETURN;
  END IF;
  IF v_payload->>'formatVersion' IS DISTINCT FROM 'play-prefix-play-v3'
  THEN RAISE EXCEPTION 'pitcher entry profile unavailable'
   USING ERRCODE='42501'; END IF;
  v_origin:='play'; v_value:=v_payload#>'{calculation,response,value}';
  IF v_payload#>>'{calculation,request,source,formatVersion}'=
    'nonplay-prefix-source-v1' THEN
   v_bl:=v_payload#>'{calculation,request,source,checkpoint,content,restored,lineup}';
  ELSE v_bl:=v_payload#>'{calculation,request,source,lineup}'; END IF;
  v_al:=v_value->'lineup'; v_artifact:=v_source.artifact_sha256;
  IF v_value->>'executionArtifactSha256' IS DISTINCT FROM v_artifact
   OR v_value#>>'{t2,facts,beforeHalf}' IS DISTINCT FROM v_before->>'state.half'
   OR v_value#>>'{t2,facts,afterHalf}' IS DISTINCT FROM v_after->>'state.half'
   OR v_value#>>'{t2,facts,beforeInning}' IS DISTINCT FROM v_before->>'state.inning'
   OR v_value#>>'{t2,facts,afterInning}' IS DISTINCT FROM v_after->>'state.inning'
  THEN RAISE EXCEPTION 'pitcher entry stored kernel mismatch'
   USING ERRCODE='42501'; END IF;
  v_half_completed:=(v_value#>>'{t2,facts,halfCompleted}')::boolean;
  v_detected:=(v_value#>>'{t2,decision,endConditionDetected}')::boolean;
  v_lock:=(v_value#>>'{t2,decision,lockFurtherPlayInput}')::boolean;
  v_outcome:=v_value#>>'{t2,decision,outcome}';
  v_xmark:=v_value#>>'{t2,decision,xMark}';
 ELSE
  v_origin:='substitution';
  SELECT sr.* INTO STRICT v_receipt FROM sync_fence.substitution_write_receipts sr
  JOIN sync_fence.nonplay_write_admissions n ON
   (n.tenant_id,n.attempt_id,n.phase_id)=(sr.tenant_id,sr.attempt_id,sr.phase_id)
  WHERE sr.tenant_id=v_tenant AND sr.game_id=v_event.game_id
  AND sr.attempt_id=p_attempt_id AND sr.phase_id=p_phase_id
  AND sr.source_event_id=v_event.id AND sr.source_d1=v_event.d1
  AND sr.xmin=v_event_xmin AND n.xmin=v_event_xmin
  AND n.state='right_verified' AND n.transaction_id=v_xid
  AND n.game_id=v_event.game_id AND n.internal_generation=v_event.generation
  AND n.device_id=v_binding.device_id
  AND n.nonce_digest=pg_catalog.sha256(p_binding_nonce)
  AND n.d5=v_event.d5 AND n.event_fingerprint=v_fingerprint;
  SELECT c.* INTO STRICT v_cp FROM sync_fence.ordinary_pitch_checkpoints c
  WHERE c.tenant_id=v_tenant AND c.game_id=v_event.game_id
  AND c.internal_generation=v_event.generation AND c.id=v_receipt.checkpoint_id
  AND c.revision=v_receipt.after_revision AND c.content_digest=v_receipt.after_digest
  AND c.state='current' AND c.xmin=v_event_xmin;
  SELECT frames.value INTO STRICT v_frame FROM pg_catalog.jsonb_array_elements(
   v_cp.content#>'{content,substitutionFrames}') AS frames(value)
  WHERE frames.value#>>'{source,eventId}'=v_event.id::text
  AND frames.value#>>'{source,gameId}'=v_event.game_id::text
  AND frames.value#>>'{source,generation}'=v_binding.wire_d4
  AND frames.value#>>'{source,d1}'=v_event.d1::text
  AND frames.value#>>'{source,d5}'=v_event.d5::text
  AND frames.value#>>'{source,fingerprint}'=v_fingerprint
  AND frames.value#>>'{source,eventKind}'='substitution';
  v_before:=v_frame#>'{beforeContext,current,stateFields}';
  v_after:=v_frame#>'{afterContext,current,stateFields}';
  v_bl:=v_frame#>'{beforeContext,lineup}'; v_al:=v_frame#>'{afterContext,lineup}';
  v_changed:=v_event.payload#>>'{operation,side}';
  v_artifact:=v_cp.content#>>'{content,executionArtifactSha256}';
 END IF;
 WITH appearance_transition AS (SELECT v_tenant AS tenant_id,v_event.game_id AS game_id,
 v_event.id AS source_id,v_origin AS origin_kind,
 v_event.generation AS internal_generation,v_event.d1 AS d1,
 (v_before->>'state.inning')::bigint AS before_inning,
 v_before->>'state.half' AS before_half,
 (v_after->>'state.inning')::bigint AS after_inning,
 v_after->>'state.half' AS after_half,
 (v_bl#>>'{home,pitcherId}')::uuid AS before_home_pitcher_id,
 (v_bl#>>'{away,pitcherId}')::uuid AS before_away_pitcher_id,
 (v_al#>>'{home,pitcherId}')::uuid AS after_home_pitcher_id,
 (v_al#>>'{away,pitcherId}')::uuid AS after_away_pitcher_id,
 v_changed AS changed_side,v_half_completed AS half_completed,
 v_detected AS end_condition_detected,v_lock AS lock_further_play,
 v_outcome AS outcome,v_xmark AS x_mark,NULL::boolean AS released_end_condition,
 NULL::boolean AS half_started_before,v_artifact AS artifact_sha256,
 v_fingerprint AS source_fingerprint)
 SELECT pg_catalog.to_jsonb(projected) INTO STRICT v_entry FROM (
-- 生成元: backend/domain/stats-appearance.model.json。真正TX原本のappearance_transitionだけを供給する。
WITH observed AS (
 SELECT e.*,
  CASE e.after_half WHEN 'top' THEN 'home' WHEN 'bottom' THEN 'away' END AS defender,
  CASE e.after_half WHEN 'top' THEN e.after_home_pitcher_id
       WHEN 'bottom' THEN e.after_away_pitcher_id END AS pitcher,
  CASE e.after_half WHEN 'top' THEN e.before_home_pitcher_id
       WHEN 'bottom' THEN e.before_away_pitcher_id END AS previous_pitcher,
  CASE
   WHEN e.origin_kind='start' THEN 1
   WHEN e.origin_kind='play' AND e.half_completed IS TRUE
        AND e.end_condition_detected IS FALSE AND e.lock_further_play IS FALSE
        AND e.outcome IN ('no-end','extra-continue','tiebreak-continue') THEN 1
   WHEN e.origin_kind='substitution' AND e.changed_side=
        CASE e.after_half WHEN 'top' THEN 'home' WHEN 'bottom' THEN 'away' END
        AND (CASE e.after_half WHEN 'top' THEN e.after_home_pitcher_id
              WHEN 'bottom' THEN e.after_away_pitcher_id END) IS DISTINCT FROM
            (CASE e.after_half WHEN 'top' THEN e.before_home_pitcher_id
              WHEN 'bottom' THEN e.before_away_pitcher_id END) THEN 1
   WHEN e.origin_kind='reopen' AND e.half_completed IS TRUE
        AND e.released_end_condition IS TRUE AND e.half_started_before IS FALSE
        THEN 1
   ELSE 0 END AS emits_entry
 FROM appearance_transition e
), checked AS (
 SELECT o.*, CASE WHEN o.origin_kind IS NULL OR o.origin_kind NOT IN ('start','play','substitution','reopen')
  OR o.tenant_id IS NULL OR o.game_id IS NULL OR o.source_id IS NULL
  OR o.internal_generation IS NULL OR o.internal_generation<=0
  OR o.artifact_sha256 IS NULL OR o.source_fingerprint IS NULL
  OR o.after_half IS NULL OR o.after_half NOT IN ('top','bottom')
  OR o.after_inning IS NULL OR o.after_inning<=0
  OR (o.origin_kind='start' AND (o.d1 IS NOT NULL OR o.after_inning<>1
       OR o.after_half<>'top'))
  OR (o.origin_kind<>'start' AND (o.d1 IS NULL OR o.d1<=0
       OR o.before_half IS NULL OR o.before_half NOT IN ('top','bottom')
       OR o.before_inning IS NULL OR o.before_inning<=0))
  OR (o.origin_kind='play' AND (o.half_completed IS NULL
       OR o.end_condition_detected IS NULL OR o.lock_further_play IS NULL
       OR o.outcome IS NULL OR o.x_mark IS NULL
       OR o.outcome NOT IN ('no-end','normal-end','extra-continue','limit-draw','tiebreak-continue','cold-end','walk-off') OR o.x_mark NOT IN ('recorded-score','x-mark')
       OR o.end_condition_detected IS DISTINCT FROM o.lock_further_play
       OR (o.half_completed IS TRUE AND o.before_half=o.after_half)
       OR (o.half_completed IS FALSE AND (o.before_half<>o.after_half
           OR o.before_inning<>o.after_inning))
       OR (o.end_condition_detected IS FALSE AND o.lock_further_play IS FALSE
           AND (o.outcome NOT IN ('no-end','extra-continue','tiebreak-continue') OR o.x_mark<>'recorded-score'))
       OR (o.end_condition_detected IS TRUE AND o.outcome IN ('no-end','extra-continue','tiebreak-continue'))))
  OR (o.origin_kind='substitution' AND (o.changed_side IS NULL
       OR o.changed_side NOT IN ('home','away') OR o.before_half<>o.after_half
       OR o.before_inning<>o.after_inning))
  OR (o.origin_kind='reopen' AND (o.half_completed IS NULL
       OR o.released_end_condition IS NULL OR o.half_started_before IS NULL))
  OR (o.emits_entry=1 AND o.pitcher IS NULL)
 THEN 'source_unavailable' ELSE 'evaluated' END AS state
 FROM observed o
)
SELECT state,tenant_id,game_id,origin_kind,source_id,internal_generation,d1,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN pitcher END AS player_id,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN defender END AS defending_side,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN after_inning END AS inning,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN after_half END AS half,
 CASE WHEN state='evaluated' AND emits_entry=1 THEN
  CASE WHEN origin_kind='substitution' THEN 'pitcher-defensive-entry' ELSE 'defensive-half-entry' END
 END AS proof_kind,artifact_sha256,source_fingerprint
FROM checked

 ) projected;
 IF v_entry->>'state' IS DISTINCT FROM 'evaluated'
 THEN RAISE EXCEPTION 'pitcher entry writer unavailable' USING ERRCODE='42501'; END IF;
 IF v_entry->>'player_id' IS NULL THEN
 PERFORM sync_fence_api.assert_writer_binding(v_tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,v_binding.device_id,v_binding.game_id);
 RETURN QUERY SELECT NULL::text; RETURN; END IF;
 v_context:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 CASE WHEN v_origin='play' THEN v_payload::text ELSE v_frame::text END,'UTF8')),'hex');
 v_proof:=pg_catalog.jsonb_build_object('tenant_id',v_tenant,'game_id',v_event.game_id,
 'origin_kind',v_origin,'start_attempt_id',NULL,'source_event_id',v_event.id,
 'generation',v_event.generation,'d1',v_event.d1,'slot_version',v_slot,
 'player_id',(v_entry->>'player_id')::uuid,'defending_side',v_entry->>'defending_side',
 'inning',(v_entry->>'inning')::bigint,'half',v_entry->>'half',
 'proof_kind',v_entry->>'proof_kind','source_fingerprint',v_fingerprint,
 'artifact_sha256',v_artifact,'context_sha256',v_context);
 v_digest:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_proof::text,'UTF8')),'hex');
 INSERT INTO sync_fence.pitcher_entry_sources(
 tenant_id,game_id,proof_sha256,origin_kind,start_attempt_id,source_event_id,
 generation,d1,slot_version,player_id,defending_side,inning,half,proof_kind,
 source_fingerprint,artifact_sha256,context_sha256)
 SELECT v_tenant,v_event.game_id,v_digest,v_origin,NULL,v_event.id,
 v_event.generation,v_event.d1,v_slot,(v_entry->>'player_id')::uuid,
 v_entry->>'defending_side',(v_entry->>'inning')::bigint,v_entry->>'half',
 v_entry->>'proof_kind',v_fingerprint,v_artifact,v_context
 ON CONFLICT (tenant_id,game_id,proof_sha256) DO NOTHING;
 IF NOT EXISTS(SELECT 1 FROM sync_fence.pitcher_entry_sources e
 WHERE e.tenant_id=v_tenant AND e.game_id=v_event.game_id AND e.proof_sha256=v_digest
 AND pg_catalog.to_jsonb(e)-'proof_sha256'=v_proof)
 THEN RAISE EXCEPTION 'pitcher entry identity mismatch' USING ERRCODE='42501'; END IF;
 PERFORM sync_fence_api.assert_writer_binding(v_tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,v_binding.device_id,v_binding.game_id);
 RETURN QUERY SELECT v_digest;
END;
$d03_writer$;
