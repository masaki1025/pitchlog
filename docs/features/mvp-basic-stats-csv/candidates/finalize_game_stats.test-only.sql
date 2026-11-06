-- TEST ONLY: 正式な終了確定providerではない。catalog/HTTPへ接続しない。
CREATE FUNCTION stats_basic_api.finalize_game_stats(p_tenant_id uuid,p_game_id uuid,p_completion_receipt_id uuid,p_public_pointer_receipt_id uuid,p_model_sha256 text)
RETURNS TABLE(fact_version_id uuid,revision bigint,completion_state text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $finalize$
#variable_conflict use_column
DECLARE tenant uuid; series record; fact_version_id uuid; revision bigint; completion_state text;
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 IF session_user IS DISTINCT FROM 'pitchlog_app' OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
  OR tenant IS NULL OR p_tenant_id IS DISTINCT FROM tenant
  OR p_game_id IS NULL OR p_completion_receipt_id IS NULL
  OR p_public_pointer_receipt_id IS NULL
  OR p_model_sha256 IS DISTINCT FROM 'sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d'
  OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 THEN RAISE EXCEPTION 'basic stats boundary rejected' USING ERRCODE='42501';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public.games g WHERE g.tenant_id=tenant
   AND g.id=p_game_id AND g.status='finished'
   AND g.hidden_at IS NULL AND g.trashed_at IS NULL) THEN
  RAISE EXCEPTION 'basic stats finalize game not found' USING ERRCODE='42501';
 END IF;
 UPDATE sync_fence.stats_fact_versions v
  SET completion_state='confirmed_ended',
      completion_receipt_id=p_completion_receipt_id,
      public_pointer_receipt_id=p_public_pointer_receipt_id,
      updated_at=pg_catalog.now()
  WHERE v.tenant_id=tenant AND v.game_id=p_game_id
    AND v.model_sha256=p_model_sha256 AND v.is_current
    AND v.invalidated_at IS NULL AND v.completion_state='current_open'
  RETURNING v.id,v.revision,v.completion_state INTO fact_version_id,revision,completion_state;
 IF FOUND THEN
  RETURN QUERY SELECT fact_version_id,revision,completion_state;
  RETURN;
 END IF;
 SELECT v.* INTO series FROM sync_fence.stats_fact_versions v
  WHERE v.tenant_id=tenant AND v.game_id=p_game_id
    AND v.model_sha256=p_model_sha256 AND v.is_current
    AND v.invalidated_at IS NULL;
 IF NOT FOUND OR series.completion_state<>'confirmed_ended'
    OR series.completion_receipt_id IS DISTINCT FROM p_completion_receipt_id
    OR series.public_pointer_receipt_id IS DISTINCT FROM p_public_pointer_receipt_id THEN
  RAISE EXCEPTION 'basic stats finalize version not found' USING ERRCODE='42501';
 END IF;
 RETURN QUERY SELECT series.id,series.revision,series.completion_state;
END;
$finalize$;
ALTER FUNCTION stats_basic_api.finalize_game_stats(uuid,uuid,uuid,uuid,text) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_basic_api.finalize_game_stats(uuid,uuid,uuid,uuid,text) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION stats_basic_api.finalize_game_stats(uuid,uuid,uuid,uuid,text) TO pitchlog_app;
