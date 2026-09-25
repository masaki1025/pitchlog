-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:group_memberships:effective_group_control

CREATE POLICY pitchlog_app_effective_group_control
    ON public.group_memberships
    AS PERMISSIVE
    FOR SELECT
    TO pitchlog_app
    USING (
        authz_private.tenant_has_effective_membership(group_id, false)
    );
