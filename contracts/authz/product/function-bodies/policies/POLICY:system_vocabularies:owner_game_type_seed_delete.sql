-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:system_vocabularies:owner_game_type_seed_delete

CREATE POLICY pitchlog_owner_game_type_seed_delete
    ON public.system_vocabularies
    AS PERMISSIVE
    FOR DELETE
    TO pitchlog_owner
    USING (
        category = 'game_type' AND key = ANY (ARRAY['game_official', 'game_semi_official', 'game_open', 'game_intrasquad', 'game_other'])
    );
