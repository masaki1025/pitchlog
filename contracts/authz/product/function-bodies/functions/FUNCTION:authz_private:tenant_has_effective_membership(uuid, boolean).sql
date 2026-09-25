-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authz_private:tenant_has_effective_membership(uuid, boolean)

CREATE OR REPLACE FUNCTION authz_private.tenant_has_effective_membership(
    p_group_id uuid,
    p_require_admin boolean
)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
    SELECT COALESCE(
        (
            SELECT true
            FROM public.analysis_groups AS effective_group
            JOIN public.group_memberships AS membership
                ON membership.group_id = effective_group.id
            JOIN public.tenants AS member_tenant
                ON member_tenant.id = membership.tenant_id
            WHERE effective_group.id = p_group_id
              AND effective_group.status = 'active'
              AND membership.status = 'active'
              AND member_tenant.enabled
              AND membership.tenant_id = NULLIF(
                  pg_catalog.current_setting('app.tenant_id', true),
                  ''
              )::uuid
              AND (NOT p_require_admin OR membership.role = 'admin')
            LIMIT 1
        ),
        false
    );
$function$;
ALTER FUNCTION authz_private.tenant_has_effective_membership(uuid, boolean)
    OWNER TO pitchlog_shared_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authz_private.tenant_has_effective_membership(uuid, boolean)
    FROM PUBLIC, pitchlog_app;
REVOKE ALL PRIVILEGES ON TABLE public.tenants, public.analysis_groups, public.group_memberships
    FROM pitchlog_shared_fn_owner;
REVOKE SELECT (id, name, enabled, disabled_at, import_batch_id)
    ON TABLE public.tenants FROM pitchlog_shared_fn_owner;
REVOKE SELECT (id, status, terminated_at, termination_reason)
    ON TABLE public.analysis_groups FROM pitchlog_shared_fn_owner;
REVOKE SELECT (id, group_id, tenant_id, role, status, joined_at, left_at)
    ON TABLE public.group_memberships FROM pitchlog_shared_fn_owner;
