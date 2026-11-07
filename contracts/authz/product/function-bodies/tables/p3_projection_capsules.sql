-- ELEMENT-TYPE: table
-- ELEMENT-ID: p3_projection_capsules

ALTER TABLE sync_fence.p3_projection_capsules ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.p3_projection_capsules FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.p3_projection_capsules FROM PUBLIC,pitchlog_app,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor;
