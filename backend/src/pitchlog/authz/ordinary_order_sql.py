"""既SQLAlchemy文法を拡張せずO4集約と実D2末尾を有限返却するread bridge。"""


def candidate_order_function_bodies():
    """app実session/tenant限定、public既原本のreadだけを許す。"""
    return {
        "read_ordinary_order_summary": """CREATE FUNCTION
sync_right_api.read_ordinary_order_summary(p_tenant_id uuid,p_game_id uuid)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $order$
DECLARE tail jsonb; duplicate boolean; epoch bigint;
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid THEN
 RAISE EXCEPTION 'ordinary order read rejected' USING ERRCODE='42501';
 END IF;
 SELECT r.recovery_generation INTO STRICT epoch
 FROM public.recording_generations r
 WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id AND r.kind='normal'
 AND r.revoked_at IS NULL AND r.retired_at IS NULL AND r.import_batch_id IS NULL;
 IF epoch IS NULL OR epoch<=0 THEN
 RAISE EXCEPTION 'ordinary order epoch rejected' USING ERRCODE='42501';
 END IF;
 SELECT pg_catalog.to_jsonb(e) INTO tail FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.d2 IS NOT NULL
 ORDER BY e.d2 DESC,e.id DESC LIMIT 1;
 SELECT EXISTS(SELECT 1 FROM public.operation_events e
 WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.d2 IS NOT NULL
 GROUP BY e.d2 HAVING pg_catalog.count(*)>1 LIMIT 1) INTO duplicate;
 RETURN QUERY SELECT pg_catalog.jsonb_build_object(
 'tail',tail,'duplicate',duplicate,'recovery_generation',epoch)::text;
END;
$order$;
"""
    }
