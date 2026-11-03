-- ELEMENT-TYPE: table
-- ELEMENT-ID: writer_admissions

ALTER TABLE sync_fence.writer_admissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.writer_admissions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.writer_admissions FROM PUBLIC,pitchlog_app,pitchlog_sync_binding_actor;
