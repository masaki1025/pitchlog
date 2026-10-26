-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:lock_current_start(uuid, uuid, uuid)
-- 未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。
CREATE OR REPLACE FUNCTION initial_right_api.lock_current_start(p_tenant_id uuid, p_game_id uuid, p_start_request_id uuid)
RETURNS TABLE(tenant_id uuid, game_id uuid, start_request_id uuid, device_id uuid, generation bigint, recovery_generation bigint, proof_digest bytea, key_id text, nonce bytea, ciphertext bytea)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE v_status text; v_generation bigint; v_delivery record;
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') IS DISTINCT FROM p_tenant_id::text
       OR p_game_id IS NULL
       OR p_start_request_id IS NULL THEN
        RAISE EXCEPTION 'initial right subject or input rejected' USING ERRCODE='42501';
    END IF;
    -- 呼出側のdevice→request→attempt排他に続け、JOIN一括lockを使わない。
    SELECT g.status INTO v_status FROM public.games AS g
     WHERE g.tenant_id=p_tenant_id AND g.id=p_game_id FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    BEGIN
        SELECT g.generation INTO STRICT v_generation FROM public.recording_generations AS g
         WHERE g.tenant_id=p_tenant_id AND g.game_id=p_game_id
           AND g.kind='normal' AND g.revoked_at IS NULL LIMIT 2 FOR UPDATE;
    EXCEPTION WHEN no_data_found THEN RETURN;
    END;
    SELECT d.start_request_id, d.device_id, d.revoked_at INTO v_delivery
      FROM public.recording_right_deliveries AS d
     WHERE d.tenant_id=p_tenant_id AND d.game_id=p_game_id AND d.generation=v_generation
     FOR UPDATE;
    IF NOT FOUND OR v_delivery.start_request_id IS DISTINCT FROM p_start_request_id
     OR v_delivery.revoked_at IS NOT NULL THEN RETURN; END IF;
    RETURN QUERY SELECT r.tenant_id,r.game_id,r.start_request_id,r.device_id,r.generation,
        r.recovery_generation,r.proof_digest,r.key_id,r.nonce,r.ciphertext
     FROM initial_right_api.read_existing_start(p_tenant_id,p_game_id,p_start_request_id) AS r;
EXCEPTION WHEN integrity_constraint_violation OR too_many_rows THEN
    -- 制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。
    RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.lock_current_start(uuid, uuid, uuid) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.lock_current_start(uuid, uuid, uuid) FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION initial_right_api.lock_current_start(uuid, uuid, uuid) TO pitchlog_initial_actor;
