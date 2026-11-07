-- ELEMENT-TYPE: table
-- ELEMENT-ID: p3_projection_capsule_items

ALTER TABLE sync_fence.p3_projection_capsule_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.p3_projection_capsule_items FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.p3_projection_capsule_items FROM PUBLIC,pitchlog_app,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor;
