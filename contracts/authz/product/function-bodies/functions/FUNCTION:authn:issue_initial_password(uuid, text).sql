-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:authn:issue_initial_password(uuid, text)

CREATE OR REPLACE FUNCTION authn.issue_initial_password(p_tenant_id uuid, p_password text)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $authn_function$
DECLARE
    new_subject_id uuid;
BEGIN
    IF authn.password_policy_ok(p_password) IS NOT TRUE THEN RETURN; END IF;
    IF NOT EXISTS (SELECT 1 FROM public.tenants AS tenant
                    WHERE tenant.id = p_tenant_id
                      AND tenant.retired_at IS NULL) THEN RETURN; END IF;
    new_subject_id := pg_catalog.gen_random_uuid();
    INSERT INTO public.tenant_auth_subjects (id, tenant_id)
    VALUES (new_subject_id, p_tenant_id);
    INSERT INTO public.tenant_credentials
        (auth_subject_id, password_hash, generation,
         password_changed_at)
    VALUES (new_subject_id,
            authn_crypto.crypt(p_password, authn_crypto.gen_salt('bf', 12)),
            1, pg_catalog.clock_timestamp());
END;
$authn_function$;
ALTER FUNCTION authn.issue_initial_password(uuid, text) OWNER TO pitchlog_auth_fn_owner;
REVOKE ALL PRIVILEGES ON FUNCTION authn.issue_initial_password(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authn.issue_initial_password(uuid, text) TO pitchlog_management_fn_owner;
