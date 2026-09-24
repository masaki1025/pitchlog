-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:sharing_grants:effective_group_control

CREATE POLICY pitchlog_app_effective_group_control
    ON public.sharing_grants
    AS PERMISSIVE
    FOR SELECT
    TO pitchlog_app
    USING (
        EXISTS (SELECT 1 FROM public.group_memberships AS membership WHERE membership.id = sharing_grants.membership_id AND authz_private.tenant_has_effective_membership(membership.group_id, false))
    );
