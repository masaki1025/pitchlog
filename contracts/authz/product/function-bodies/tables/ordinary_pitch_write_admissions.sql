-- ELEMENT-TYPE: table
-- ELEMENT-ID: ordinary_pitch_write_admissions

ALTER TABLE sync_fence.ordinary_pitch_write_admissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.ordinary_pitch_write_admissions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.ordinary_pitch_write_admissions FROM PUBLIC,pitchlog_app;
