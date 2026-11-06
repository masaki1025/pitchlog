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

-- active-only replay索引では置換/退役原本を含む監査keysetを支えない。
-- 正式0047と実PG EXPLAINの受理前は候補であり、既共有DBには適用しない。
CREATE INDEX ix_operation_events_export_audit
  ON public.operation_events (tenant_id, game_id, d2 ASC NULLS LAST, id)
  WHERE ledger_kind = 'accepted';
