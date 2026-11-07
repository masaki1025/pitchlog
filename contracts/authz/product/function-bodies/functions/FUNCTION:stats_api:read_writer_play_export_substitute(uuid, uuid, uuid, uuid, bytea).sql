-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:stats_api:read_writer_play_export_substitute(uuid, uuid, uuid, uuid, bytea)

CREATE FUNCTION stats_api.read_writer_play_export_substitute(
  p_attempt_id uuid,p_phase_id uuid,p_source_event_id uuid,
  p_player_id uuid,p_binding_nonce bytea)
RETURNS TABLE(substitution_event_id uuid,substitution_d2 bigint,
  substitution_payload jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $export_substitute$
#variable_conflict use_column
DECLARE tenant uuid; own_xid text; bound_game uuid; bound_device uuid;
  bound_generation bigint; bound_d5 uuid; own_d2 bigint;
BEGIN
 tenant:=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 IF session_user IS DISTINCT FROM 'pitchlog_app'
   OR current_user IS DISTINCT FROM 'pitchlog_sync_right_fn_owner'
   OR tenant IS NULL OR p_attempt_id IS NULL OR p_phase_id IS NULL
   OR p_source_event_id IS NULL OR p_player_id IS NULL
   OR p_binding_nonce IS NULL OR pg_catalog.octet_length(p_binding_nonce)<>32
   OR pg_catalog.current_setting('transaction_read_only') IS DISTINCT FROM 'off'
 THEN RAISE EXCEPTION 'play export substitute boundary rejected'
   USING ERRCODE='42501'; END IF;
 SELECT b.game_id,b.device_id,b.internal_generation,b.d5
 INTO STRICT bound_game,bound_device,bound_generation,bound_d5
 FROM sync_fence.writer_bindings b
 WHERE b.tenant_id=tenant AND b.attempt_id=p_attempt_id AND b.phase_id=p_phase_id
   AND b.state='open' AND b.transaction_id=own_xid
   AND b.expires_at>pg_catalog.clock_timestamp();
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
   p_binding_nonce,bound_device,bound_game);
 SELECT e.d2 INTO STRICT own_d2 FROM public.operation_events e
 WHERE e.tenant_id=tenant AND e.game_id=bound_game AND e.id=p_source_event_id
   AND e.generation=bound_generation AND e.d5=bound_d5
   AND e.event_kind='play_input' AND e.ledger_kind='accepted'
   AND e.d2 IS NOT NULL AND NOT e.is_tombstone
   AND e.replaced_at IS NULL AND e.retired_at IS NULL
   AND e.import_batch_id IS NULL AND NOT e.migration_unverified
   AND e.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric);
 RETURN QUERY SELECT e.id,e.d2,e.payload FROM public.operation_events e
 JOIN sync_fence.substitution_write_receipts r
   ON (r.tenant_id,r.game_id,r.source_event_id,r.source_d1)
    =(e.tenant_id,e.game_id,e.id,e.d1)
 WHERE e.tenant_id=tenant AND e.game_id=bound_game AND e.d2<own_d2
   AND e.event_kind='substitution' AND e.ledger_kind='accepted'
   AND NOT e.is_tombstone AND e.replaced_at IS NULL AND e.retired_at IS NULL
   AND e.import_batch_id IS NULL AND NOT e.migration_unverified
   AND e.payload->>'formatVersion'='substitution-event-v1'
   AND pg_catalog.jsonb_typeof(e.payload->'incomingSnapshots')='array'
   AND EXISTS (SELECT 1 FROM pg_catalog.jsonb_array_elements(
     e.payload->'incomingSnapshots') AS item
     WHERE item->>'playerId'=p_player_id::text)
 ORDER BY e.d2 DESC,e.id DESC LIMIT 1;
 PERFORM sync_fence_api.assert_writer_binding(tenant,p_attempt_id,p_phase_id,
   p_binding_nonce,bound_device,bound_game);
END;
$export_substitute$;
ALTER FUNCTION stats_api.read_writer_play_export_substitute(
  uuid,uuid,uuid,uuid,bytea) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION stats_api.read_writer_play_export_substitute(
  uuid,uuid,uuid,uuid,bytea) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION stats_api.read_writer_play_export_substitute(
  uuid,uuid,uuid,uuid,bytea) TO pitchlog_app;
