-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:tenants:self_tenant_row

CREATE POLICY pitchlog_app_self_tenant_row
    ON public.tenants
    AS PERMISSIVE
    FOR SELECT
    TO pitchlog_app
    USING (
        COALESCE(id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE)
    );
