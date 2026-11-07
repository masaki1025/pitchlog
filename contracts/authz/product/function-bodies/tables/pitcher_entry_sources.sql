-- ELEMENT-TYPE: table
-- ELEMENT-ID: pitcher_entry_sources

ALTER TABLE sync_fence.pitcher_entry_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.pitcher_entry_sources FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.pitcher_entry_sources FROM PUBLIC,pitchlog_app,pitchlog_initial_actor,pitchlog_sync_binding_actor,pitchlog_rg1_control_actor;
