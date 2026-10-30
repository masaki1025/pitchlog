-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:ordinary_pitch_write_admissions:ordinary_pitch_insert_ordinary_pitch_write_admissions

CREATE POLICY ordinary_pitch_insert_ordinary_pitch_write_admissions ON sync_fence.ordinary_pitch_write_admissions FOR INSERT TO pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app');
