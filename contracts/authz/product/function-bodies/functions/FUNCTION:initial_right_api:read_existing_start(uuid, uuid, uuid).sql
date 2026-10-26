-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:read_existing_start(uuid, uuid, uuid)
-- 未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。
CREATE OR REPLACE FUNCTION initial_right_api.read_existing_start(p_tenant_id uuid, p_game_id uuid, p_start_request_id uuid)
RETURNS TABLE(tenant_id uuid, game_id uuid, start_request_id uuid, device_id uuid, generation bigint, recovery_generation bigint, proof_digest bytea, key_id text, nonce bytea, ciphertext bytea)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE v_row record;
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') IS DISTINCT FROM p_tenant_id::text
       OR p_game_id IS NULL
       OR p_start_request_id IS NULL THEN
        RAISE EXCEPTION 'initial right subject or input rejected' USING ERRCODE='42501';
    END IF;
    BEGIN
        SELECT d.tenant_id, d.game_id, d.start_request_id, d.device_id,
           g.generation, g.recovery_generation, g.proof_digest,
           d.key_id, d.nonce, d.ciphertext
     INTO STRICT v_row
      FROM public.game_start_requests AS r
      JOIN public.recording_right_deliveries AS d
        ON (d.tenant_id,d.game_id,d.start_request_id,d.device_id) =
           (r.tenant_id,r.game_id,r.start_request_id,r.device_id)
      JOIN public.recording_generations AS g
        ON (g.tenant_id,g.game_id,g.generation) = (d.tenant_id,d.game_id,d.generation)
     WHERE r.tenant_id = p_tenant_id AND r.game_id = p_game_id
       AND r.start_request_id = p_start_request_id
       AND g.kind = 'normal' AND g.revoked_at IS NULL AND d.revoked_at IS NULL
       AND g.holder_device = d.device_id::text
       AND g.proof_digest IS NOT NULL AND pg_catalog.octet_length(g.proof_digest) = 32
       AND g.recovery_generation > 0
       AND EXISTS (SELECT 1 FROM public.rg1_restore_gate AS e
                    WHERE e.singleton_id = 1 AND e.recovery_generation = g.recovery_generation)
     LIMIT 2;
    EXCEPTION WHEN no_data_found THEN RETURN;
    END;
    RETURN QUERY SELECT v_row.tenant_id, v_row.game_id, v_row.start_request_id, v_row.device_id, v_row.generation, v_row.recovery_generation, v_row.proof_digest, v_row.key_id, v_row.nonce, v_row.ciphertext;
EXCEPTION WHEN integrity_constraint_violation OR too_many_rows THEN
    -- 制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。
    RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.read_existing_start(uuid, uuid, uuid) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.read_existing_start(uuid, uuid, uuid) FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION initial_right_api.read_existing_start(uuid, uuid, uuid) TO pitchlog_initial_actor;
