-- ELEMENT-TYPE: table
-- ELEMENT-ID: p3_projection_page_progress

ALTER TABLE sync_fence.p3_projection_page_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.p3_projection_page_progress FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.p3_projection_page_progress FROM PUBLIC,pitchlog_app,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor;
