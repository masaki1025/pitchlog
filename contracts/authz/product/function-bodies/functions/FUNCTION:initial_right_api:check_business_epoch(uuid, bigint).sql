-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:check_business_epoch(uuid, bigint)
-- 未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。
CREATE OR REPLACE FUNCTION initial_right_api.check_business_epoch(p_tenant_id uuid, p_recovery_generation bigint)
RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE v_epoch bigint;
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') IS DISTINCT FROM p_tenant_id::text
       OR p_recovery_generation IS NULL
       OR p_recovery_generation<=0 THEN
        RAISE EXCEPTION 'initial right subject or input rejected' USING ERRCODE='42501';
    END IF;
    SELECT e.recovery_generation INTO v_epoch FROM public.rg1_restore_gate AS e
     WHERE e.singleton_id=1;
    RETURN FOUND AND p_recovery_generation>0 AND v_epoch IS NOT NULL AND v_epoch=p_recovery_generation;
EXCEPTION WHEN integrity_constraint_violation OR too_many_rows THEN
    -- 制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。
    RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.check_business_epoch(uuid, bigint) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.check_business_epoch(uuid, bigint) FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION initial_right_api.check_business_epoch(uuid, bigint) TO pitchlog_initial_actor;
