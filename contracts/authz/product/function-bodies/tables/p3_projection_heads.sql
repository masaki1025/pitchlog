-- ELEMENT-TYPE: table
-- ELEMENT-ID: p3_projection_heads

ALTER TABLE sync_fence.p3_projection_heads ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.p3_projection_heads FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.p3_projection_heads FROM PUBLIC,pitchlog_app,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor;
