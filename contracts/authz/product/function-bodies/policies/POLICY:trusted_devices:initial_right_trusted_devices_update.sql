-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:trusted_devices:initial_right_trusted_devices_update

CREATE POLICY initial_right_trusted_devices_update ON public.trusted_devices
AS PERMISSIVE FOR UPDATE TO pitchlog_initial_fn_owner
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE))
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
