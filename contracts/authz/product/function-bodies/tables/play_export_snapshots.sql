-- ELEMENT-TYPE: table
-- ELEMENT-ID: play_export_snapshots

ALTER TABLE public.play_export_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.play_export_snapshots FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.play_export_snapshots FROM PUBLIC, pitchlog_app;
