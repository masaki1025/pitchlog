-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:record_admin_login_failure(text)

CREATE OR REPLACE FUNCTION authn.record_admin_login_failure(p_scope_key text)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
DECLARE
    max_failures bigint;
    window_seconds bigint;
    lock_seconds bigint;
BEGIN
    max_failures := authn.setting_positive_integer('auth.admin_login.max_failures');
    window_seconds := authn.setting_positive_integer('auth.admin_login.window_seconds');
    lock_seconds := authn.setting_positive_integer('auth.admin_login.lock_seconds');
    IF max_failures IS NULL OR window_seconds IS NULL
       OR lock_seconds IS NULL THEN RETURN true; END IF;
    RETURN authn.record_failure('admin:' || coalesce(p_scope_key, ''),
                                window_seconds, max_failures,
                                lock_seconds, true);
END;
$authn_function$;
ALTER FUNCTION authn.record_admin_login_failure(text) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.record_admin_login_failure(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authn.record_admin_login_failure(text) TO pitchlog_management_fn_owner;
