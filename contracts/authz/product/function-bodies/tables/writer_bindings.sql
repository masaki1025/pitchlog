-- ELEMENT-TYPE: table
-- ELEMENT-ID: writer_bindings

ALTER TABLE sync_fence.writer_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.writer_bindings FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.writer_bindings FROM PUBLIC,pitchlog_app,pitchlog_sync_binding_actor;
