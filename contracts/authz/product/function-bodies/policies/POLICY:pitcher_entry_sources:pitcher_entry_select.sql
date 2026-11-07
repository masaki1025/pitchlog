-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:pitcher_entry_sources:pitcher_entry_select

CREATE POLICY pitcher_entry_select ON sync_fence.pitcher_entry_sources AS PERMISSIVE FOR SELECT TO pitchlog_initial_fn_owner,pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
