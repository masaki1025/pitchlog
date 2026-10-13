-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:system_vocabularies:owner_game_type_seed_insert

CREATE POLICY pitchlog_owner_game_type_seed_insert
    ON public.system_vocabularies
    AS PERMISSIVE
    FOR INSERT
    TO pitchlog_owner
    WITH CHECK (
        category = 'game_type' AND disabled IS FALSE AND ((key = 'game_official' AND display_name = '公式戦') OR (key = 'game_semi_official' AND display_name = '準公式戦') OR (key = 'game_open' AND display_name = 'オープン戦') OR (key = 'game_intrasquad' AND display_name = '紅白戦') OR (key = 'game_other' AND display_name = 'その他'))
    );
