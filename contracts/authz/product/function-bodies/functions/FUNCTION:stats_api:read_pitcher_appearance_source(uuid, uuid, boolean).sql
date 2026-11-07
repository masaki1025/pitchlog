-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:read_pitcher_appearance_source(uuid, uuid, boolean)

CREATE FUNCTION stats_api.read_pitcher_appearance_source(
 p_tenant_id uuid,p_game_id uuid,p_official boolean)
RETURNS TABLE(record_json text) LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $d03_source$
DECLARE query text:=$appearance_query$WITH canonical_scope AS (
 SELECT g.tenant_id,g.id AS game_id FROM public.games g
 WHERE g.tenant_id=$1 AND g.hidden_at IS NULL AND g.trashed_at IS NULL
   AND g.status NOT IN ('hidden','trashed')
   AND g.id=$2
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
),
appearance_version AS MATERIALIZED (
 SELECT v.* FROM sync_fence.stats_fact_versions v
 WHERE v.tenant_id=$1 AND v.game_id=$2
 AND v.is_current AND v.invalidated_at IS NULL
 AND v.model_sha256='sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6'
), appearance_cp AS MATERIALIZED (
 SELECT j.context_json::jsonb AS j FROM
 stats_api.read_pitcher_appearance_context($1,$2) j
), appearance_lc AS MATERIALIZED (
 SELECT l.record_json::jsonb AS j FROM
 sync_right_api.read_lifecycle_display($1,$2) l
), appearance_native AS MATERIALIZED (
 SELECT s.* FROM appearance_version v CROSS JOIN LATERAL (SELECT s.* FROM sync_fence.stats_primitive_sources s
 JOIN canonical_s c ON c.tenant_id=s.tenant_id AND c.game_id=s.game_id
   AND c.source_event_id=s.source_event_id AND c.recording_generation=s.recording_generation
   AND c.d1=s.d1 AND c.d2=s.d2 AND c.slot_version=s.slot_version
   AND c.play_row_id=s.play_row_id AND c.play_row_version=s.play_row_version
   AND c.source_fingerprint=s.source_fingerprint AND c.artifact_sha256=s.artifact_sha256
   AND c.source_state='included'
WHERE s.tenant_id=$1 AND s.game_id=$2 AND s.fact_version_id=v.id) s
), appearance_events AS MATERIALIZED (
 SELECT e.*,l.source_fingerprint AS fingerprint
 FROM public.operation_events e JOIN canonical_scope g
 ON (g.tenant_id,g.game_id)=(e.tenant_id,e.game_id)
 JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
 WHERE e.ledger_kind='accepted' AND e.replaced_at IS NULL AND e.retired_at IS NULL
 AND l.kind='accepted' AND l.retired_at IS NULL
), appearance_frames AS MATERIALIZED (
 SELECT e.tenant_id,e.game_id,e.id,e.generation,e.d1,e.fingerprint,
 'play'::text AS origin_kind,e.payload AS context,
 e.payload#>'{calculation,request,t1,before,stateFields}' AS before_fields,
 e.payload#>'{calculation,response,value,t1,after,stateFields}' AS after_fields,
 CASE WHEN e.payload#>>'{calculation,request,source,formatVersion}'=
 'nonplay-prefix-source-v1' THEN
 e.payload#>'{calculation,request,source,checkpoint,content,restored,lineup}'
 ELSE e.payload#>'{calculation,request,source,lineup}' END AS before_lineup,
 e.payload#>'{calculation,response,value,lineup}' AS after_lineup,
 e.payload#>'{calculation,response,value,t2}' AS t2,
 NULL::text AS changed_side,s.artifact_sha256,s.slot_version
 FROM appearance_native s JOIN appearance_events e ON
 (e.tenant_id,e.game_id,e.id,e.generation,e.d1)=
 (s.tenant_id,s.game_id,s.source_event_id,s.recording_generation,s.d1)
 WHERE e.event_kind='play_input' AND s.slot_version=1
 AND e.payload->>'formatVersion'='play-prefix-play-v3'
 UNION ALL
 SELECT e.tenant_id,e.game_id,e.id,e.generation,e.d1,e.fingerprint,
 'substitution',frame.value,
 frame.value#>'{beforeContext,current,stateFields}',
 frame.value#>'{afterContext,current,stateFields}',
 frame.value#>'{beforeContext,lineup}',frame.value#>'{afterContext,lineup}',
 NULL::jsonb,e.payload#>>'{operation,side}',
 cp.j#>>'{checkpoint,content,executionArtifactSha256}',1::bigint
 FROM appearance_cp cp CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
 COALESCE(cp.j#>'{checkpoint,content,substitutionFrames}','[]'::jsonb)) frame(value)
 JOIN appearance_events e ON frame.value#>>'{source,eventId}'=e.id::text
 AND frame.value#>>'{source,gameId}'=e.game_id::text
 AND frame.value#>>'{source,d1}'=e.d1::text
 AND frame.value#>>'{source,d5}'=e.d5::text
 AND frame.value#>>'{source,fingerprint}'=e.fingerprint
 JOIN sync_fence.substitution_write_receipts sr ON
 (sr.tenant_id,sr.game_id,sr.source_event_id,sr.source_d1)=
 (e.tenant_id,e.game_id,e.id,e.d1)
 JOIN sync_fence.nonplay_write_admissions n ON
 (n.tenant_id,n.attempt_id,n.phase_id)=(sr.tenant_id,sr.attempt_id,sr.phase_id)
 WHERE e.event_kind='substitution' AND n.state='right_verified'
 AND frame.value#>>'{source,generation}'=n.wire_d4
 AND frame.value#>>'{source,eventKind}'='substitution'
), appearance_transition AS MATERIALIZED (
 SELECT f.tenant_id,f.game_id,f.id AS source_id,f.origin_kind,
 f.generation AS internal_generation,f.d1,
 (f.before_fields->>'state.inning')::bigint AS before_inning,
 f.before_fields->>'state.half' AS before_half,
 (f.after_fields->>'state.inning')::bigint AS after_inning,
 f.after_fields->>'state.half' AS after_half,
 (f.before_lineup#>>'{home,pitcherId}')::uuid AS before_home_pitcher_id,
 (f.before_lineup#>>'{away,pitcherId}')::uuid AS before_away_pitcher_id,
 (f.after_lineup#>>'{home,pitcherId}')::uuid AS after_home_pitcher_id,
 (f.after_lineup#>>'{away,pitcherId}')::uuid AS after_away_pitcher_id,
 f.changed_side,(f.t2#>>'{facts,halfCompleted}')::boolean AS half_completed,
 (f.t2#>>'{decision,endConditionDetected}')::boolean AS end_condition_detected,
 (f.t2#>>'{decision,lockFurtherPlayInput}')::boolean AS lock_further_play,
 f.t2#>>'{decision,outcome}' AS outcome,f.t2#>>'{decision,xMark}' AS x_mark,
 NULL::boolean AS released_end_condition,NULL::boolean AS half_started_before,
 f.artifact_sha256,f.fingerprint AS source_fingerprint
 FROM appearance_frames f
), appearance_projected AS MATERIALIZED (-- 生成元: backend/domain/stats-appearance.model.json。真正TX原本のappearance_transitionだけを供給する。
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
),
appearance_proofs AS MATERIALIZED (
 SELECT e.* FROM sync_fence.pitcher_entry_sources e
 WHERE e.tenant_id=$1 AND e.game_id=$2
), appearance_valid_proofs AS MATERIALIZED (
 SELECT e.* FROM appearance_proofs e WHERE e.proof_sha256=
 pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 (pg_catalog.to_jsonb(e)-'proof_sha256')::text,'UTF8')),'hex')
), appearance_effective AS MATERIALIZED (
 SELECT e.* FROM appearance_valid_proofs e,appearance_cp cp
 WHERE e.origin_kind='start' AND e.generation=(cp.j->>'checkpoint_generation')::bigint
 AND e.proof_kind='defensive-half-entry' AND e.defending_side='home'
 AND e.inning=1 AND e.half='top' AND e.start_attempt_id IS NOT NULL
 AND e.source_event_id IS NULL AND e.d1 IS NULL AND e.slot_version IS NULL
 UNION ALL
 SELECT e.* FROM appearance_valid_proofs e JOIN appearance_projected p ON
 (e.tenant_id,e.game_id,e.origin_kind,e.source_event_id,e.generation,e.d1,e.player_id,
 e.defending_side,e.inning,e.half,e.proof_kind,e.artifact_sha256,e.source_fingerprint)=
 (p.tenant_id,p.game_id,p.origin_kind,p.source_id,p.internal_generation,p.d1,p.player_id,
 p.defending_side,p.inning,p.half,p.proof_kind,p.artifact_sha256,p.source_fingerprint)
 JOIN appearance_frames f ON f.id=p.source_id AND f.tenant_id=p.tenant_id
 AND f.game_id=p.game_id AND e.slot_version=f.slot_version
 WHERE p.state='evaluated' AND p.player_id IS NOT NULL
 AND e.context_sha256=pg_catalog.encode(pg_catalog.sha256(
 pg_catalog.convert_to(f.context::text,'UTF8')),'hex')
), appearance_completeness AS (
 SELECT (SELECT count(*) FROM appearance_version)=1
 AND (SELECT count(*) FROM appearance_cp)=1 AND (SELECT count(*) FROM appearance_lc)=1
 AND EXISTS(SELECT 1 FROM appearance_version v JOIN canonical_health h ON
 (h.tenant_id,h.game_id)=(v.tenant_id,v.game_id)
 WHERE h.unavailable_count=0 AND h.game_count=1
 AND h.canonical_source_count=v.source_count
 AND h.canonical_source_set_sha256=v.source_set_sha256
 AND v.source_count=(SELECT count(*) FROM appearance_native))
 AND NOT EXISTS(SELECT 1 FROM appearance_events e WHERE e.event_kind NOT IN
 ('play_input','substitution','game_end_declaration','game_reopen'))
 AND NOT EXISTS(SELECT 1 FROM appearance_events e WHERE e.event_kind='game_reopen'
 AND NOT EXISTS(SELECT 1 FROM sync_fence.lifecycle_write_admissions a
 WHERE (a.tenant_id,a.game_id,a.source_event_id,a.internal_generation,
 a.source_d1,a.source_d2,a.d5,a.event_fingerprint)=
 (e.tenant_id,e.game_id,e.id,e.generation,e.d1,e.d2,e.d5,e.fingerprint)
 AND a.action='reopen' AND a.state='consumed' AND a.consumed_at IS NOT NULL
 AND a.receipt_id::text=e.payload#>>'{event,receiptId}'
 AND a.preparation#>'{before_source,checkpoint,content,restored,lastPlayEvaluation,
 decision,lockFurtherPlayInput}'='false'::jsonb
 AND pg_catalog.jsonb_typeof(a.preparation#>'{before_source,checkpoint,
 content,restored,current,stateFields,state.gameEnded}')='boolean'
 AND a.preparation#>'{after_source,checkpoint,content,restored,current,
 stateFields,state.gameEnded}'='false'::jsonb
 AND (a.preparation#>'{before_source,checkpoint,content,restored}')
 #- '{current,stateFields,state.gameEnded}' =
 (a.preparation#>'{after_source,checkpoint,content,restored}')
 #- '{current,stateFields,state.gameEnded}'))
 AND (SELECT count(DISTINCT generation) FROM appearance_events)=1
 AND (SELECT count(*) FROM appearance_frames WHERE origin_kind='play')=
 (SELECT count(*) FROM appearance_native)
 AND (SELECT count(*) FROM appearance_frames WHERE origin_kind='substitution')=
 (SELECT count(*) FROM appearance_events WHERE event_kind='substitution')
 AND NOT EXISTS(SELECT 1 FROM appearance_frames f WHERE f.origin_kind='play'
 AND (f.context#>>'{calculation,response,value,executionArtifactSha256}'
 IS DISTINCT FROM f.artifact_sha256
 OR f.t2#>>'{facts,beforeHalf}' IS DISTINCT FROM f.before_fields->>'state.half'
 OR f.t2#>>'{facts,afterHalf}' IS DISTINCT FROM f.after_fields->>'state.half'
 OR f.t2#>>'{facts,beforeInning}' IS DISTINCT FROM f.before_fields->>'state.inning'
 OR f.t2#>>'{facts,afterInning}' IS DISTINCT FROM f.after_fields->>'state.inning'))
 AND NOT EXISTS(SELECT 1 FROM appearance_frames
 GROUP BY tenant_id,game_id,id HAVING count(*)<>1)
 AND NOT EXISTS(SELECT 1 FROM appearance_effective
 GROUP BY tenant_id,game_id,proof_sha256 HAVING count(*)<>1)
 AND NOT EXISTS(SELECT 1 FROM appearance_projected WHERE state<>'evaluated'
 OR state IS NULL)
 AND (SELECT count(*) FROM appearance_effective WHERE origin_kind='start')=1
 AND (SELECT count(*) FROM appearance_effective WHERE origin_kind<>'start')=
 (SELECT count(*) FROM appearance_projected WHERE player_id IS NOT NULL)
 AND (SELECT count(*) FROM appearance_effective)=
 (SELECT count(*) FROM appearance_proofs)
 AND EXISTS(SELECT 1 FROM appearance_version v,appearance_lc l WHERE
 (($3 AND v.completion_state='confirmed_ended'
 AND l.j->>'status'='finished' AND l.j->>'activeStatsVersionId'=v.id::text
 AND l.j#>>'{active,receiptId}'=v.completion_receipt_id::text
 AND v.public_pointer_receipt_id=v.completion_receipt_id)
 OR (NOT $3 AND v.completion_state='current_open'
 AND l.j->>'status'='in_progress' AND l.j->'active'='null'::jsonb)))
 AS complete
), appearance_scope AS MATERIALIZED (
 SELECT v.tenant_id,v.game_id,v.id AS fact_version_id,v.revision,v.source_set_sha256,
 (cp.j->>'checkpoint_id')::uuid AS checkpoint_id,
 (cp.j->>'checkpoint_generation')::bigint AS checkpoint_generation,
 (cp.j->>'checkpoint_revision')::bigint AS checkpoint_revision,
 cp.j->>'checkpoint_digest' AS checkpoint_digest,(cp.j->>'d3')::bigint AS d3,
 v.completion_receipt_id AS lifecycle_receipt_id,
 pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(COALESCE(
 (SELECT pg_catalog.string_agg(e.proof_sha256,E'\n' ORDER BY e.proof_sha256)
 FROM appearance_effective e),'pitcher-entry-set-v1:empty'),'UTF8')),'hex')
 AS entry_set_sha256,c.complete AS supply_complete,
 (SELECT count(*) FROM appearance_effective) AS member_count
 FROM appearance_version v,appearance_cp cp,appearance_completeness c
), appearance_members AS MATERIALIZED (
 SELECT s.*,e.player_id,e.proof_kind,e.proof_sha256 AS proof_source_id
 FROM appearance_scope s JOIN appearance_effective e ON
 (e.tenant_id,e.game_id)=(s.tenant_id,s.game_id)
)
SELECT pg_catalog.jsonb_build_object(
 'scope',(SELECT pg_catalog.to_jsonb(s) FROM appearance_scope s),
 'members',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(m)
 ORDER BY m.proof_source_id) FROM appearance_members m),'[]'::jsonb))::text
$appearance_query$;
BEGIN
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL OR p_official IS NULL
 OR p_tenant_id IS DISTINCT FROM NULLIF(
 pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR pg_catalog.current_setting('transaction_isolation')
 IS DISTINCT FROM 'repeatable read'
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'on'
 THEN RAISE EXCEPTION 'pitcher appearance source readonly boundary rejected'
 USING ERRCODE='42501'; END IF;
 BEGIN
  RETURN QUERY EXECUTE query USING p_tenant_id,p_game_id,p_official;
 EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS OR insufficient_privilege THEN
  -- 読取資格/原本不足だけを未供給にする。SQL不正/欠表/未知故障は503へ残す。
  RETURN QUERY SELECT '{"scope":null,"members":[]}'::text;
 END;
END;
$d03_source$;
ALTER FUNCTION stats_api.read_pitcher_appearance_source(uuid, uuid, boolean) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.read_pitcher_appearance_source(uuid, uuid, boolean) FROM PUBLIC,pitchlog_app,pitchlog_initial_actor,pitchlog_sync_binding_actor,pitchlog_initial_fn_owner;
