-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:probe_groups:tenant_boundary

CREATE POLICY tenant_boundary
    ON probe_data.probe_groups
    AS PERMISSIVE
    FOR ALL
    TO app_role
    USING (
        -- DECISION: RLS_PROBE_GROUPS_USING
        EXISTS (
            SELECT 1
            FROM probe_data.probe_memberships AS membership
            WHERE membership.group_id = probe_groups.group_id
              AND membership.tenant_id
                    = NULLIF(
                        pg_catalog.current_setting('app.tenant_id', true),
                        ''
                    )::BIGINT
              AND membership.status = 'active'
        )
    )
    WITH CHECK (
        -- DECISION: RLS_PROBE_GROUPS_WITH_CHECK
        EXISTS (
            SELECT 1
            FROM probe_data.probe_memberships AS membership
            WHERE membership.group_id = probe_groups.group_id
              AND membership.tenant_id
                    = NULLIF(
                        pg_catalog.current_setting('app.tenant_id', true),
                        ''
                    )::BIGINT
              AND membership.status = 'active'
        )
    );
