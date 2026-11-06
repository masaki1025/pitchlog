-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:sync_right_api:read_lifecycle_display(uuid, uuid)

CREATE FUNCTION sync_right_api.read_lifecycle_display(
 p_tenant_id uuid,p_game_id uuid)
RETURNS TABLE(record_json text) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $lifecycle_display$
DECLARE g record; h sync_fence.game_lifecycle_heads%ROWTYPE; lifecycle jsonb;
BEGIN
 IF session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_game_id IS NULL THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
 SELECT x.id,x.status INTO g FROM public.games x
 WHERE x.tenant_id=p_tenant_id AND x.id=p_game_id AND x.started_at IS NOT NULL
 AND x.trashed_at IS NULL AND x.hidden_at IS NULL AND x.import_batch_id IS NULL
 AND x.status IN ('in_progress','finished');
 IF NOT FOUND THEN RETURN; END IF;
 SELECT x.* INTO h FROM sync_fence.game_lifecycle_heads x WHERE x.tenant_id=p_tenant_id
 AND x.game_id=p_game_id;
 IF NOT FOUND THEN
  IF g.status<>'in_progress' OR EXISTS(SELECT 1 FROM public.operation_events e
  WHERE e.tenant_id=p_tenant_id AND e.game_id=p_game_id
  AND e.event_kind IN ('game_end_declaration','game_reopen')
  AND e.ledger_kind='accepted' AND e.replaced_at IS NULL AND e.retired_at IS NULL)
  THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
  lifecycle:=pg_catalog.jsonb_build_object('formatVersion','native-game-lifecycle-read-v1',
  'status','in_progress','lastVersion','0','active',NULL,'activeStatsVersionId',NULL);
 ELSE
  IF h.is_finished IS DISTINCT FROM (g.status='finished')
  OR NOT EXISTS(SELECT 1 FROM sync_fence.lifecycle_write_admissions a
  JOIN public.operation_events e ON e.tenant_id=a.tenant_id AND e.game_id=a.game_id
  AND e.id=a.source_event_id
  JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5
  JOIN public.event_slots slot ON (slot.tenant_id,slot.game_id,slot.generation,slot.d1)
  =(e.tenant_id,e.game_id,e.generation,e.d1)
  WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id AND a.state='consumed'
  AND a.consumed_at IS NOT NULL AND e.id=h.last_control_event_id
  AND e.event_kind=(CASE WHEN h.is_finished THEN 'game_end_declaration' ELSE
 'game_reopen' END)
  AND a.action=(CASE WHEN h.is_finished THEN 'end' ELSE 'reopen' END)
  AND e.ledger_kind='accepted' AND NOT e.is_tombstone
  AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
  AND slot.confirmed_version=1 AND l.kind='accepted' AND l.retired_at IS NULL
  AND l.source_fingerprint=a.event_fingerprint)
  THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
  IF h.is_finished AND NOT EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v
  JOIN sync_fence.lifecycle_write_admissions a ON a.tenant_id=v.tenant_id AND a.game_id=v.game_id
  AND a.source_event_id=h.active_end_event_id AND a.receipt_id=h.active_receipt_id
  WHERE v.tenant_id=p_tenant_id AND v.game_id=p_game_id AND
 v.id=h.active_stats_version_id
  AND v.is_current AND v.invalidated_at IS NULL AND v.completion_state='confirmed_ended'
  AND v.completion_receipt_id=h.active_receipt_id
  AND v.public_pointer_receipt_id=h.active_receipt_id AND a.action='end' AND
 a.state='consumed')
  THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
  IF NOT h.is_finished AND EXISTS(SELECT 1 FROM sync_fence.stats_fact_versions v
  WHERE v.tenant_id=p_tenant_id AND v.game_id=p_game_id AND v.is_current
  AND v.completion_state='confirmed_ended') THEN RAISE EXCEPTION 'game lifecycle rejected' USING ERRCODE='42501'; END IF;
  lifecycle:=pg_catalog.jsonb_build_object('formatVersion','native-game-lifecycle-read-v1',
  'status',g.status,'lastVersion',h.last_version::text,
  'active',CASE WHEN h.is_finished THEN
 pg_catalog.jsonb_build_object('version',h.last_version::text,
  'eventId',h.active_end_event_id::text,'receiptId',h.active_receipt_id::text) ELSE
 NULL END,
  'activeStatsVersionId',h.active_stats_version_id::text);
 END IF;
 RETURN QUERY SELECT lifecycle::text;
END;
$lifecycle_display$;

ALTER FUNCTION sync_right_api.read_lifecycle_display(uuid, uuid) OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.read_lifecycle_display(uuid, uuid) FROM PUBLIC,pitchlog_app;
GRANT EXECUTE ON FUNCTION sync_right_api.read_lifecycle_display(uuid, uuid) TO pitchlog_app;
