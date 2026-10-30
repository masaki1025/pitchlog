-- ELEMENT-TYPE: table
-- ELEMENT-ID: first_ball_write_admissions

ALTER TABLE sync_fence.first_ball_write_admissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.first_ball_write_admissions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.first_ball_write_admissions FROM PUBLIC,pitchlog_app,pitchlog_sync_binding_actor;
