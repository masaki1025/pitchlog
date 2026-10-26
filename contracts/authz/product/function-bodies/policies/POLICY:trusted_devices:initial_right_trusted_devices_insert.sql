-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:trusted_devices:initial_right_trusted_devices_insert

CREATE POLICY initial_right_trusted_devices_insert ON public.trusted_devices
AS PERMISSIVE FOR INSERT TO pitchlog_initial_fn_owner
WITH CHECK (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
