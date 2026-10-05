-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:change_password(uuid, text, text)

CREATE OR REPLACE FUNCTION authn.change_password(p_token_id uuid, p_current_password text, p_new_password text)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
DECLARE
    initial_subject_id uuid;
    current_generation bigint;
    current_hash text;
    token_tenant_id uuid;
    token_subject_id uuid;
    token_generation bigint;
    token_expires_at timestamptz;
    tenant_enabled boolean;
    tenant_retired_at timestamptz;
    subject_tenant_id uuid;
    checked_at timestamptz;
BEGIN
    SELECT token.auth_subject_id INTO initial_subject_id
      FROM public.tenant_tokens AS token WHERE token.id = p_token_id;
    IF initial_subject_id IS NULL THEN RETURN false; END IF;
    SELECT credential.generation, credential.password_hash
      INTO current_generation, current_hash
      FROM public.tenant_credentials AS credential
     WHERE credential.auth_subject_id = initial_subject_id FOR UPDATE;
    IF current_generation IS NULL THEN RETURN false; END IF;
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
     WHERE token.id = p_token_id FOR SHARE OF token;
    checked_at := pg_catalog.clock_timestamp();
    IF token_tenant_id IS NULL OR token_subject_id <> initial_subject_id
       OR subject_tenant_id IS DISTINCT FROM token_tenant_id
       OR token_generation <> current_generation
       OR tenant_enabled IS NOT TRUE OR tenant_retired_at IS NOT NULL
       OR token_expires_at <= checked_at
       OR authn.setting_positive_integer('auth.token_ttl_seconds') IS NULL THEN
        RETURN false;
    END IF;
    IF authn_crypto.crypt(coalesce(p_current_password, ''),
                         current_hash) <> current_hash
       OR NOT authn.password_policy_ok(p_new_password) THEN
        RETURN false;
    END IF;
    UPDATE public.tenant_credentials
       SET password_hash = authn_crypto.crypt(p_new_password,
                                               authn_crypto.gen_salt('bf', 12)),
           generation = generation + 1, password_changed_at = checked_at
     WHERE auth_subject_id = initial_subject_id;
    RETURN true;
END;
$authn_function$;
ALTER FUNCTION authn.change_password(uuid, text, text) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.change_password(uuid, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authn.change_password(uuid, text, text) TO pitchlog_app;
