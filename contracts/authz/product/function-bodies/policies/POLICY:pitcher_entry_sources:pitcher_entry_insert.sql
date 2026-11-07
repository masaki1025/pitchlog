-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:pitcher_entry_sources:pitcher_entry_insert

CREATE POLICY pitcher_entry_insert ON sync_fence.pitcher_entry_sources AS PERMISSIVE FOR INSERT TO pitchlog_initial_fn_owner,pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
