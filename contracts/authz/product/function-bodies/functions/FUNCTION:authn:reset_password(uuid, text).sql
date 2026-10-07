-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:reset_password(uuid, text)

CREATE OR REPLACE FUNCTION authn.reset_password(p_tenant_id uuid, p_new_password text)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
DECLARE
    locked_subject_id uuid;
BEGIN
    IF authn.password_policy_ok(p_new_password) IS NOT TRUE THEN RETURN; END IF;
    SELECT credential.auth_subject_id INTO locked_subject_id
      FROM public.tenant_auth_subjects AS subject
      JOIN public.tenant_credentials AS credential
        ON credential.auth_subject_id = subject.id
     WHERE subject.tenant_id = p_tenant_id FOR UPDATE OF credential;
    IF locked_subject_id IS NULL THEN RETURN; END IF;
    UPDATE public.tenant_credentials
       SET password_hash = authn_crypto.crypt(p_new_password,
                                               authn_crypto.gen_salt('bf', 12)),
           generation = generation + 1,
           password_changed_at = pg_catalog.clock_timestamp()
     WHERE auth_subject_id = locked_subject_id;
END;
$authn_function$;
ALTER FUNCTION authn.reset_password(uuid, text) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.reset_password(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authn.reset_password(uuid, text) TO pitchlog_management_fn_owner;
