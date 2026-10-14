-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:observe_rate_limit_counters()

CREATE OR REPLACE FUNCTION authn.observe_rate_limit_counters(
    OUT out_of_window_rows bigint, OUT distinct_scope_keys bigint
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
DECLARE
    window_seconds bigint;
    window_begin timestamptz;
BEGIN
    window_seconds := authn.setting_positive_integer('auth.team_login.window_seconds');
    IF window_seconds IS NULL THEN
        RAISE EXCEPTION 'ログインの監視設定が不正です' USING ERRCODE = '22023';
    END IF;
    window_begin := pg_catalog.to_timestamp(
        pg_catalog.floor(extract(epoch FROM pg_catalog.clock_timestamp())
                         / window_seconds::numeric) * window_seconds
    );

    -- 累積量は src:・team:・admin: を含む表全体で数える。鍵の前置きでは絞らない。
    -- 索引の先頭列でまとめ、索引にある scope_key と window_start だけを読む。
    SELECT coalesce(pg_catalog.sum(scopes.outside_count), 0),
           pg_catalog.count(*)
      INTO out_of_window_rows, distinct_scope_keys
    FROM (
        SELECT counter.scope_key,
               pg_catalog.count(*) FILTER (
                   WHERE counter.window_start <> window_begin
               ) AS outside_count
        FROM public.rate_limit_counters AS counter
        GROUP BY counter.scope_key
    ) AS scopes;
END;
$authn_function$;
ALTER FUNCTION authn.observe_rate_limit_counters() OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.observe_rate_limit_counters() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authn.observe_rate_limit_counters() TO pitchlog_management_fn_owner;
