-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:login_attempt(text, text, text)

CREATE OR REPLACE FUNCTION authn.login_attempt(
    p_team_name text, p_password text, p_source text,
    OUT token_id uuid, OUT wait_ms integer
)
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
    window_seconds bigint;
    throttle_threshold bigint;
    throttle_step_ms bigint;
    throttle_max_ms bigint;
    password_matches boolean;
    failure boolean;
    issued_at timestamptz;
    source_key text;
    event_time timestamptz;
    window_begin timestamptz;
    failure_count bigint;
    response_interval_ms bigint;
    old_allowed_at timestamptz;
    next_allowed_at timestamptz;
    counter_id uuid;
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
    window_seconds := authn.setting_positive_integer('auth.team_login.window_seconds');
    throttle_threshold := authn.setting_positive_integer('auth.team_login.throttle_threshold');
    throttle_step_ms := authn.setting_positive_integer('auth.team_login.throttle_step_ms');
    throttle_max_ms := authn.setting_positive_integer('auth.team_login.throttle_max_ms');
    -- max_failures と lock_seconds のキーは既存投入物に残し、このログイン経路では読まない。
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
        OR window_seconds IS NULL OR throttle_threshold IS NULL
        OR throttle_step_ms IS NULL OR throttle_max_ms IS NULL;
    IF NOT failure THEN
        issued_at := pg_catalog.clock_timestamp();
        token_id := pg_catalog.gen_random_uuid();
        INSERT INTO public.tenant_tokens
            (id, tenant_id, auth_subject_id, credential_generation,
             expires_at, last_used_at)
        VALUES (token_id, tenant_id, subject_id, credential_generation,
                issued_at + token_ttl * INTERVAL '1 second', issued_at);
        wait_ms := 0;
        RETURN;
    END IF;

    token_id := NULL;
    wait_ms := 0;
    IF window_seconds IS NULL OR throttle_threshold IS NULL
       OR throttle_step_ms IS NULL OR throttle_max_ms IS NULL THEN
        RETURN;
    END IF;

    -- 試行元はアプリが正規化して渡す。名前とウィンドウはロック鍵に含めない。
    source_key := 'src:' || coalesce(nullif(pg_catalog.lower(
        pg_catalog.btrim(p_source)), ''), 'unknown');
    PERFORM pg_catalog.pg_advisory_xact_lock(
        87001224, pg_catalog.hashtext(source_key)
    );
    event_time := pg_catalog.clock_timestamp();
    window_begin := pg_catalog.to_timestamp(
        pg_catalog.floor(extract(epoch FROM event_time)
                         / window_seconds::numeric) * window_seconds
    );
    SELECT coalesce(pg_catalog.sum(counter.attempt_count), 0),
           pg_catalog.max(counter.locked_until)
      INTO failure_count, old_allowed_at
    FROM public.rate_limit_counters AS counter
    WHERE counter.scope_key = source_key
      AND counter.window_start >= window_begin - window_seconds * INTERVAL '1 second'
      AND counter.window_start <= window_begin;
    IF failure_count <= throttle_threshold THEN
        response_interval_ms := 0;
    ELSIF failure_count <= throttle_threshold * 2 THEN
        response_interval_ms := throttle_step_ms;
    ELSIF failure_count <= throttle_threshold * 4 THEN
        response_interval_ms := throttle_step_ms * 2;
    ELSE
        response_interval_ms := throttle_step_ms * 4;
    END IF;
    wait_ms := LEAST(
        throttle_max_ms,
        GREATEST(
            0, pg_catalog.ceil(extract(epoch FROM
                (old_allowed_at - event_time)) * 1000)
        )
    )::integer;
    next_allowed_at := GREATEST(
        event_time, coalesce(old_allowed_at, event_time)
    ) + response_interval_ms * INTERVAL '1 millisecond';
    -- record_failure の locked_until は拒否用のロック期限であり、予約票とは意味が異なる。
    SELECT counter.id INTO counter_id
    FROM public.rate_limit_counters AS counter
    WHERE counter.scope_key = source_key
      AND counter.window_start = window_begin
    ORDER BY counter.id LIMIT 1 FOR UPDATE;
    IF counter_id IS NULL THEN
        INSERT INTO public.rate_limit_counters
            (id, scope_key, window_start, attempt_count, locked_until)
        VALUES (pg_catalog.gen_random_uuid(), source_key, window_begin,
                1, next_allowed_at);
    ELSE
        UPDATE public.rate_limit_counters
           SET attempt_count = attempt_count + 1,
               locked_until = next_allowed_at
         WHERE id = counter_id;
    END IF;
    RETURN;
END;
$authn_function$;
ALTER FUNCTION authn.login_attempt(text, text, text) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.login_attempt(text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authn.login_attempt(text, text, text) TO pitchlog_app;
