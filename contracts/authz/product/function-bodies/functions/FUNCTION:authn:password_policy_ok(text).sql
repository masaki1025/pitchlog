-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:password_policy_ok(text)

CREATE OR REPLACE FUNCTION authn.password_policy_ok(p_password text)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
BEGIN
    RETURN p_password IS NOT NULL
       AND pg_catalog.char_length(p_password) >= 8
       AND p_password ~ '[A-Za-z]'
       AND p_password ~ '[0-9]';
END;
$authn_function$;
ALTER FUNCTION authn.password_policy_ok(text) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.password_policy_ok(text) FROM PUBLIC;
