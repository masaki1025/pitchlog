-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:analysis_groups:effective_group_control

CREATE POLICY pitchlog_app_effective_group_control
    ON public.analysis_groups
    AS PERMISSIVE
    FOR SELECT
    TO pitchlog_app
    USING (
        authz_private.tenant_has_effective_membership(id, false)
    );
