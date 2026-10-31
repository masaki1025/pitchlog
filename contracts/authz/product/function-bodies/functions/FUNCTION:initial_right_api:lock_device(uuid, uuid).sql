-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:lock_device(uuid, uuid)
-- 未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。
CREATE OR REPLACE FUNCTION initial_right_api.lock_device(p_tenant_id uuid, p_device_id uuid)
RETURNS TABLE(credential_digest bytea, revoked_at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE v_row record;
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') IS DISTINCT FROM p_tenant_id::text
       OR p_device_id IS NULL THEN
        RAISE EXCEPTION 'initial right subject or input rejected' USING ERRCODE='42501';
    END IF;
    BEGIN
        SELECT d.credential_digest, d.revoked_at INTO STRICT v_row
          FROM public.trusted_devices AS d
         WHERE d.tenant_id=p_tenant_id AND d.device_id=p_device_id
         LIMIT 2 FOR SHARE;
    EXCEPTION WHEN no_data_found THEN RETURN;
    END;
    RETURN QUERY SELECT v_row.credential_digest, v_row.revoked_at;
EXCEPTION WHEN integrity_constraint_violation OR too_many_rows THEN
    -- 制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。
    RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.lock_device(uuid, uuid) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.lock_device(uuid, uuid) FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION initial_right_api.lock_device(uuid, uuid) TO pitchlog_initial_actor;
