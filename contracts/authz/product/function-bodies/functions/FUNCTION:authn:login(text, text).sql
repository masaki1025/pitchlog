-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:login(text, text)

CREATE OR REPLACE FUNCTION authn.login(p_team_name text, p_password text)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
DECLARE
    normalized_name text;
    tenant_id uuid;
    tenant_enabled boolean;
    subject_id uuid;
    password_hash text;
    hash_for_check text;
    credential_generation bigint;
    token_ttl bigint;
    max_failures bigint;
    window_seconds bigint;
    lock_seconds bigint;
    password_matches boolean;
    failure boolean;
    issued_at timestamptz;
    token_id uuid;
BEGIN
    normalized_name := public.authn_normalize_team_name(p_team_name);
    SELECT tenant.id, tenant.enabled, subject.id,
           credential.password_hash, credential.generation
      INTO tenant_id, tenant_enabled, subject_id,
           password_hash, credential_generation
    FROM public.tenants AS tenant
    LEFT JOIN public.tenant_auth_subjects AS subject
      ON subject.tenant_id = tenant.id
    LEFT JOIN public.tenant_credentials AS credential
      ON credential.auth_subject_id = subject.id
    WHERE tenant.name_normalized = normalized_name
      AND tenant.retired_at IS NULL;
    token_ttl := authn.setting_positive_integer('auth.token_ttl_seconds');
    max_failures := authn.setting_positive_integer('auth.team_login.max_failures');
    window_seconds := authn.setting_positive_integer('auth.team_login.window_seconds');
    lock_seconds := authn.setting_positive_integer('auth.team_login.lock_seconds');
    -- 無い名前・無効なテナント・誤ったパスワードも cost 12 を一度照合する。
    hash_for_check := CASE
        WHEN password_hash ~ '^\$2[aby]\$12\$[./A-Za-z0-9]{53}$'
        THEN password_hash
        ELSE '$2a$12$abcdefghijklmnopqrstuug/hOvRed88u/sCt2izp9NATk2M3qMx6'
    END;
    password_matches := coalesce(
        authn_crypto.crypt(coalesce(p_password, ''), hash_for_check)
        = password_hash, false);
    failure := tenant_id IS NULL OR tenant_enabled IS NOT TRUE
        OR subject_id IS NULL OR credential_generation IS NULL
        OR NOT password_matches OR token_ttl IS NULL
        OR max_failures IS NULL OR window_seconds IS NULL
        OR lock_seconds IS NULL;
    IF failure THEN
        -- 設定が欠けた場合も発行しない。計数可能なら同じ経路を通る。
        IF window_seconds IS NOT NULL AND max_failures IS NOT NULL
           AND lock_seconds IS NOT NULL THEN
            PERFORM authn.record_failure('team:' ||
                coalesce(normalized_name, ''), window_seconds,
                max_failures, lock_seconds, false);
        END IF;
        RETURN NULL;
    END IF;
    issued_at := pg_catalog.clock_timestamp();
    token_id := pg_catalog.gen_random_uuid();
    INSERT INTO public.tenant_tokens
        (id, tenant_id, auth_subject_id, credential_generation,
         expires_at, last_used_at)
    VALUES (token_id, tenant_id, subject_id, credential_generation,
            issued_at + token_ttl * INTERVAL '1 second', issued_at);
    RETURN token_id;
END;
$authn_function$;
ALTER FUNCTION authn.login(text, text) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.login(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authn.login(text, text) TO pitchlog_app;
