-- ELEMENT-TYPE: table
-- ELEMENT-ID: attempt_retirements

ALTER TABLE sync_fence.attempt_retirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.attempt_retirements FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.attempt_retirements FROM PUBLIC,pitchlog_app,pitchlog_sync_binding_actor;
