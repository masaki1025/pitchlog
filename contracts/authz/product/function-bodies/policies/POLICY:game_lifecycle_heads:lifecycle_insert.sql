-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:game_lifecycle_heads:lifecycle_insert

CREATE POLICY lifecycle_insert ON sync_fence.game_lifecycle_heads AS PERMISSIVE FOR INSERT TO pitchlog_sync_right_fn_owner WITH CHECK (tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid AND session_user = 'pitchlog_app' AND EXISTS(SELECT 1 FROM sync_fence.lifecycle_write_admissions a WHERE a.tenant_id=game_lifecycle_heads.tenant_id AND a.game_id=game_lifecycle_heads.game_id AND a.state='consumed' AND a.transaction_id=pg_catalog.pg_current_xact_id()::text));
