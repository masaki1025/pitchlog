-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:read_ordinary_checkpoint(uuid, uuid, bigint)

CREATE FUNCTION sync_right_api.read_ordinary_checkpoint(p_tenant_id uuid,p_game_id uuid,p_generation bigint)
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

 RETURN QUERY SELECT (pg_catalog.jsonb_build_object('kind','checkpoint','row',pg_catalog.to_jsonb(c) || pg_catalog.jsonb_build_object('last_play_row',s.expected_play_row)))::text
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

ALTER FUNCTION sync_right_api.read_ordinary_checkpoint(uuid, uuid, bigint) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_ordinary_checkpoint(uuid, uuid, bigint) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.read_ordinary_checkpoint(uuid, uuid, bigint) TO pitchlog_app;
