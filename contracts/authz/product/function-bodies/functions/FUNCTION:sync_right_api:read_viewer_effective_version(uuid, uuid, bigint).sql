-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:read_viewer_effective_version(uuid, uuid, bigint)

CREATE FUNCTION sync_right_api.read_viewer_effective_version(
    p_tenant_id uuid, p_game_id uuid, p_generation bigint
) RETURNS TABLE(record_json text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $viewer_effective$
BEGIN
    IF session_user IS DISTINCT FROM 'pitchlog_app'
       OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
       OR p_tenant_id IS NULL OR p_game_id IS NULL
       OR p_generation IS NULL OR p_generation <= 0
       OR p_tenant_id IS DISTINCT FROM
          NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
       OR pg_catalog.current_setting('transaction_isolation')
          IS DISTINCT FROM 'repeatable read'
       OR pg_catalog.current_setting('transaction_read_only')
          IS DISTINCT FROM 'on'
    THEN
        RAISE EXCEPTION 'viewer effective version rejected' USING ERRCODE='42501';
    END IF;
    RETURN QUERY
    SELECT pg_catalog.jsonb_build_object(
        'checkpoint', CASE WHEN c.id IS NULL THEN NULL ELSE
            pg_catalog.jsonb_build_object(
                'id',c.id::text,'revision',c.revision,
                'history_version',c.history_version,
                'confirmed_watermark',c.confirmed_watermark,
                'applied_watermark',c.applied_watermark,
                'content_digest',c.content_digest,'state',c.state
            ) END,
        'p3', CASE WHEN p.capsule_id IS NULL THEN NULL ELSE
            pg_catalog.jsonb_build_object(
                'capsule_id',p.capsule_id::text,'revision',p.revision,
                'source_set_digest',p.source_set_digest,
                'stats_version_id',p.stats_version_id::text
            ) END,
        'lifecycle', CASE WHEN l.last_version IS NULL THEN NULL ELSE
            pg_catalog.jsonb_build_object(
                'last_version',l.last_version,'is_finished',l.is_finished,
                'active_receipt_id',l.active_receipt_id::text,
                'active_stats_version_id',l.active_stats_version_id::text,
                'last_control_event_id',l.last_control_event_id::text
            ) END
    )::text
    FROM public.games g
    LEFT JOIN sync_fence.ordinary_pitch_checkpoints c
      ON (c.tenant_id,c.game_id,c.internal_generation)=
         (g.tenant_id,g.id,p_generation)
    LEFT JOIN sync_fence.p3_projection_heads p
      ON (p.tenant_id,p.game_id,p.internal_generation)=
         (g.tenant_id,g.id,p_generation)
    LEFT JOIN sync_fence.game_lifecycle_heads l
      ON (l.tenant_id,l.game_id)=(g.tenant_id,g.id)
    WHERE g.tenant_id=p_tenant_id AND g.id=p_game_id;
END;
$viewer_effective$;
ALTER FUNCTION sync_right_api.read_viewer_effective_version(uuid,uuid,bigint) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_viewer_effective_version(uuid,uuid,bigint) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.read_viewer_effective_version(uuid,uuid,bigint) TO pitchlog_app;
