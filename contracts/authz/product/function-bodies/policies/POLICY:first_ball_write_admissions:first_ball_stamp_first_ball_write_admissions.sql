-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:first_ball_write_admissions:first_ball_stamp_first_ball_write_admissions

CREATE POLICY first_ball_stamp_first_ball_write_admissions ON sync_fence.first_ball_write_admissions FOR ALL TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
