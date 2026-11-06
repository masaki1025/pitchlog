-- 毎球CSV 88列projectionの候補table。正式migration/認可未受理。
-- 記録時に確定した88列だけを保持し、export時にT1を再計算しない。
CREATE TABLE public.play_export_snapshots (
  tenant_id uuid NOT NULL,
  game_id uuid NOT NULL,
  play_row_id uuid NOT NULL,
  plays_csv_json jsonb NOT NULL,
  recording_generation bigint NULL,
  event_sequence bigint NULL,
  captured_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
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
GRANT SELECT ON TABLE public.play_export_snapshots TO pitchlog_app;
CREATE POLICY play_export_snapshots_select ON public.play_export_snapshots
  FOR SELECT TO pitchlog_app
  USING (
    tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid
    AND session_user = 'pitchlog_app'
  );
