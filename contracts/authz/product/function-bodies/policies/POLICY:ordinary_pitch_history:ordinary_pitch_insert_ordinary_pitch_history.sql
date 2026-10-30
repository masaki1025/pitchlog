-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:ordinary_pitch_history:ordinary_pitch_insert_ordinary_pitch_history

CREATE POLICY ordinary_pitch_insert_ordinary_pitch_history ON sync_fence.ordinary_pitch_history FOR INSERT TO pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
