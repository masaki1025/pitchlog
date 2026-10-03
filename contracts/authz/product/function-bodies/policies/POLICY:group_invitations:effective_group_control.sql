-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:group_invitations:effective_group_control

CREATE POLICY pitchlog_app_effective_group_control
    ON public.group_invitations
    AS PERMISSIVE
    FOR SELECT
    TO pitchlog_app
    USING (
        authz_private.tenant_has_effective_membership(group_id, true)
    );
