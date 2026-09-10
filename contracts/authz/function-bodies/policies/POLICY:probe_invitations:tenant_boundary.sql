-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:probe_invitations:tenant_boundary

CREATE POLICY tenant_boundary
    ON probe_data.probe_invitations
    AS PERMISSIVE
    FOR ALL
    TO app_role
    USING (
        -- DECISION: RLS_PROBE_INVITATIONS_USING
        COALESCE(
            invited_tenant_id
                = NULLIF(
                    pg_catalog.current_setting('app.tenant_id', true),
                    ''
                )::BIGINT,
            FALSE
        )
    )
    WITH CHECK (
        -- DECISION: RLS_PROBE_INVITATIONS_WITH_CHECK
        COALESCE(
            invited_tenant_id
                = NULLIF(
                    pg_catalog.current_setting('app.tenant_id', true),
                    ''
                )::BIGINT,
            FALSE
        )
    );
