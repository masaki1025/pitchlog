-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:public:resolve_stage_a_rule(uuid, text, text, boolean)

-- 実DB identityは固定実行器がscope UUIDを先頭に注入する4引数。
DO $authz$
DECLARE
    v_proc oid := pg_catalog.to_regprocedure(
        'public.resolve_stage_a_rule(uuid,text,text,boolean)'
    );
BEGIN
    IF v_proc IS NOT NULL AND EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p
        WHERE p.oid = v_proc
          AND (
              p.proowner <> 'pitchlog_rule_resolution_fn_owner'::regrole
              OR EXISTS (
                  SELECT 1
                  FROM pg_catalog.aclexplode(
                      COALESCE(p.proacl, pg_catalog.acldefault('f', p.proowner))
                  ) a
                  WHERE a.grantee NOT IN (
                      p.proowner, 'pitchlog_app'::regrole
                  ) OR a.privilege_type <> 'EXECUTE'
                    OR (a.grantee = 'pitchlog_app'::regrole AND a.is_grantable)
              )
              OR NOT pg_catalog.has_function_privilege(
                  'pitchlog_app', p.oid, 'EXECUTE'
              )
          )
    ) THEN
        RAISE EXCEPTION 'rule resolver function collision';
    END IF;
END;
$authz$;

CREATE OR REPLACE FUNCTION public.resolve_stage_a_rule(
    p_tenant_id uuid,
    p_game_type_key text,
    p_tournament_key text,
    p_has_override boolean
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    v_guc_text text;
    v_guc_tenant_id uuid;
    v_parent_key text;
    v_expected_rule_id uuid;
    v_rule_id uuid;
    v_rule public.rule_sets%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
        RETURN pg_catalog.jsonb_build_object('status', 'outcome_unconfirmed');
    END IF;
    v_guc_text := NULLIF(
        pg_catalog.current_setting('app.tenant_id', true), ''
    );
    IF v_guc_text IS NULL OR p_tenant_id IS NULL THEN
        RETURN pg_catalog.jsonb_build_object('status', 'rule_not_available');
    END IF;
    BEGIN
        v_guc_tenant_id := v_guc_text::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        RETURN pg_catalog.jsonb_build_object('status', 'rule_not_available');
    END;
    IF v_guc_tenant_id <> p_tenant_id THEN
        RETURN pg_catalog.jsonb_build_object('status', 'rule_not_available');
    END IF;
    IF p_game_type_key IS NULL OR p_game_type_key = ''
       OR p_tournament_key IS NULL OR p_tournament_key = ''
       OR p_has_override IS NULL THEN
        RETURN pg_catalog.jsonb_build_object('status', 'rule_not_available');
    END IF;
    IF p_has_override THEN
        RETURN pg_catalog.jsonb_build_object('status', 'stage_a_unsupported');
    END IF;

    SELECT vocabulary.key INTO v_parent_key
    FROM public.tenant_vocabularies AS vocabulary
    WHERE vocabulary.tenant_id = p_tenant_id
      AND vocabulary.key = p_tournament_key
      AND vocabulary.category = 'tournament'
      AND vocabulary.disabled = false
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('status', 'rule_not_available');
    END IF;
    -- 親ロック待機後の別SQL文で新しいREAD COMMITTED snapshotを読む。
    IF EXISTS (
        SELECT 1 FROM public.tournament_rule_assignments AS assignment
        WHERE assignment.tenant_id = p_tenant_id
          AND assignment.tournament_key = p_tournament_key
    ) THEN
        RETURN pg_catalog.jsonb_build_object('status', 'stage_a_unsupported');
    END IF;

    v_expected_rule_id := CASE p_game_type_key
        WHEN 'game_official' THEN 'ca626b2e-8751-530e-a431-9ef5c00f7d95'::uuid
        WHEN 'game_semi_official' THEN '8fa3b9b7-481b-538b-8093-6af96050d97f'::uuid
        WHEN 'game_open' THEN 'b679f9f1-86a8-54f7-9466-a5b01d932953'::uuid
        WHEN 'game_intrasquad' THEN '45677369-9e25-5220-9a30-1d89b338174c'::uuid
        WHEN 'game_other' THEN '6ff51660-bee2-552a-9075-1f3f3d1e0dd7'::uuid
        ELSE NULL
    END;
    IF v_expected_rule_id IS NULL THEN
        RETURN pg_catalog.jsonb_build_object('status', 'rule_not_available');
    END IF;
    SELECT defaults.rule_set_id INTO v_rule_id
    FROM public.game_type_rule_defaults AS defaults
    WHERE defaults.game_type_key = p_game_type_key
      AND defaults.game_type_category = 'game_type'
    FOR SHARE;
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('status', 'rule_not_available');
    END IF;
    IF v_rule_id IS DISTINCT FROM v_expected_rule_id THEN
        RETURN pg_catalog.jsonb_build_object('status', 'invalid_rule');
    END IF;
    SELECT rules.* INTO v_rule
    FROM public.rule_sets AS rules
    WHERE rules.id = v_rule_id
    FOR SHARE;
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('status', 'rule_not_available');
    END IF;
    IF v_rule.regulation_innings IS DISTINCT FROM 9
       OR v_rule.uses_dh IS DISTINCT FROM true
       OR (
           p_game_type_key = 'game_official'
           AND (
               v_rule.called_game_conditions IS DISTINCT FROM '[]'::jsonb
               OR v_rule.extra_innings_limit IS DISTINCT FROM 12
               OR v_rule.tiebreak_rule IS DISTINCT FROM
                  '{"startInning":10,"runnerPlacement":"no_out_first_second","leadoffRule":"continue_lineup"}'::jsonb
           )
       )
       OR (
           p_game_type_key IN (
               'game_semi_official', 'game_open', 'game_intrasquad'
           )
           AND (
               v_rule.called_game_conditions IS DISTINCT FROM
                  '[{"pointDifference":10,"startInning":5},{"pointDifference":7,"startInning":7}]'::jsonb
               OR v_rule.extra_innings_limit IS DISTINCT FROM 9
               OR v_rule.tiebreak_rule IS NOT NULL
           )
       )
       OR (
           p_game_type_key = 'game_other'
           AND (
               v_rule.called_game_conditions IS DISTINCT FROM '[]'::jsonb
               OR v_rule.extra_innings_limit IS DISTINCT FROM 9
               OR v_rule.tiebreak_rule IS NOT NULL
           )
       ) THEN
        RETURN pg_catalog.jsonb_build_object('status', 'invalid_rule');
    END IF;


    -- この戻りは出所候補であり、相関・未裁定設定の保存前拒否は既存codecが行う。
    RETURN pg_catalog.jsonb_build_object(
        'status', 'resolved',
        'rule', pg_catalog.jsonb_build_object(
            'ruleSetId', v_rule.id::text,
            'regulationInnings', v_rule.regulation_innings,
            'coldConditions', v_rule.called_game_conditions,
            'extensionLimit', v_rule.extra_innings_limit,
            'tiebreak', v_rule.tiebreak_rule,
            'dh', v_rule.uses_dh
        )
    );
EXCEPTION WHEN OTHERS THEN
    RETURN pg_catalog.jsonb_build_object('status', 'outcome_unconfirmed');
END;
$function$;

ALTER FUNCTION public.resolve_stage_a_rule(uuid, text, text, boolean)
    OWNER TO pitchlog_rule_resolution_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION public.resolve_stage_a_rule(uuid, text, text, boolean)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.resolve_stage_a_rule(uuid, text, text, boolean)
    TO pitchlog_app;
