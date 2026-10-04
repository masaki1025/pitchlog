-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:admin_vocabularies:global_read_only

CREATE POLICY pitchlog_app_global_read_only
    ON public.admin_vocabularies
    AS PERMISSIVE
    FOR SELECT
    TO pitchlog_app
    USING (
        true
    );
