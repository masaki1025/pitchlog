-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:game_type_rule_defaults:global_read_only

CREATE POLICY pitchlog_app_global_read_only
    ON public.game_type_rule_defaults
    AS PERMISSIVE
    FOR SELECT
    TO pitchlog_app
    USING (
        true
    );
