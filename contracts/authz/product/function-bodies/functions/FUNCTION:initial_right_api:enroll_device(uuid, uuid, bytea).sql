-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:enroll_device(uuid, uuid, bytea)

CREATE OR REPLACE FUNCTION initial_right_api.enroll_device(
    p_tenant_id uuid, p_device_id uuid, p_credential_digest bytea)
RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL OR p_device_id IS NULL
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')
          IS DISTINCT FROM p_tenant_id::text
       OR p_credential_digest IS NULL
       OR pg_catalog.octet_length(p_credential_digest) <> 32 THEN
        RAISE EXCEPTION 'initial enrollment subject or input rejected'
            USING ERRCODE='42501';
    END IF;
    INSERT INTO public.trusted_devices(tenant_id,device_id,credential_digest)
    VALUES (p_tenant_id,p_device_id,p_credential_digest);
    RETURN p_device_id;
END
$body$;
ALTER FUNCTION initial_right_api.enroll_device(uuid, uuid, bytea)
    OWNER TO pitchlog_initial_fn_owner;
REVOKE EXECUTE ON FUNCTION initial_right_api.enroll_device(uuid, uuid, bytea)
    FROM PUBLIC, pitchlog_app, pitchlog_initial_auth_verifier;
GRANT EXECUTE ON FUNCTION initial_right_api.enroll_device(uuid, uuid, bytea)
    TO pitchlog_initial_actor;
