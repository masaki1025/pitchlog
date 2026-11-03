-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:writer_admissions:first_ball_stamp_writer_admissions

CREATE POLICY first_ball_stamp_writer_admissions ON sync_fence.writer_admissions FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
