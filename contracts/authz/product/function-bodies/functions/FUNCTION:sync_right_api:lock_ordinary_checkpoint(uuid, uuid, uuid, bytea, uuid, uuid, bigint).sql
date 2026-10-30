-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:lock_ordinary_checkpoint(uuid, uuid, uuid, bytea, uuid, uuid, bigint)

CREATE FUNCTION sync_right_api.lock_ordinary_checkpoint(p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,p_binding_nonce bytea,p_device_id uuid,p_game_id uuid,p_generation bigint)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $prefix$
BEGIN

IF session_user <> 'pitchlog_app' OR current_user <> 'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_device_id IS NULL
 OR p_game_id IS NULL OR p_binding_nonce IS NULL
 OR pg_catalog.octet_length(p_binding_nonce) <> 32 THEN
 RAISE EXCEPTION 'sync writer binding rejected' USING ERRCODE='42501';
END IF;
-- 実関数未供給なら例外で閉じる。callerのnonceだけでは成功しない。
PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,
 p_phase_id,p_binding_nonce,p_device_id,p_game_id);

 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_game_id IS NULL
 OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_generation IS NULL OR p_generation<=0 THEN
 RAISE EXCEPTION 'ordinary prefix read rejected' USING ERRCODE='42501';
 END IF;

 RETURN QUERY SELECT (pg_catalog.to_jsonb(c) || pg_catalog.jsonb_build_object('last_play_row',s.expected_play_row))::text
 FROM sync_fence.ordinary_pitch_checkpoints c
 LEFT JOIN sync_fence.ordinary_pitch_write_admissions s
 ON s.tenant_id=c.tenant_id AND s.game_id=c.game_id
 AND s.internal_generation=c.internal_generation AND s.checkpoint_id=c.id
 AND s.source_event_id=(c.content->'last_source'->>'id')::uuid
 AND s.state='consumed' AND s.consumed_at=c.saved_at
 AND s.checkpoint_revision+1=c.revision AND s.next_checkpoint_content=c.content
 WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id
 AND c.internal_generation=p_generation LIMIT 2 FOR UPDATE OF c;

END;
$prefix$;

ALTER FUNCTION sync_right_api.lock_ordinary_checkpoint(uuid, uuid, uuid, bytea, uuid, uuid, bigint) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.lock_ordinary_checkpoint(uuid, uuid, uuid, bytea, uuid, uuid, bigint) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.lock_ordinary_checkpoint(uuid, uuid, uuid, bytea, uuid, uuid, bigint) TO pitchlog_app;
