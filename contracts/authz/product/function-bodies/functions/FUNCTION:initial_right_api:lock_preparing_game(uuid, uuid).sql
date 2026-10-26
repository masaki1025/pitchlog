-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:lock_preparing_game(uuid, uuid)
-- 未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。
CREATE OR REPLACE FUNCTION initial_right_api.lock_preparing_game(p_tenant_id uuid, p_game_id uuid)
RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE v_status text;
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') IS DISTINCT FROM p_tenant_id::text
       OR p_game_id IS NULL THEN
        RAISE EXCEPTION 'initial right subject or input rejected' USING ERRCODE='42501';
    END IF;
    SELECT g.status INTO v_status FROM public.games AS g
     WHERE g.tenant_id=p_tenant_id AND g.id=p_game_id FOR UPDATE;
    RETURN FOUND AND v_status = 'preparing';
EXCEPTION WHEN integrity_constraint_violation OR too_many_rows THEN
    -- 制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。
    RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.lock_preparing_game(uuid, uuid) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.lock_preparing_game(uuid, uuid) FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION initial_right_api.lock_preparing_game(uuid, uuid) TO pitchlog_initial_actor;
