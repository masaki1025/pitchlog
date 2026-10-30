-- ELEMENT-TYPE: table
-- ELEMENT-ID: ordinary_pitch_history

ALTER TABLE sync_fence.ordinary_pitch_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.ordinary_pitch_history FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.ordinary_pitch_history FROM PUBLIC,pitchlog_app;
