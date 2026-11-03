-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:writer_bindings:first_ball_stamp_writer_bindings

CREATE POLICY first_ball_stamp_writer_bindings ON sync_fence.writer_bindings FOR SELECT TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
