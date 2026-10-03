-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:system_settings:global_read_only

CREATE POLICY pitchlog_app_global_read_only
    ON public.system_settings
    AS PERMISSIVE
    FOR SELECT
    TO pitchlog_app
    USING (
        true
    );
