-- ELEMENT-TYPE: table
-- ELEMENT-ID: ordinary_pitch_checkpoints

ALTER TABLE sync_fence.ordinary_pitch_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.ordinary_pitch_checkpoints FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.ordinary_pitch_checkpoints FROM PUBLIC,pitchlog_app;
