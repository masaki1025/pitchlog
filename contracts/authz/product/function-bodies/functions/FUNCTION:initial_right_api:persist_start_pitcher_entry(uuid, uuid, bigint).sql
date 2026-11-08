-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:persist_start_pitcher_entry(uuid, uuid, bigint)

CREATE FUNCTION initial_right_api.persist_start_pitcher_entry(
 p_tenant_id uuid,p_attempt_id uuid,p_generation bigint)
RETURNS TABLE(proof_sha256 text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $d03_start$
#variable_conflict use_column
DECLARE v_tenant uuid; v_game uuid; v_device uuid; v_home uuid; v_away uuid;
 v_fingerprint text; v_home_pitcher uuid; v_away_pitcher uuid;
 v_entry jsonb; v_proof jsonb; v_digest text; v_context text;
BEGIN
 v_tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 IF session_user IS DISTINCT FROM 'pitchlog_initial_actor'
 OR current_user IS DISTINCT FROM 'pitchlog_initial_fn_owner'
 OR v_tenant IS NULL OR p_tenant_id IS DISTINCT FROM v_tenant
 OR p_attempt_id IS NULL OR p_generation IS NULL
 OR p_generation<1 OR pg_catalog.current_setting('transaction_read_only')<>'off'
 THEN RAISE EXCEPTION 'pitcher entry start boundary rejected'
 USING ERRCODE='42501'; END IF;
 SELECT a.game_id,a.device_id,g.home_team_record_id,g.away_team_record_id,
 pg_catalog.encode(r.request_digest,'hex')
 INTO STRICT v_game,v_device,v_home,v_away,v_fingerprint
 FROM public.game_start_attempts a
 JOIN public.game_start_requests r
 ON (r.tenant_id,r.game_id,r.start_request_id,r.device_id)=
 (a.tenant_id,a.game_id,a.start_request_id,a.device_id)
 JOIN public.games g ON g.tenant_id=a.tenant_id AND g.id=a.game_id
 JOIN public.recording_generations rg
 ON rg.tenant_id=a.tenant_id AND rg.game_id=a.game_id
 WHERE a.tenant_id=v_tenant AND a.attempt_id=p_attempt_id AND a.outcome='committed'
 AND rg.generation=p_generation AND rg.kind='normal' AND rg.revoked_at IS NULL
 AND rg.holder_device=a.device_id::text
 AND g.status='in_progress' AND g.started_at IS NOT NULL;
 SELECT (entries.value->>'player_id')::uuid INTO STRICT v_home_pitcher
 FROM public.game_lineups l CROSS JOIN LATERAL
 pg_catalog.jsonb_array_elements(l.entries_with_uniform_number_snapshot)
 AS entries(value)
 WHERE l.tenant_id=v_tenant AND l.game_id=v_game AND l.team_record_id=v_home
 AND entries.value->'fielding_position'='{"kind":"fielding","position":1}'::jsonb;
 SELECT (entries.value->>'player_id')::uuid INTO STRICT v_away_pitcher
 FROM public.game_lineups l CROSS JOIN LATERAL
 pg_catalog.jsonb_array_elements(l.entries_with_uniform_number_snapshot)
 AS entries(value)
 WHERE l.tenant_id=v_tenant AND l.game_id=v_game AND l.team_record_id=v_away
 AND entries.value->'fielding_position'='{"kind":"fielding","position":1}'::jsonb;
 WITH appearance_transition AS (SELECT v_tenant AS tenant_id,v_game AS game_id,
 p_attempt_id AS source_id,'start'::text AS origin_kind,
 p_generation AS internal_generation,
 NULL::bigint AS d1,NULL::bigint AS before_inning,NULL::text AS before_half,
 1::bigint AS after_inning,'top'::text AS after_half,
 v_home_pitcher AS after_home_pitcher_id,v_away_pitcher AS after_away_pitcher_id,
 NULL::uuid AS before_home_pitcher_id,NULL::uuid AS before_away_pitcher_id,
 NULL::text AS changed_side,NULL::boolean AS half_completed,
 NULL::boolean AS end_condition_detected,NULL::boolean AS lock_further_play,
 NULL::text AS outcome,NULL::text AS x_mark,NULL::boolean AS released_end_condition,
 NULL::boolean AS half_started_before,'859986408d75994d6f1530ce99c0331da1644da9d5ae6339bb479e3926ee7f2e'::text AS artifact_sha256,
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
 IF v_entry->>'state' IS DISTINCT FROM 'evaluated' OR v_entry->>'player_id' IS NULL
 THEN RAISE EXCEPTION 'pitcher entry start unavailable' USING ERRCODE='42501'; END IF;
 v_context:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
 pg_catalog.jsonb_build_object('homePitcher',v_home_pitcher,
 'awayPitcher',v_away_pitcher,'requestDigest',v_fingerprint)::text,'UTF8')),'hex');
 v_proof:=pg_catalog.jsonb_build_object('tenant_id',v_tenant,'game_id',v_game,
 'origin_kind','start','start_attempt_id',p_attempt_id,'source_event_id',NULL,
 'generation',p_generation,'d1',NULL,'slot_version',NULL,
 'player_id',(v_entry->>'player_id')::uuid,'defending_side',v_entry->>'defending_side',
 'inning',(v_entry->>'inning')::bigint,'half',v_entry->>'half',
 'proof_kind',v_entry->>'proof_kind','source_fingerprint',v_fingerprint,
 'artifact_sha256','859986408d75994d6f1530ce99c0331da1644da9d5ae6339bb479e3926ee7f2e','context_sha256',v_context);
 v_digest:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_proof::text,'UTF8')),'hex');
 INSERT INTO sync_fence.pitcher_entry_sources(
 tenant_id,game_id,proof_sha256,origin_kind,start_attempt_id,source_event_id,
 generation,d1,slot_version,player_id,defending_side,inning,half,proof_kind,
 source_fingerprint,artifact_sha256,context_sha256)
 SELECT v_tenant,v_game,v_digest,'start',p_attempt_id,NULL,p_generation,NULL,NULL,
 (v_entry->>'player_id')::uuid,v_entry->>'defending_side',(v_entry->>'inning')::bigint,
 v_entry->>'half',v_entry->>'proof_kind',v_fingerprint,'859986408d75994d6f1530ce99c0331da1644da9d5ae6339bb479e3926ee7f2e',v_context
 ON CONFLICT (tenant_id,game_id,proof_sha256) DO NOTHING;
 IF NOT EXISTS(SELECT 1 FROM sync_fence.pitcher_entry_sources e
 WHERE e.tenant_id=v_tenant AND e.game_id=v_game AND e.proof_sha256=v_digest
 AND pg_catalog.to_jsonb(e)-'proof_sha256'=v_proof)
 THEN RAISE EXCEPTION 'pitcher entry start identity mismatch'
 USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT v_digest;
END;
$d03_start$;
ALTER FUNCTION initial_right_api.persist_start_pitcher_entry(uuid, uuid, bigint) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.persist_start_pitcher_entry(uuid, uuid, bigint) FROM PUBLIC,pitchlog_app,pitchlog_initial_actor,pitchlog_sync_binding_actor,pitchlog_sync_right_fn_owner;
