-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:probe_grants:tenant_boundary

CREATE POLICY tenant_boundary
    ON probe_data.probe_grants
    AS PERMISSIVE
    FOR ALL
    TO app_role
    USING (
        -- DECISION: RLS_PROBE_GRANTS_USING
        COALESCE(
            tenant_id
                = NULLIF(
                    pg_catalog.current_setting('app.tenant_id', true),
                    ''
                )::BIGINT,
            FALSE
        )
    )
    WITH CHECK (
        -- DECISION: RLS_PROBE_GRANTS_WITH_CHECK
        COALESCE(
            tenant_id
                = NULLIF(
                    pg_catalog.current_setting('app.tenant_id', true),
                    ''
                )::BIGINT,
            FALSE
        )
    );
