-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:medical_note_versions:tenant_owned

CREATE POLICY pitchlog_app_tenant_owned
    ON public.medical_note_versions
    AS PERMISSIVE
    FOR ALL
    TO pitchlog_app
    USING (
        COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE)
    )
    WITH CHECK (
        COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE)
    );
