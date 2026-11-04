-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:ordinary_pitch_checkpoints:ordinary_pitch_update_ordinary_pitch_checkpoints

CREATE POLICY ordinary_pitch_update_ordinary_pitch_checkpoints ON sync_fence.ordinary_pitch_checkpoints FOR UPDATE TO pitchlog_sync_right_fn_owner USING (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app') WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
