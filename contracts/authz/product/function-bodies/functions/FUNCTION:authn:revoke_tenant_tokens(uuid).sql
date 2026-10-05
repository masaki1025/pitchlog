-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:revoke_tenant_tokens(uuid)

CREATE OR REPLACE FUNCTION authn.revoke_tenant_tokens(p_tenant_id uuid)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
DECLARE
    locked_subject_id uuid;
BEGIN
    SELECT credential.auth_subject_id INTO locked_subject_id
      FROM public.tenant_auth_subjects AS subject
      JOIN public.tenant_credentials AS credential
        ON credential.auth_subject_id = subject.id
     WHERE subject.tenant_id = p_tenant_id FOR UPDATE OF credential;
    IF locked_subject_id IS NULL THEN RETURN; END IF;
    UPDATE public.tenant_credentials
       SET generation = generation + 1
     WHERE auth_subject_id = locked_subject_id;
END;
$authn_function$;
ALTER FUNCTION authn.revoke_tenant_tokens(uuid) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.revoke_tenant_tokens(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authn.revoke_tenant_tokens(uuid) TO pitchlog_management_fn_owner;
