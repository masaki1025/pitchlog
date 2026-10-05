-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:record_failure(text, bigint, bigint, bigint, boolean)

CREATE OR REPLACE FUNCTION authn.record_failure(p_scope_key text, p_window_seconds bigint, p_max_failures bigint, p_lock_seconds bigint, p_apply_lock boolean)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
DECLARE
    event_time timestamptz;
    window_begin timestamptz;
    counter_id uuid;
    old_attempt_count bigint;
    old_locked_until timestamptz;
    next_attempt_count bigint;
    next_locked_until timestamptz;
BEGIN
    -- 同じ組を鍵・索引付き照会・更新で共用する。第1鍵は計数専用の名前空間。
    event_time := pg_catalog.clock_timestamp();
    window_begin := pg_catalog.to_timestamp(
        pg_catalog.floor(extract(epoch FROM event_time)
                         / p_window_seconds::numeric) * p_window_seconds
    );
    PERFORM pg_catalog.pg_advisory_xact_lock(
        87001223,
        pg_catalog.hashtext(p_scope_key || ':' ||
                            extract(epoch FROM window_begin)::text)
    );
    SELECT counter.id, counter.attempt_count, counter.locked_until
      INTO counter_id, old_attempt_count, old_locked_until
    FROM public.rate_limit_counters AS counter
    WHERE counter.scope_key = p_scope_key
      AND counter.window_start >= window_begin
      AND counter.window_start <= window_begin
    ORDER BY counter.id LIMIT 1 FOR UPDATE;
    next_attempt_count := coalesce(old_attempt_count, 0) + 1;
    next_locked_until := old_locked_until;
    IF p_apply_lock AND next_attempt_count >= p_max_failures THEN
        next_locked_until := event_time + p_lock_seconds * INTERVAL '1 second';
    END IF;
    IF counter_id IS NULL THEN
        INSERT INTO public.rate_limit_counters
            (id, scope_key, window_start, attempt_count, locked_until)
        VALUES (pg_catalog.gen_random_uuid(), p_scope_key, window_begin,
                next_attempt_count, next_locked_until);
    ELSE
        UPDATE public.rate_limit_counters
           SET attempt_count = next_attempt_count,
               locked_until = next_locked_until
         WHERE id = counter_id;
    END IF;
    RETURN p_apply_lock AND next_locked_until IS NOT NULL
           AND next_locked_until > event_time;
END;
$authn_function$;
ALTER FUNCTION authn.record_failure(text, bigint, bigint, bigint, boolean) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.record_failure(text, bigint, bigint, bigint, boolean) FROM PUBLIC;
