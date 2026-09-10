-- ELEMENT-TYPE: function
-- ELEMENT-ID: read_control_resources

CREATE FUNCTION authz_private.read_control_resources(
    p_group_id BIGINT,
    p_control_kind TEXT,
    p_limit INTEGER DEFAULT 100,
    p_offset BIGINT DEFAULT 0
)
RETURNS TABLE (
    control_kind TEXT,
    group_id BIGINT,
    tenant_id BIGINT,
    status TEXT,
    qualifier TEXT,
    enabled BOOLEAN
)
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, authz_private, pg_temp
BEGIN ATOMIC
    -- member が読める情報と admin 限定情報を別の要求種別・別の SELECT に分ける。
    WITH control_access_matrix (control_kind, admin_required) AS (
        VALUES
            ('group'::TEXT, FALSE),
            ('member_names'::TEXT, FALSE),
            ('membership_admin_details'::TEXT, TRUE),
            ('grant'::TEXT, FALSE),
            ('invitation'::TEXT, TRUE)
    ),
    request_context AS (
        SELECT NULLIF(
            pg_catalog.current_setting('app.tenant_id', true),
            ''
        )::BIGINT AS requester_tenant_id
    ),
    request_access AS (
        SELECT
            p_group_id AS group_id,
            control_access_matrix.control_kind,
            request_context.requester_tenant_id
        FROM request_context
        JOIN control_access_matrix
          ON
            -- DECISION: CONTROL_RESOURCE_KIND_ALLOWED
            control_access_matrix.control_kind = p_control_kind
        WHERE
            -- DECISION: CONTROL_REQUESTER_CONTEXT_PRESENT
            request_context.requester_tenant_id IS NOT NULL
          AND
            -- DECISION: CONTROL_GROUP_EFFECTIVE
            EXISTS (
                SELECT 1
                FROM probe_data.probe_groups AS requested_group
                WHERE requested_group.group_id = p_group_id
                  AND requested_group.status = 'active'
            )
          AND
            -- DECISION: CONTROL_REQUESTER_MEMBERSHIP_EFFECTIVE
            EXISTS (
                SELECT 1
                FROM probe_data.probe_memberships AS requester_membership
                WHERE requester_membership.group_id = p_group_id
                  AND requester_membership.tenant_id
                        = request_context.requester_tenant_id
                  AND requester_membership.status = 'active'
            )
          AND
            -- DECISION: CONTROL_ADMIN_ONLY_ACCESS
            (
                NOT control_access_matrix.admin_required
                OR EXISTS (
                    SELECT 1
                    FROM probe_data.probe_memberships AS admin_membership
                    WHERE admin_membership.group_id = p_group_id
                      AND admin_membership.tenant_id
                            = request_context.requester_tenant_id
                      AND admin_membership.status = 'active'
                      AND admin_membership.group_role = 'admin'
                )
            )
    ),
    authorized_control_rows AS (
        SELECT
            'group'::TEXT AS control_kind,
            controlled_group.group_id,
            NULL::BIGINT AS tenant_id,
            controlled_group.status,
            NULL::TEXT AS qualifier,
            NULL::BOOLEAN AS enabled
        FROM request_access
        JOIN probe_data.probe_groups AS controlled_group
          -- DECISION: CONTROL_GROUP_ROW_GROUP_MATCH
          ON controlled_group.group_id = request_access.group_id
        WHERE request_access.control_kind = 'group'

        UNION ALL

        -- member 向けの一覧は tenant_id だけを返し、status と role を経路から外す。
        SELECT
            'member_names'::TEXT,
            controlled_membership.group_id,
            controlled_membership.tenant_id,
            NULL::TEXT,
            NULL::TEXT,
            NULL::BOOLEAN
        FROM request_access
        JOIN probe_data.probe_memberships AS controlled_membership
          -- DECISION: CONTROL_MEMBER_ROW_GROUP_MATCH
          ON controlled_membership.group_id = request_access.group_id
        WHERE request_access.control_kind = 'member_names'
          AND
            -- DECISION: CONTROL_MEMBER_LIST_ACTIVE_ROW
            controlled_membership.status = 'active'

        UNION ALL

        -- 参加状態と役割を返す SELECT は admin_required の行からしか到達できない。
        SELECT
            'membership_admin_details'::TEXT,
            controlled_membership.group_id,
            controlled_membership.tenant_id,
            controlled_membership.status,
            controlled_membership.group_role,
            NULL::BOOLEAN
        FROM request_access
        JOIN probe_data.probe_memberships AS controlled_membership
          -- DECISION: CONTROL_ADMIN_MEMBER_ROW_GROUP_MATCH
          ON controlled_membership.group_id = request_access.group_id
        WHERE request_access.control_kind = 'membership_admin_details'
          AND
            -- DECISION: CONTROL_ADMIN_MEMBER_ACTIVE_ROW
            controlled_membership.status = 'active'

        UNION ALL

        SELECT
            'grant'::TEXT,
            controlled_grant.group_id,
            controlled_grant.tenant_id,
            NULL::TEXT,
            controlled_grant.grant_kind,
            controlled_grant.enabled
        FROM request_access
        JOIN probe_data.probe_grants AS controlled_grant
          -- DECISION: CONTROL_GRANT_ROW_GROUP_MATCH
          ON controlled_grant.group_id = request_access.group_id
        WHERE request_access.control_kind = 'grant'
          AND
            -- DECISION: CONTROL_GRANT_TARGET_MEMBERSHIP_EFFECTIVE
            EXISTS (
                SELECT 1
                FROM probe_data.probe_memberships AS target_membership
                WHERE target_membership.group_id = controlled_grant.group_id
                  AND target_membership.tenant_id = controlled_grant.tenant_id
                  AND target_membership.status = 'active'
            )

        UNION ALL

        -- invitation は control_access_matrix の admin_required 行だけが到達できる。
        SELECT
            'invitation'::TEXT,
            controlled_invitation.group_id,
            controlled_invitation.invited_tenant_id,
            controlled_invitation.status,
            NULL::TEXT,
            NULL::BOOLEAN
        FROM request_access
        JOIN probe_data.probe_invitations AS controlled_invitation
          -- DECISION: CONTROL_INVITATION_ROW_GROUP_MATCH
          ON controlled_invitation.group_id = request_access.group_id
        WHERE request_access.control_kind = 'invitation'
    )
    SELECT
        authorized_row.control_kind,
        authorized_row.group_id,
        authorized_row.tenant_id,
        authorized_row.status,
        authorized_row.qualifier,
        authorized_row.enabled
    FROM authorized_control_rows AS authorized_row
    ORDER BY
        authorized_row.control_kind,
        authorized_row.group_id,
        authorized_row.tenant_id NULLS FIRST,
        authorized_row.qualifier NULLS FIRST
    OFFSET GREATEST(COALESCE(p_offset, 0), 0)
    LIMIT LEAST(GREATEST(COALESCE(p_limit, 100), 1), 100);
END;

ALTER FUNCTION authz_private.read_control_resources(
    BIGINT,
    TEXT,
    INTEGER,
    BIGINT
)
    OWNER TO shared_fn_owner;
REVOKE ALL PRIVILEGES
    ON FUNCTION authz_private.read_control_resources(
        BIGINT,
        TEXT,
        INTEGER,
        BIGINT
    )
    FROM PUBLIC;
