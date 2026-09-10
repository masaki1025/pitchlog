-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:probe_management_effects:tenant_boundary

CREATE POLICY tenant_boundary
    ON probe_data.probe_management_effects
    AS PERMISSIVE
    FOR ALL
    TO app_role
    USING (
        -- DECISION: RLS_PROBE_MANAGEMENT_EFFECTS_USING
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
        -- DECISION: RLS_PROBE_MANAGEMENT_EFFECTS_WITH_CHECK
        COALESCE(
            tenant_id
                = NULLIF(
                    pg_catalog.current_setting('app.tenant_id', true),
                    ''
                )::BIGINT,
            FALSE
        )
    );
