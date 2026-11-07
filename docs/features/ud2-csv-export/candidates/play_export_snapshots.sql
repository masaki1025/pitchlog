-- 毎球CSV 88列projectionの候補table。正式migration/認可未受理。
-- 記録時に確定した88列だけを保持し、export時にT1を再計算しない。
CREATE TABLE public.play_export_snapshots (
  tenant_id uuid NOT NULL,
  game_id uuid NOT NULL,
  play_row_id uuid NOT NULL,
  plays_csv_json jsonb NOT NULL,
  full_innings_json jsonb NOT NULL,
  source_event_id uuid NOT NULL,
  play_version bigint NOT NULL CHECK (play_version > 0),
  recording_generation bigint NOT NULL,
  event_sequence bigint NOT NULL,
  captured_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  CONSTRAINT ck_play_export_snapshot_shapes CHECK (
    pg_catalog.jsonb_typeof(plays_csv_json) = 'object'
    AND pg_catalog.jsonb_typeof(full_innings_json) = 'array'
  ),
  PRIMARY KEY (tenant_id, play_row_id),
  FOREIGN KEY (tenant_id, game_id)
    REFERENCES public.games (tenant_id, id)
    ON DELETE NO ACTION,
  FOREIGN KEY (tenant_id, play_row_id)
    REFERENCES public.play_rows (tenant_id, id)
    ON DELETE NO ACTION
);
ALTER TABLE public.play_export_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.play_export_snapshots FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.play_export_snapshots FROM PUBLIC, pitchlog_app;
GRANT SELECT (
  tenant_id,game_id,play_row_id,plays_csv_json,full_innings_json,
  source_event_id,play_version,recording_generation,event_sequence,captured_at
) ON public.play_export_snapshots TO pitchlog_app;
GRANT INSERT (
  tenant_id,game_id,play_row_id,plays_csv_json,full_innings_json,
  source_event_id,play_version,recording_generation,event_sequence
) ON public.play_export_snapshots TO pitchlog_sync_right_fn_owner;
CREATE POLICY play_export_snapshots_select ON public.play_export_snapshots
  FOR SELECT TO pitchlog_app
  USING (
    tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid
    AND session_user = 'pitchlog_app'
  );
CREATE POLICY play_export_snapshots_insert ON public.play_export_snapshots
  FOR INSERT TO pitchlog_sync_right_fn_owner
  WITH CHECK (
    tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid
    AND session_user = 'pitchlog_app'
    AND current_user = 'pitchlog_sync_right_fn_owner'
  );

-- 同一RRの旧projectionを当該試合だけで読み、監査原本を全tenant走査しない。
CREATE INDEX ix_play_export_snapshots_game_captured
  ON public.play_export_snapshots (tenant_id,game_id,captured_at,play_row_id);
CREATE INDEX ix_play_rows_export_audit
  ON public.play_rows (tenant_id,game_id,play_number,id);

-- active-only replay索引では置換/退役原本を含む監査keysetを支えない。
-- 正式0047と実PG EXPLAINの受理前は候補であり、既共有DBには適用しない。
CREATE INDEX ix_operation_events_export_audit
  ON public.operation_events (tenant_id, game_id, d2 ASC NULLS LAST, id)
  WHERE ledger_kind = 'accepted';

-- 記録時の新出場者だけを、実writerと0044同TX印のある受理交代へ束縛する。
-- 正式0047/operation registryの受理前はowned候補に限る。
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
