-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:verify_token(uuid)

CREATE OR REPLACE FUNCTION authn.verify_token(
    p_token_id uuid, OUT tenant_id uuid, OUT expires_at timestamptz
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
DECLARE
    initial_subject_id uuid;
    current_generation bigint;
    token_tenant_id uuid;
    token_subject_id uuid;
    token_generation bigint;
    token_expires_at timestamptz;
    tenant_enabled boolean;
    tenant_retired_at timestamptz;
    subject_tenant_id uuid;
    token_ttl bigint;
    checked_at timestamptz;
BEGIN
    SELECT token.auth_subject_id INTO initial_subject_id
      FROM public.tenant_tokens AS token WHERE token.id = p_token_id;
    IF initial_subject_id IS NULL THEN RETURN; END IF;
    SELECT credential.generation INTO current_generation
      FROM public.tenant_credentials AS credential
     WHERE credential.auth_subject_id = initial_subject_id FOR SHARE;
    IF current_generation IS NULL THEN RETURN; END IF;
    SELECT token.tenant_id, token.auth_subject_id,
           token.credential_generation, token.expires_at,
           tenant.enabled, tenant.retired_at, subject.tenant_id
      INTO token_tenant_id, token_subject_id, token_generation,
           token_expires_at, tenant_enabled, tenant_retired_at,
           subject_tenant_id
      FROM public.tenant_tokens AS token
      LEFT JOIN public.tenants AS tenant ON tenant.id = token.tenant_id
      LEFT JOIN public.tenant_auth_subjects AS subject
        ON subject.id = token.auth_subject_id
     WHERE token.id = p_token_id FOR UPDATE OF token;
    checked_at := pg_catalog.clock_timestamp();
    token_ttl := authn.setting_positive_integer('auth.token_ttl_seconds');
    IF token_tenant_id IS NULL OR token_subject_id <> initial_subject_id
       OR subject_tenant_id IS DISTINCT FROM token_tenant_id
       OR token_generation <> current_generation
       OR tenant_enabled IS NOT TRUE OR tenant_retired_at IS NOT NULL
       OR token_expires_at <= checked_at OR token_ttl IS NULL THEN
        RETURN;
    END IF;
    tenant_id := token_tenant_id;
    expires_at := checked_at + token_ttl * INTERVAL '1 second';
    UPDATE public.tenant_tokens
       SET last_used_at = checked_at,
           expires_at = verify_token.expires_at
     WHERE id = p_token_id;
    RETURN;
END;
$authn_function$;
ALTER FUNCTION authn.verify_token(uuid) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.verify_token(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authn.verify_token(uuid) TO pitchlog_app;
