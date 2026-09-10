-- ELEMENT-TYPE: function
-- ELEMENT-ID: apply_representative_grant_change

CREATE FUNCTION management_private.apply_representative_grant_change(
    p_group_id BIGINT,
    p_tenant_id BIGINT,
    p_effect_kind TEXT
)
RETURNS TABLE (
    applied BOOLEAN,
    group_id BIGINT,
    tenant_id BIGINT,
    effect_kind TEXT
)
LANGUAGE SQL
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, management_private, pg_temp
BEGIN ATOMIC
    WITH request_context AS (
        SELECT NULLIF(
            pg_catalog.current_setting('app.tenant_id', true),
            ''
        )::BIGINT AS requester_tenant_id
    ),
    authorized_target AS (
        SELECT 1 AS authorization_token
        FROM probe_data.probe_memberships AS caller_membership
        JOIN probe_data.probe_grants AS target_grant
          -- DECISION: MANAGEMENT_TARGET_GRANT_GROUP_MATCH
          ON target_grant.group_id = caller_membership.group_id
        CROSS JOIN request_context
        WHERE
            -- DECISION: MANAGEMENT_REQUESTER_CONTEXT_PRESENT
            request_context.requester_tenant_id IS NOT NULL
            AND
            -- DECISION: MANAGEMENT_GROUP_SCOPE
            caller_membership.group_id = p_group_id
            AND
            -- DECISION: MANAGEMENT_REQUESTER_MEMBERSHIP_EFFECTIVE
            caller_membership.tenant_id
                = request_context.requester_tenant_id
            AND caller_membership.status = 'active'
            AND
            -- DECISION: MANAGEMENT_ADMIN_ROLE_REQUIRED
            caller_membership.group_role = 'admin'
            AND
            -- DECISION: MANAGEMENT_TARGET_GRANT_SCOPE
            target_grant.tenant_id = p_tenant_id
            AND
            -- DECISION: MANAGEMENT_EFFECT_KIND_MATCH
            target_grant.grant_kind = p_effect_kind
            AND
            -- DECISION: MANAGEMENT_TARGET_GRANT_ENABLED
            target_grant.enabled
        LIMIT 1
    ),
    applied_effect AS (
        INSERT INTO probe_data.probe_management_effects (
            group_id,
            tenant_id,
            effect_kind
        )
        SELECT p_group_id, p_tenant_id, p_effect_kind
        FROM authorized_target
        RETURNING TRUE AS applied
    )
    SELECT
        applied_effect.applied,
        p_group_id,
        p_tenant_id,
        p_effect_kind
    FROM applied_effect;

    -- UNCHECKABLE-PRECONDITION: MANAGEMENT_TENANTS_ACTIVE
    -- 凍結された probe の 6 表に tenant 表も有効性の列もないため、要求元と対象の
    -- tenant 有効性はこの関数では検査できない。資産外 relation は追加しない。
END;

ALTER FUNCTION management_private.apply_representative_grant_change(
    BIGINT,
    BIGINT,
    TEXT
)
    OWNER TO management_fn_owner;
REVOKE ALL PRIVILEGES
    ON FUNCTION management_private.apply_representative_grant_change(
        BIGINT,
        BIGINT,
        TEXT
    )
    FROM PUBLIC;
