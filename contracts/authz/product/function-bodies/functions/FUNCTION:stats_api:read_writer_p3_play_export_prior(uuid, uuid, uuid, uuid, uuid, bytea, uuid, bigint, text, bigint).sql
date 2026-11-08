-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:read_writer_p3_play_export_prior(uuid, uuid, uuid, uuid, uuid, bytea, uuid, bigint, text, bigint)

CREATE FUNCTION stats_api.read_writer_p3_play_export_prior(
 p_attempt_id uuid,p_phase_id uuid,p_game_id uuid,p_capsule_id uuid,
 p_change_event_id uuid,p_binding_nonce bytea,p_checkpoint_id uuid,
 p_checkpoint_revision bigint,p_checkpoint_digest text,p_watermark bigint)
RETURNS TABLE(prior_capsule_id uuid,prior_native_version_id uuid,
 prior_checkpoint_id uuid,prior_checkpoint_revision bigint,
 prior_checkpoint_digest text,transaction_id text,
 game_source_count bigint,generation_source_count bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_csv_prior$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; binding_device uuid; generation bigint;
 model_hash text := 'sha256:882acb95c08d88deb724a77f2fdfb184de48a2252cd03f5ca44df5cd8b48f4c6';
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app'
 OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner' OR tenant IS NULL
 OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_game_id IS NULL
 OR p_capsule_id IS NULL OR p_change_event_id IS NULL
 OR p_checkpoint_id IS NULL OR p_checkpoint_revision IS NULL
 OR p_checkpoint_revision<1 OR p_checkpoint_digest IS NULL
 OR p_checkpoint_digest !~ '^[a-f0-9]{64}$' OR p_watermark IS NULL OR p_watermark<1
 OR p_binding_nonce IS NULL OR pg_catalog.octet_length(p_binding_nonce)<>32
 OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 THEN RAISE EXCEPTION 'P3 CSV prior source unavailable' USING ERRCODE='42501'; END IF;
 SELECT b.device_id,b.internal_generation INTO STRICT binding_device,generation
 FROM sync_fence.writer_bindings b
 WHERE (b.tenant_id,b.game_id,b.attempt_id,b.phase_id)
 =(tenant,p_game_id,p_attempt_id,p_phase_id)
 AND b.state='open' AND b.transaction_id=own_xid
 AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,binding_device,p_game_id);
 IF EXISTS(SELECT 1 FROM sync_fence.p3_projection_capsules c
 WHERE (c.tenant_id,c.game_id,c.internal_generation,c.id)
 =(tenant,p_game_id,generation,p_capsule_id)) THEN
 RAISE EXCEPTION 'P3 CSV prior source already published' USING ERRCODE='42501'; END IF;
 -- 前版は当該変更で増える前のsource_countを持つ保存済T5版だけを選ぶ。
 -- 変更eventをcanonical sourceへ混ぜず、checkpointと実source件数で束縛する。
 RETURN QUERY
 SELECT h.capsule_id,v.id,cp.id,cp.revision,cp.content_digest,own_xid,
  v.source_count,
  (SELECT count(*) FROM sync_fence.stats_primitive_sources s
   WHERE s.tenant_id=tenant AND s.game_id=p_game_id
   AND s.fact_version_id=v.id
   AND s.recording_generation=generation)::bigint
 FROM sync_fence.stats_fact_versions v
 JOIN sync_fence.ordinary_pitch_checkpoints cp ON
  (cp.tenant_id,cp.game_id,cp.id,cp.revision,cp.content_digest)
  =(tenant,p_game_id,p_checkpoint_id,p_checkpoint_revision,p_checkpoint_digest)
 LEFT JOIN sync_fence.p3_projection_heads h ON
  (h.tenant_id,h.game_id,h.internal_generation)=(tenant,p_game_id,generation)
 WHERE v.tenant_id=tenant AND v.game_id=p_game_id
  AND v.model_sha256=model_hash AND v.source_count=p_watermark
  AND v.completion_state IN ('current_open','confirmed_ended')
 ORDER BY v.revision DESC LIMIT 1;
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
 p_binding_nonce,binding_device,p_game_id);
END;
$p3_csv_prior$;
ALTER FUNCTION stats_api.read_writer_p3_play_export_prior(uuid, uuid, uuid, uuid, uuid, bytea, uuid, bigint, text, bigint) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.read_writer_p3_play_export_prior(uuid, uuid, uuid, uuid, uuid, bytea, uuid, bigint, text, bigint) FROM PUBLIC,pitchlog_app,pitchlog_initial_actor,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor,pitchlog_initial_fn_owner,pitchlog_sync_binding_fn_owner;
GRANT EXECUTE ON FUNCTION stats_api.read_writer_p3_play_export_prior(uuid, uuid, uuid, uuid, uuid, bytea, uuid, bigint, text, bigint) TO pitchlog_app;
