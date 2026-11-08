-- ELEMENT-TYPE: table
-- ELEMENT-ID: play_export_p3_snapshots

ALTER TABLE sync_fence.play_export_p3_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.play_export_p3_snapshots FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.play_export_p3_snapshots FROM PUBLIC,pitchlog_app,pitchlog_initial_actor,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor,pitchlog_initial_fn_owner,pitchlog_sync_binding_fn_owner,pitchlog_sync_right_fn_owner;
