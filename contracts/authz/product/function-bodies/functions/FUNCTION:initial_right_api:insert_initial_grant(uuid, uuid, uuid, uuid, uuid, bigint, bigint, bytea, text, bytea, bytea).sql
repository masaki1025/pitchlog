-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:insert_initial_grant(uuid, uuid, uuid, uuid, uuid, bigint, bigint, bytea, text, bytea, bytea)
-- 未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。
CREATE OR REPLACE FUNCTION initial_right_api.insert_initial_grant(p_tenant_id uuid, p_game_id uuid, p_start_request_id uuid, p_device_id uuid, p_attempt_id uuid, p_generation bigint, p_recovery_generation bigint, p_proof_digest bytea, p_key_id text, p_nonce bytea, p_ciphertext bytea)
RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE v_request record; v_outcome text; v_status text; v_epoch bigint; v_count bigint;
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') IS DISTINCT FROM p_tenant_id::text
       OR p_game_id IS NULL
       OR p_start_request_id IS NULL
       OR p_device_id IS NULL
       OR p_attempt_id IS NULL
       OR p_generation IS NULL
       OR p_recovery_generation IS NULL
       OR p_proof_digest IS NULL
       OR p_key_id IS NULL
       OR p_nonce IS NULL
       OR p_ciphertext IS NULL
       OR p_generation<=0
       OR p_recovery_generation<=0
       OR pg_catalog.octet_length(p_proof_digest)<>32
       OR p_key_id=''
       OR pg_catalog.octet_length(p_nonce)<>12
       OR pg_catalog.octet_length(p_ciphertext)<>48 THEN
        RAISE EXCEPTION 'initial right subject or input rejected' USING ERRCODE='42501';
    END IF;
    -- 固定brokerだけが既issuerの実claim結果を渡す。引数を認証proofとは扱わない。
    -- 同Session既取得lockを、device→request→attempt→gameの順で再確認する。
    PERFORM d.device_id FROM public.trusted_devices AS d
     WHERE d.tenant_id=p_tenant_id AND d.device_id=p_device_id AND d.revoked_at IS NULL FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
    SELECT r.device_id INTO v_request FROM public.game_start_requests AS r
     WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id AND r.start_request_id=p_start_request_id
     FOR UPDATE;
    IF NOT FOUND OR v_request.device_id IS DISTINCT FROM p_device_id THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
    SELECT a.outcome INTO v_outcome FROM public.game_start_attempts AS a
     WHERE a.tenant_id=p_tenant_id AND a.attempt_id=p_attempt_id AND a.game_id=p_game_id
       AND a.start_request_id=p_start_request_id AND a.device_id=p_device_id FOR UPDATE;
    IF NOT FOUND OR v_outcome IS DISTINCT FROM 'pending' THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
    SELECT g.status INTO v_status FROM public.games AS g
     WHERE g.tenant_id=p_tenant_id AND g.id=p_game_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
    -- preparing検証は既lock_preparing_game。後続start hookのstatus変更をここで上書きしない。
    IF EXISTS (SELECT 1 FROM public.recording_generations AS g
     WHERE g.tenant_id=p_tenant_id AND g.game_id=p_game_id) THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
    SELECT e.recovery_generation INTO v_epoch FROM public.rg1_restore_gate AS e WHERE e.singleton_id=1;
    IF NOT FOUND OR v_epoch IS NULL OR v_epoch IS DISTINCT FROM p_recovery_generation THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
    INSERT INTO public.recording_generations
     (tenant_id,game_id,generation,kind,issuance_order,holder_device,confirmed_watermark,
      applied_prefix,proof_digest,recovery_generation)
     VALUES (p_tenant_id,p_game_id,p_generation,'normal',1,p_device_id::text,0,0,
             p_proof_digest,p_recovery_generation);
    INSERT INTO public.recording_right_deliveries
     (tenant_id,game_id,generation,start_request_id,device_id,key_id,nonce,ciphertext)
     VALUES (p_tenant_id,p_game_id,p_generation,p_start_request_id,p_device_id,p_key_id,p_nonce,p_ciphertext);
    UPDATE public.game_start_attempts AS a SET outcome='committed',resolved_at=CURRENT_TIMESTAMP
     WHERE a.tenant_id=p_tenant_id AND a.attempt_id=p_attempt_id AND a.game_id=p_game_id
       AND a.start_request_id=p_start_request_id AND a.device_id=p_device_id AND a.outcome='pending';
    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count<>1 THEN RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE = '23514'; END IF;
    RETURN true;
EXCEPTION WHEN integrity_constraint_violation OR too_many_rows THEN
    -- 制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。
    RAISE EXCEPTION 'initial right operation rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.insert_initial_grant(uuid, uuid, uuid, uuid, uuid, bigint, bigint, bytea, text, bytea, bytea) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.insert_initial_grant(uuid, uuid, uuid, uuid, uuid, bigint, bigint, bytea, text, bytea, bytea) FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION initial_right_api.insert_initial_grant(uuid, uuid, uuid, uuid, uuid, bigint, bigint, bytea, text, bytea, bytea) TO pitchlog_initial_actor;
