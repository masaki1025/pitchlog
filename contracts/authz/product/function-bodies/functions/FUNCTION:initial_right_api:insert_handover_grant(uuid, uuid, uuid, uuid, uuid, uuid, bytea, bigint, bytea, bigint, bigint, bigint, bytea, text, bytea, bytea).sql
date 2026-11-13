-- ELEMENT-TYPE: function
-- ELEMENT-ID: FUNCTION:initial_right_api:insert_handover_grant(uuid, uuid, uuid, uuid, uuid, uuid, bytea, bigint, bytea, bigint, bigint, bigint, bytea, text, bytea, bytea)
-- 通常引き継ぎの旧世代失効と新世代発行を同一取引に閉じる。未適用候補。
CREATE OR REPLACE FUNCTION initial_right_api.insert_handover_grant(p_tenant_id uuid, p_game_id uuid, p_start_request_id uuid, p_device_id uuid, p_attempt_id uuid, p_from_device_id uuid, p_from_credential_digest bytea, p_from_generation bigint, p_from_proof_digest bytea, p_last_d1 bigint, p_generation bigint, p_recovery_generation bigint, p_proof_digest bytea, p_key_id text, p_nonce bytea, p_ciphertext bytea)
RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE
    v_current record;
    v_request record;
    v_outcome text;
    v_status text;
    v_epoch bigint;
    v_count bigint;
    v_order bigint;
    v_revoked bigint;
    v_constraint text;
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') IS DISTINCT FROM p_tenant_id::text
       OR p_game_id IS NULL
       OR p_start_request_id IS NULL
       OR p_device_id IS NULL
       OR p_attempt_id IS NULL
       OR p_from_device_id IS NULL
       OR p_from_credential_digest IS NULL
       OR pg_catalog.octet_length(p_from_credential_digest)<>32
       OR p_from_generation IS NULL
       OR p_from_generation<=0
       OR p_from_proof_digest IS NULL
       OR pg_catalog.octet_length(p_from_proof_digest)<>32
       OR p_last_d1 IS NULL
       OR p_last_d1<0
       OR p_generation IS NULL
       OR p_generation<=0
       OR p_generation=p_from_generation
       OR p_recovery_generation IS NULL
       OR p_recovery_generation<=0
       OR p_proof_digest IS NULL
       OR pg_catalog.octet_length(p_proof_digest)<>32
       OR p_key_id IS NULL
       OR p_key_id=''
       OR p_nonce IS NULL
       OR pg_catalog.octet_length(p_nonce)<>12
       OR p_ciphertext IS NULL
       OR pg_catalog.octet_length(p_ciphertext)<>48 THEN
        RAISE EXCEPTION 'handover right subject or input rejected' USING ERRCODE='42501';
    END IF;
    -- 旧保持端末の資格を同一取引で再確認する。
    PERFORM d.device_id
      FROM public.trusted_devices AS d
     WHERE d.tenant_id=p_tenant_id
       AND d.device_id=p_from_device_id
       AND d.revoked_at IS NULL
       AND d.credential_digest=p_from_credential_digest
     FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'handover right operation rejected: from_device' USING ERRCODE='P0001';
    END IF;
    -- 新保持端末の実在を確認する。
    PERFORM d.device_id
      FROM public.trusted_devices AS d
     WHERE d.tenant_id=p_tenant_id
       AND d.device_id=p_device_id
       AND d.revoked_at IS NULL
     FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'handover right operation rejected: to_device' USING ERRCODE='P0001';
    END IF;
    -- 既存の開始要求/試行を挿入順に再確認する。
    SELECT r.device_id
      INTO v_request
      FROM public.game_start_requests AS r
     WHERE r.tenant_id=p_tenant_id
       AND r.game_id=p_game_id
       AND r.start_request_id=p_start_request_id
     FOR UPDATE;
    IF NOT FOUND OR v_request.device_id IS DISTINCT FROM p_device_id THEN
        RAISE EXCEPTION 'handover right operation rejected: request' USING ERRCODE='P0001';
    END IF;
    SELECT a.outcome
      INTO v_outcome
      FROM public.game_start_attempts AS a
     WHERE a.tenant_id=p_tenant_id
       AND a.attempt_id=p_attempt_id
       AND a.game_id=p_game_id
       AND a.start_request_id=p_start_request_id
       AND a.device_id=p_device_id
     FOR UPDATE;
    IF NOT FOUND OR v_outcome IS DISTINCT FROM 'pending' THEN
        RAISE EXCEPTION 'handover right operation rejected: attempt' USING ERRCODE='P0001';
    END IF;
    -- 試合行→現世代行の順で lock する。
    SELECT g.status
      INTO v_status
      FROM public.games AS g
     WHERE g.tenant_id=p_tenant_id AND g.id=p_game_id
     FOR UPDATE;
    IF NOT FOUND OR v_status IS DISTINCT FROM 'in_progress' THEN
        RAISE EXCEPTION 'handover right operation rejected: game' USING ERRCODE='P0001';
    END IF;
    SELECT e.recovery_generation
      INTO v_epoch
      FROM public.rg1_restore_gate AS e
     WHERE e.singleton_id=1;
    IF NOT FOUND OR v_epoch IS NULL OR v_epoch IS DISTINCT FROM p_recovery_generation THEN
        RAISE EXCEPTION 'handover right operation rejected: epoch' USING ERRCODE='P0001';
    END IF;
    SELECT r.generation, r.kind, r.holder_device, r.confirmed_watermark,
           r.applied_prefix, r.proof_digest, r.recovery_generation,
           r.revoked_at, r.retired_at
      INTO v_current
      FROM public.recording_generations AS r
     WHERE r.tenant_id=p_tenant_id
       AND r.game_id=p_game_id
       AND r.kind='normal'
       AND r.revoked_at IS NULL
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'handover right operation rejected: current_missing' USING ERRCODE='P0001';
    END IF;
    -- 保持端末・世代・確定水位(D3)の照合。追いついていなければ成立しない。
    IF v_current.generation IS DISTINCT FROM p_from_generation
       OR v_current.holder_device IS DISTINCT FROM p_from_device_id::text
       OR v_current.proof_digest IS DISTINCT FROM p_from_proof_digest
       OR v_current.recovery_generation IS DISTINCT FROM p_recovery_generation
       OR v_current.retired_at IS NOT NULL
       OR v_current.confirmed_watermark < p_last_d1
       OR v_current.applied_prefix < p_last_d1 THEN
        RAISE EXCEPTION 'handover right operation rejected: current_mismatch' USING ERRCODE='P0001';
    END IF;
    -- 試合行 lock の下で発行順を単調に進める。D4 値順には依存しない。
    SELECT COALESCE(MAX(r.issuance_order),0)+1
      INTO v_order
      FROM public.recording_generations AS r
     WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id;
    IF v_order IS NULL OR v_order<=0 THEN
        RAISE EXCEPTION 'handover right operation rejected: order' USING ERRCODE='P0001';
    END IF;
    -- 現世代の部分一意を満たすため、旧世代を先に失効させる。
    UPDATE public.recording_generations AS r
       SET revoked_at=CURRENT_TIMESTAMP
     WHERE r.tenant_id=p_tenant_id
       AND r.game_id=p_game_id
       AND r.generation=p_from_generation
       AND r.revoked_at IS NULL;
    GET DIAGNOSTICS v_revoked = ROW_COUNT;
    IF v_revoked<>1 THEN
        RAISE EXCEPTION 'handover right operation rejected: revoke' USING ERRCODE='P0001';
    END IF;
    INSERT INTO public.recording_generations
        (tenant_id,game_id,generation,kind,issuance_order,holder_device,
         confirmed_watermark,applied_prefix,proof_digest,recovery_generation)
    VALUES
        (p_tenant_id,p_game_id,p_generation,'normal',v_order,p_device_id::text,
         0,0,p_proof_digest,p_recovery_generation);
    INSERT INTO public.recording_right_deliveries
        (tenant_id,game_id,generation,start_request_id,device_id,key_id,nonce,ciphertext)
    VALUES
        (p_tenant_id,p_game_id,p_generation,p_start_request_id,p_device_id,
         p_key_id,p_nonce,p_ciphertext);
    UPDATE public.game_start_attempts AS a
       SET outcome='committed',resolved_at=CURRENT_TIMESTAMP
     WHERE a.tenant_id=p_tenant_id
       AND a.attempt_id=p_attempt_id
       AND a.game_id=p_game_id
       AND a.start_request_id=p_start_request_id
       AND a.device_id=p_device_id
       AND a.outcome='pending';
    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count<>1 THEN
        RAISE EXCEPTION 'handover right operation rejected: attempt_commit' USING ERRCODE='P0001';
    END IF;
    RETURN true;
EXCEPTION WHEN integrity_constraint_violation OR too_many_rows THEN
    -- 制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。
    GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
    RAISE EXCEPTION 'handover right operation rejected: constraint %',
        COALESCE(v_constraint,'') USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.insert_handover_grant(uuid, uuid, uuid, uuid, uuid, uuid, bytea, bigint, bytea, bigint, bigint, bigint, bytea, text, bytea, bytea) OWNER TO pitchlog_initial_fn_owner;
REVOKE ALL ON FUNCTION initial_right_api.insert_handover_grant(uuid, uuid, uuid, uuid, uuid, uuid, bytea, bigint, bytea, bigint, bigint, bigint, bytea, text, bytea, bytea) FROM PUBLIC, pitchlog_app;
GRANT EXECUTE ON FUNCTION initial_right_api.insert_handover_grant(uuid, uuid, uuid, uuid, uuid, uuid, bytea, bigint, bytea, bigint, bigint, bigint, bytea, text, bytea, bytea) TO pitchlog_initial_actor;
