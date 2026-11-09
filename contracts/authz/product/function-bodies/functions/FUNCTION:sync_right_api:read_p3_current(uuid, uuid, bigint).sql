-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:read_p3_current(uuid, uuid, bigint)

CREATE FUNCTION sync_right_api.read_p3_current(
p_tenant_id uuid,p_game_id uuid,p_generation bigint)
RETURNS TABLE(record_json text) LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_current$
#variable_conflict use_column
DECLARE h sync_fence.p3_projection_heads%ROWTYPE;
 c sync_fence.p3_projection_capsules%ROWTYPE;
 cp sync_fence.ordinary_pitch_checkpoints%ROWTYPE;
 v sync_fence.stats_fact_versions%ROWTYPE;
 change_event public.operation_events%ROWTYPE;
 change_ledger public.idempotency_ledger%ROWTYPE;
 members jsonb; member_count bigint; suffix_members jsonb:='[]'::jsonb;
 suffix_count bigint:=0; source_upper bigint; anchor_mode boolean;
 first_control_preparation jsonb;
 source_rows jsonb; source_count bigint; health record;
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL OR p_generation IS NULL
 OR p_generation<=0 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 THEN RAISE EXCEPTION 'P3 current read rejected' USING ERRCODE='42501'; END IF;
 SELECT x.* INTO h FROM sync_fence.p3_projection_heads x
 WHERE (x.tenant_id,x.game_id,x.internal_generation)=
 (p_tenant_id,p_game_id,p_generation);
 IF NOT FOUND THEN
 RETURN QUERY SELECT pg_catalog.jsonb_build_object('kind','none')::text;
 RETURN;
 END IF;
 SELECT x.* INTO STRICT c FROM sync_fence.p3_projection_capsules x
 WHERE (x.tenant_id,x.game_id,x.internal_generation,x.id)=
 (p_tenant_id,p_game_id,p_generation,h.capsule_id);
 SELECT x.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints x
 WHERE (x.tenant_id,x.game_id,x.internal_generation)=
 (p_tenant_id,p_game_id,p_generation) AND x.state='current';
 SELECT x.* INTO STRICT v FROM sync_fence.stats_fact_versions x
 WHERE (x.tenant_id,x.game_id,x.id)=(p_tenant_id,p_game_id,h.stats_version_id);
 SELECT x.* INTO STRICT change_event FROM public.operation_events x
 WHERE (x.tenant_id,x.game_id,x.id)=
 (p_tenant_id,p_game_id,c.change_event_id)
 AND x.event_kind='play_change' AND x.ledger_kind='accepted'
 AND NOT x.is_tombstone AND x.replaced_at IS NULL AND x.retired_at IS NULL;
 SELECT x.* INTO STRICT change_ledger FROM public.idempotency_ledger x
 WHERE (x.tenant_id,x.d5)=(p_tenant_id,c.d5)
 AND x.kind='accepted' AND x.retired_at IS NULL;
 SELECT pg_catalog.count(*),COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.jsonb_build_object(
 'item',pg_catalog.to_jsonb(i),
 'original_event',pg_catalog.to_jsonb(e),
 'original_ledger',pg_catalog.to_jsonb(ol),
 'original_history',pg_catalog.to_jsonb(hi),
 'original_play_row',pg_catalog.to_jsonb(op),
 'original_play_runners',original_runners.rows,
 'effective_play_row',pg_catalog.to_jsonb(ep),
 'effective_play_runners',effective_runners.rows)
 ORDER BY i.d1),'[]'::jsonb)
 INTO member_count,members
 FROM sync_fence.p3_projection_capsule_items i
 LEFT JOIN public.operation_events e ON
 (e.tenant_id,e.id)=(i.tenant_id,i.original_event_id)
 LEFT JOIN public.idempotency_ledger ol ON
 (ol.tenant_id,ol.d5)=(e.tenant_id,e.d5)
 LEFT JOIN sync_fence.ordinary_pitch_history hi ON
 (hi.tenant_id,hi.game_id,hi.internal_generation,hi.source_event_id,hi.d1)=
 (i.tenant_id,i.game_id,i.internal_generation,i.original_event_id,i.d1)
 AND hi.history_version=cp.history_version
 LEFT JOIN public.play_rows op ON
 (op.tenant_id,op.id)=(i.tenant_id,i.original_play_row_id)
 LEFT JOIN public.play_rows ep ON
 (ep.tenant_id,ep.id)=(i.tenant_id,i.effective_play_row_id)
 CROSS JOIN LATERAL (SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(r) ORDER BY r.base),'[]'::jsonb) rows
 FROM public.play_runners r WHERE r.tenant_id=i.tenant_id
 AND r.play_id=i.original_play_row_id) original_runners
 CROSS JOIN LATERAL (SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(r) ORDER BY r.base),'[]'::jsonb) rows
 FROM public.play_runners r WHERE r.tenant_id=i.tenant_id
 AND r.play_id=i.effective_play_row_id) effective_runners
 WHERE (i.tenant_id,i.game_id,i.internal_generation,i.capsule_id)=
 (p_tenant_id,p_game_id,p_generation,h.capsule_id);
 anchor_mode:=cp.content->>'formatVersion'='nonplay-prefix-checkpoint-v1';
 IF anchor_mode THEN
  -- P3当時のT5とLC現在版を分け、最初のcontrolより前だけを検証する。
  IF member_count IS DISTINCT FROM c.watermark
  OR member_count NOT BETWEEN 1 AND 26
  OR cp.id IS DISTINCT FROM c.next_checkpoint_id
  OR cp.history_version IS DISTINCT FROM
  (c.next_checkpoint_content->>'history_version')::bigint
  OR cp.content->'content'->'scope'->>'tenantId' IS DISTINCT FROM
  p_tenant_id::text
  OR cp.content->'content'->'scope'->>'gameId' IS DISTINCT FROM
  p_game_id::text
  OR cp.content->'content'->>'d3' IS DISTINCT FROM
  cp.confirmed_watermark::text
  OR cp.applied_watermark IS DISTINCT FROM cp.confirmed_watermark
  OR pg_catalog.jsonb_typeof(cp.content->'content'->'controlBridges')
  IS DISTINCT FROM 'array'
  OR pg_catalog.jsonb_array_length(
  cp.content->'content'->'controlBridges')<1
  OR cp.content->'content'->'controlBridges'->0->'checkpointBefore'->>'id'
  IS DISTINCT FROM c.next_checkpoint_id::text
  OR (cp.content->'content'->'controlBridges'->0->'checkpointBefore'
  ->>'revision')::bigint<c.next_checkpoint_revision
  OR cp.content->'content'->'controlBridges'->0->'source'->>'d1'
  IS DISTINCT FROM (v.source_count+1)::text
  OR cp.confirmed_watermark<v.source_count+1
  OR h.source_set_digest IS DISTINCT FROM c.source_set_digest
  OR h.stats_version_id IS DISTINCT FROM c.stats_version_id
  OR v.is_current OR v.invalidated_at IS NULL
  OR v.source_count NOT BETWEEN c.watermark AND c.watermark+100
  OR v.model_sha256 IS DISTINCT FROM c.stats_model_sha256
  THEN RAISE EXCEPTION 'P3 anchor read rejected' USING ERRCODE='42501';
  END IF;
  SELECT a.preparation INTO STRICT first_control_preparation
  FROM sync_fence.lifecycle_write_admissions a
  JOIN public.operation_events e ON
  (e.tenant_id,e.game_id,e.id)=(a.tenant_id,a.game_id,a.source_event_id)
  JOIN public.event_slots slot ON
  (slot.tenant_id,slot.game_id,slot.generation,slot.d1)=
  (e.tenant_id,e.game_id,e.generation,e.d1)
  JOIN public.idempotency_ledger l ON
  (l.tenant_id,l.d5)=(e.tenant_id,e.d5)
  WHERE (a.tenant_id,a.game_id,a.internal_generation)=
  (p_tenant_id,p_game_id,p_generation)
  AND a.source_event_id::text=cp.content->'content'->'controlBridges'
  ->0->'source'->>'eventId'
  AND a.action='end' AND a.state='consumed' AND a.consumed_at IS NOT NULL
  AND a.preparation->'storage'->'row'->>'id'=cp.id::text
  AND a.preparation->'storage'->'row'->'content'->>'version'='3'
  AND a.preparation->'before_source'->'checkpoint'->'ref'=
  cp.content->'content'->'controlBridges'->0->'checkpointBefore'
  AND a.preparation->'after_source'->'checkpoint'->'content'
  ->'controlBridges'->0=cp.content->'content'->'controlBridges'->0
  AND e.event_kind='game_end_declaration' AND e.ledger_kind='accepted'
  AND e.generation=p_generation AND e.d1=v.source_count+1
  AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
  AND e.import_batch_id IS NULL AND NOT e.migration_unverified
  AND slot.confirmed_version=1 AND slot.xmin=a.xmin AND e.xmin=a.xmin
  AND l.kind='accepted' AND l.source_fingerprint=a.event_fingerprint
  AND l.retired_at IS NULL AND l.import_batch_id IS NULL
  AND a.transaction_id ~ '^[1-9][0-9]{0,19}$'
  AND a.xmin::text::numeric=pg_catalog.mod(
  a.transaction_id::numeric,4294967296::numeric);
  source_upper:=v.source_count;
 ELSE
 IF member_count IS DISTINCT FROM c.watermark OR member_count NOT BETWEEN 1 AND 26
 THEN RAISE EXCEPTION 'P3 current count rejected' USING ERRCODE='42501'; END IF;
 IF h.source_set_digest IS DISTINCT FROM c.source_set_digest
 THEN RAISE EXCEPTION 'P3 current source set rejected' USING ERRCODE='42501'; END IF;
 IF v.model_sha256 IS DISTINCT FROM c.stats_model_sha256
 THEN RAISE EXCEPTION 'P3 current model rejected' USING ERRCODE='42501'; END IF;
 IF v.source_count<c.watermark
 THEN RAISE EXCEPTION 'P3 current source count rejected' USING ERRCODE='42501'; END IF;
 source_upper:=c.watermark;
 END IF;
 IF source_upper>c.watermark THEN
 SELECT pg_catalog.count(*),COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.jsonb_build_object(
 'event',pg_catalog.to_jsonb(e),'ledger',pg_catalog.to_jsonb(l),
 'history',pg_catalog.to_jsonb(hi),'play_row',pg_catalog.to_jsonb(p),
 'play_runners',r.rows) ORDER BY slot.d1),'[]'::jsonb)
 INTO suffix_count,suffix_members
 FROM public.event_slots slot
 JOIN public.operation_events e ON
 (e.tenant_id,e.game_id,e.generation,e.d1)=
 (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
 AND e.event_kind='play_input' AND e.ledger_kind='accepted'
 AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
 JOIN public.idempotency_ledger l ON
 (l.tenant_id,l.d5)=(e.tenant_id,e.d5)
 AND l.kind='accepted' AND l.retired_at IS NULL
 JOIN sync_fence.ordinary_pitch_history hi ON
 (hi.tenant_id,hi.game_id,hi.internal_generation,hi.d1,hi.source_event_id)=
 (e.tenant_id,e.game_id,e.generation,e.d1,e.id)
 AND hi.history_version=cp.history_version
 JOIN public.play_rows p ON
 (p.tenant_id,p.game_id,p.source_event_id)=(e.tenant_id,e.game_id,e.id)
 AND p.hidden_at IS NULL
 CROSS JOIN LATERAL (SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(pr) ORDER BY pr.base),'[]'::jsonb) rows
 FROM public.play_runners pr WHERE pr.tenant_id=p.tenant_id
 AND pr.play_id=p.id) r
 WHERE (slot.tenant_id,slot.game_id,slot.generation)=
 (p_tenant_id,p_game_id,p_generation)
 AND slot.d1>c.watermark AND slot.d1<=source_upper
 AND slot.confirmed_version=1;
 IF suffix_count IS DISTINCT FROM source_upper-c.watermark THEN
 RAISE EXCEPTION 'P3 current read rejected' USING ERRCODE='42501'; END IF;
 END IF;
 SELECT pg_catalog.count(*),COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(s) ORDER BY s.d1),'[]'::jsonb)
 INTO source_count,source_rows FROM sync_fence.stats_primitive_sources s
 WHERE (s.tenant_id,s.game_id,s.fact_version_id)=
 (p_tenant_id,p_game_id,v.id);
 IF anchor_mode THEN
  IF source_count IS DISTINCT FROM v.source_count THEN
  RAISE EXCEPTION 'P3 anchor read rejected' USING ERRCODE='42501'; END IF;
  RETURN QUERY SELECT pg_catalog.jsonb_build_object(
  'kind','p3-anchor','head',pg_catalog.to_jsonb(h),
  'capsule',pg_catalog.to_jsonb(c),'checkpoint',
  first_control_preparation->'storage'->'row',
  'nonplay_checkpoint',pg_catalog.to_jsonb(cp),
  'first_control_preparation',first_control_preparation,
  'stats',pg_catalog.to_jsonb(v),'change_event',
  pg_catalog.to_jsonb(change_event),'change_ledger',
  pg_catalog.to_jsonb(change_ledger),'members',members,
  'suffix',suffix_members,'stats_sources',source_rows)::text;
  RETURN;
 END IF;
 IF v.is_current THEN
 SELECT * INTO health FROM (WITH canonical_scope AS (
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
)
SELECT COALESCE(ch.game_count,0) AS game_count,COALESCE(ch.canonical_source_count,0) AS canonical_source_count,COALESCE(ch.unavailable_count,0) AS unavailable_count,COALESCE(ch.canonical_source_set_sha256,encode(sha256(convert_to('accepted-play-slot-v1:empty','UTF8')),'hex')) AS canonical_source_set_sha256 FROM (VALUES(1)) singleton(n) LEFT JOIN canonical_health ch ON true) p3_current_health;
 IF source_count IS DISTINCT FROM v.source_count
 OR health.game_count IS DISTINCT FROM 1::bigint
 OR health.unavailable_count IS DISTINCT FROM 0::bigint
 OR health.canonical_source_count IS DISTINCT FROM v.source_count
 OR health.canonical_source_set_sha256 IS DISTINCT FROM v.source_set_sha256
 THEN RAISE EXCEPTION 'P3 current read rejected' USING ERRCODE='42501'; END IF;
 END IF;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object(
 'kind','p3-current','head',pg_catalog.to_jsonb(h),
 'capsule',pg_catalog.to_jsonb(c),
 'checkpoint',pg_catalog.to_jsonb(cp) || pg_catalog.jsonb_build_object(
  'id',c.next_checkpoint_id,
  'history_version',(c.next_checkpoint_content->>'history_version')::bigint,
  'revision',c.next_checkpoint_revision,
  'confirmed_watermark',
  (c.next_checkpoint_content->>'confirmed_watermark')::bigint,
  'applied_watermark',
  (c.next_checkpoint_content->>'confirmed_watermark')::bigint,
  'content',c.next_checkpoint_content,
  'content_digest',c.next_checkpoint_digest),
 'stats',pg_catalog.to_jsonb(v),
 'change_event',pg_catalog.to_jsonb(change_event),
 'change_ledger',pg_catalog.to_jsonb(change_ledger),
 'members',members,'suffix',suffix_members,'stats_sources',source_rows)::text;
END;
$p3_current$;
ALTER FUNCTION sync_right_api.read_p3_current(uuid,uuid,bigint)
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_p3_current(uuid,uuid,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.read_p3_current(uuid,uuid,bigint)
 TO pitchlog_app;
