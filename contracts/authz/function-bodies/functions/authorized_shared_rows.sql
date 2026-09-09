-- ELEMENT-TYPE: function
-- ELEMENT-ID: authorized_shared_rows

CREATE FUNCTION authz_private.authorized_shared_rows(
    p_group_id BIGINT,
    p_target_tenant_ids BIGINT[],
    p_granularity TEXT
)
RETURNS TABLE (
    tenant_id BIGINT,
    resource_kind TEXT,
    ownership_kind TEXT,
    payload JSONB
)
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, authz_private, pg_temp
BEGIN ATOMIC
    -- 認可行列を表の形で保持する。下段の常時 404 資源はこの表に行を持たず、
    -- grant_kind の値にかかわらず返却経路へ入れない。
    WITH authorization_matrix (
        requested_granularity,
        resource_kind,
        required_grant_kinds
    ) AS (
        VALUES
            (
                'team_statistics'::TEXT,
                'team_statistics'::TEXT,
                ARRAY['performance']::TEXT[]
            ),
            (
                'team_overview'::TEXT,
                'team_overview'::TEXT,
                ARRAY['performance']::TEXT[]
            ),
            (
                'player_individual'::TEXT,
                'player_individual'::TEXT,
                ARRAY['performance', 'player_individual']::TEXT[]
            ),
            (
                'team_statistics_export'::TEXT,
                'team_statistics'::TEXT,
                ARRAY['performance', 'export']::TEXT[]
            ),
            (
                'team_overview_export'::TEXT,
                'team_overview'::TEXT,
                ARRAY['performance', 'export']::TEXT[]
            ),
            (
                'player_individual_export'::TEXT,
                'player_individual'::TEXT,
                ARRAY['performance', 'player_individual', 'export']::TEXT[]
            )
    ),
    request_context AS (
        SELECT
            NULLIF(
                pg_catalog.current_setting('app.tenant_id', true),
                ''
            )::BIGINT AS requester_tenant_id,
            COALESCE(pg_catalog.cardinality(p_target_tenant_ids), 0)
                AS requested_target_count
    ),
    request_guard AS (
        SELECT
            request_context.requester_tenant_id,
            authorization_matrix.resource_kind,
            authorization_matrix.required_grant_kinds
        FROM request_context
        JOIN authorization_matrix
          ON
            -- DECISION: SHARED_RESOURCE_GRANULARITY_ALLOWED
            authorization_matrix.requested_granularity = p_granularity
        WHERE
            -- DECISION: SHARED_REQUESTER_CONTEXT_PRESENT
            request_context.requester_tenant_id IS NOT NULL
          AND
            -- DECISION: SHARED_TARGET_SET_NONEMPTY
            request_context.requested_target_count > 0
          AND
            -- DECISION: SHARED_COMPARISON_LIMIT
            -- 10 は要件書の「同時比較表示上限(既定 10)」= 付録 C の設定値。
            -- probe では設定表を持たないため既定値を直接置く。実製品では設定値から読む。
            request_context.requested_target_count <= 10
    ),
    requested_targets AS (
        SELECT requested_target.target_tenant_id
        FROM pg_catalog.unnest(p_target_tenant_ids)
            AS requested_target(target_tenant_id)
        WHERE
            -- DECISION: SHARED_TARGET_IDENTIFIER_PRESENT
            requested_target.target_tenant_id IS NOT NULL
    ),
    authorized_targets AS (
        SELECT
            requested_target.target_tenant_id,
            request_guard.resource_kind
        FROM requested_targets AS requested_target
        CROSS JOIN request_guard
        WHERE
            -- DECISION: SHARED_GROUP_EFFECTIVE
            EXISTS (
                SELECT 1
                FROM probe_data.probe_groups AS requested_group
                WHERE requested_group.group_id = p_group_id
                  AND requested_group.status = 'active'
            )
          AND
            -- DECISION: SHARED_REQUESTER_MEMBERSHIP_EFFECTIVE
            EXISTS (
                SELECT 1
                FROM probe_data.probe_memberships AS requester_membership
                WHERE requester_membership.group_id = p_group_id
                  AND requester_membership.tenant_id
                        = request_guard.requester_tenant_id
                  AND requester_membership.status = 'active'
            )
          AND
            -- DECISION: SHARED_TARGET_MEMBERSHIP_EFFECTIVE
            EXISTS (
                SELECT 1
                FROM probe_data.probe_memberships AS target_membership
                WHERE target_membership.group_id = p_group_id
                  AND target_membership.tenant_id
                        = requested_target.target_tenant_id
                  AND target_membership.status = 'active'
            )
          AND (
                -- DECISION: SHARED_SELF_TENANT_EXEMPTION
                requested_target.target_tenant_id
                    = request_guard.requester_tenant_id
                OR (
                    -- DECISION: SHARED_TARGET_GRANTS_COMPLETE
                    NOT EXISTS (
                        SELECT 1
                        FROM pg_catalog.unnest(
                            request_guard.required_grant_kinds
                        ) AS required_grant(grant_kind)
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM probe_data.probe_grants AS target_grant
                            WHERE target_grant.group_id = p_group_id
                              AND target_grant.tenant_id
                                    = requested_target.target_tenant_id
                              AND target_grant.grant_kind
                                    = required_grant.grant_kind
                              AND target_grant.enabled
                        )
                    )
                  AND
                    -- DECISION: SHARED_REQUESTER_GRANTS_COMPLETE
                    NOT EXISTS (
                        SELECT 1
                        FROM pg_catalog.unnest(
                            request_guard.required_grant_kinds
                        ) AS required_grant(grant_kind)
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM probe_data.probe_grants AS requester_grant
                            WHERE requester_grant.group_id = p_group_id
                              AND requester_grant.tenant_id
                                    = request_guard.requester_tenant_id
                              AND requester_grant.grant_kind
                                    = required_grant.grant_kind
                              AND requester_grant.enabled
                        )
                    )
                )
            )
    )
    SELECT
        business_row.tenant_id,
        business_row.resource_kind,
        business_row.ownership_kind,
        business_row.payload
    FROM authorized_targets AS authorized_target
    JOIN probe_data.probe_business_rows AS business_row
      ON business_row.tenant_id = authorized_target.target_tenant_id
     AND
        -- DECISION: SHARED_RESOURCE_KIND_ALLOWLIST
        business_row.resource_kind = authorized_target.resource_kind
    WHERE
        -- DECISION: SHARED_SELF_OWNED_RESOURCE
        business_row.ownership_kind = 'self';

    -- UNCHECKABLE-PRECONDITION: BOTH_TENANTS_ACTIVE
    -- 前提③「要求元と対象の両テナントが有効」は、凍結された probe の 6 表に
    -- tenant 表も tenant の有効性を示す列もないため、この probe では検査できない。
    -- dependency_table_ids 外の relation を追加せず、後続の実製品スキーマで検査する。
    -- STRUCTURAL-DENY: 常時 404 の生記録・カルテ所見・第三者データ・身体プロフィールは
    -- authorization_matrix に resource_kind の行を持たない。第三者データは加えて
    -- ownership_kind = 'self' により返却対象から構造的に除外する。
END;

ALTER FUNCTION authz_private.authorized_shared_rows(BIGINT, BIGINT[], TEXT)
    OWNER TO shared_fn_owner;
REVOKE ALL PRIVILEGES
    ON FUNCTION authz_private.authorized_shared_rows(BIGINT, BIGINT[], TEXT)
    FROM PUBLIC;
