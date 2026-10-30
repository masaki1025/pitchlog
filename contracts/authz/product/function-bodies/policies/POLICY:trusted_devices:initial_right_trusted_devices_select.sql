-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:trusted_devices:initial_right_trusted_devices_select

CREATE POLICY initial_right_trusted_devices_select ON public.trusted_devices
AS PERMISSIVE FOR SELECT TO pitchlog_initial_fn_owner
USING (COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE));
