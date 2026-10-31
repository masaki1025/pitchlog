-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:read_play_prefix_checkpoint(uuid, uuid, bigint)

CREATE FUNCTION sync_right_api.read_play_prefix_checkpoint(p_tenant_id uuid,p_game_id uuid,p_generation bigint)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $prefix$
BEGIN

 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_generation IS NULL OR p_generation<=0 THEN
 RAISE EXCEPTION 'ordinary prefix read rejected' USING ERRCODE='42501';
 END IF;

 RETURN QUERY SELECT (pg_catalog.jsonb_build_object('kind','checkpoint','row',pg_catalog.to_jsonb(c) || pg_catalog.jsonb_build_object('last_play_row',s.expected_play_row,'source_evidence',(SELECT pg_catalog.jsonb_build_object(
 'all_play_count',pg_catalog.count(*) FILTER (WHERE e.event_kind='play_input'),
 'ordinary_play_count',pg_catalog.count(*) FILTER (WHERE e.event_kind='play_input'
 AND e.payload->>'formatVersion' IN ('first-ball-play-v1','ordinary-pitch-play-v1')
 AND
e.payload->'calculation'->'response'->'value'->'t1'->>'plateAppearanceEnded'='false'),
 'invalid_count',pg_catalog.count(*) FILTER (WHERE e.ledger_kind<>'accepted' OR
e.is_tombstone
 OR e.replaced_at IS NOT NULL OR e.retired_at IS NOT NULL OR e.import_batch_id IS
NOT NULL
 OR e.migration_unverified OR e.legacy_row_identifier IS NOT NULL),
 'non_play_count',pg_catalog.count(*) FILTER (WHERE e.event_kind<>'play_input'),
 'history_count',(SELECT pg_catalog.count(*) FROM sync_fence.ordinary_pitch_history h
 WHERE h.tenant_id=c.tenant_id AND h.game_id=c.game_id AND
h.internal_generation=c.internal_generation
 AND h.history_version=c.history_version),
 'pa_change_count',pg_catalog.count(*) FILTER (WHERE e.event_kind<>'play_input'
 AND e.d1>CASE WHEN c.content->'pa_start_source'->>'kind'='confirmed-play' THEN
 (SELECT z.d1 FROM public.operation_events z WHERE z.tenant_id=c.tenant_id
 AND z.game_id=c.game_id AND z.generation=c.internal_generation
 AND z.id=(c.content->'pa_start_source'->>'id')::uuid) ELSE 0 END))
 FROM public.operation_events e WHERE e.tenant_id=c.tenant_id AND e.game_id=c.game_id
 AND e.generation=c.internal_generation AND e.d1<=c.confirmed_watermark),'last_play_runners',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(pr) ORDER BY pr.base),'[]'::jsonb) FROM public.play_runners pr WHERE pr.tenant_id=c.tenant_id AND pr.play_id=s.play_row_id))))::text
 FROM sync_fence.ordinary_pitch_checkpoints c
 LEFT JOIN sync_fence.ordinary_pitch_write_admissions s
 ON s.tenant_id=c.tenant_id AND s.game_id=c.game_id
 AND s.internal_generation=c.internal_generation AND s.checkpoint_id=c.id
 AND s.source_event_id=(c.content->'last_source'->>'id')::uuid
 AND s.state='consumed' AND s.consumed_at=c.saved_at
 AND s.checkpoint_revision+1=c.revision AND s.next_checkpoint_content=c.content
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation LIMIT 2;

 IF NOT FOUND THEN
 RETURN QUERY SELECT pg_catalog.jsonb_build_object('kind','first-ball-save',
 'source_event_id',f.source_event_id::text,'saved_at',f.consumed_at)::text
 FROM sync_fence.first_ball_write_admissions f
 WHERE f.tenant_id=p_tenant_id AND f.game_id=p_game_id
 AND f.internal_generation=p_generation AND f.state='consumed'
 AND f.source_event_id IS NOT NULL AND f.consumed_at IS NOT NULL LIMIT 2;
 END IF;

END;
$prefix$;

ALTER FUNCTION sync_right_api.read_play_prefix_checkpoint(uuid, uuid, bigint) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_play_prefix_checkpoint(uuid, uuid, bigint) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.read_play_prefix_checkpoint(uuid, uuid, bigint) TO pitchlog_app;
