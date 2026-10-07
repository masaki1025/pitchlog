-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:logout(uuid)

CREATE OR REPLACE FUNCTION authn.logout(p_token_id uuid)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
DECLARE
    previous_last_used_at timestamptz;
    logged_out_at timestamptz;
BEGIN
    SELECT token.last_used_at INTO previous_last_used_at
      FROM public.tenant_tokens AS token WHERE token.id = p_token_id FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    logged_out_at := pg_catalog.clock_timestamp();
    UPDATE public.tenant_tokens
       SET expires_at = greatest(logged_out_at, previous_last_used_at)
     WHERE id = p_token_id;
END;
$authn_function$;
ALTER FUNCTION authn.logout(uuid) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.logout(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authn.logout(uuid) TO pitchlog_app;
