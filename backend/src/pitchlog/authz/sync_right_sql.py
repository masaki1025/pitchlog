"""初球検証の固定SQL候補を描画する。適用・runtime登録は行わない。"""

_OWNER = "pitchlog_sync_right_fn_owner"
_COMMON = (
    "p_tenant_id uuid,p_attempt_id uuid,p_phase_id uuid,"
    "p_binding_nonce bytea,p_device_id uuid,p_game_id uuid"
)
_ASSERT = """
IF session_user <> 'pitchlog_app' OR current_user <> 'pitchlog_sync_right_fn_owner'
 OR p_tenant_id IS NULL OR p_tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR p_attempt_id IS NULL OR p_phase_id IS NULL OR p_device_id IS NULL
 OR p_game_id IS NULL OR p_binding_nonce IS NULL
 OR pg_catalog.octet_length(p_binding_nonce) <> 32 THEN
 RAISE EXCEPTION 'sync writer binding rejected' USING ERRCODE='42501';
END IF;
-- 実関数未供給なら例外で閉じる。callerのnonceだけでは成功しない。
PERFORM sync_fence_api.assert_writer_binding(p_tenant_id,p_attempt_id,
 p_phase_id,p_binding_nonce,p_device_id,p_game_id);
"""
_BIND_HEAD = """
IF p_credential_digest IS NULL OR
 pg_catalog.octet_length(p_credential_digest) <> 32 THEN
 RAISE EXCEPTION 'sync credential input rejected' USING ERRCODE='42501';
END IF;
SELECT d.credential_digest,d.revoked_at INTO stored_digest,revoked
 FROM public.trusted_devices d
 WHERE d.tenant_id=p_tenant_id AND d.device_id=p_device_id FOR SHARE;
"""
_BIND_MATCH = """COALESCE(FOUND AND revoked IS NULL AND
 stored_digest=p_credential_digest,false)"""
_RIGHT_HEAD = """
IF p_internal_generation IS NULL OR p_internal_generation <= 0 OR
 p_recovery_generation IS NULL OR p_recovery_generation <= 0 OR
 p_proof_digest IS NULL OR pg_catalog.octet_length(p_proof_digest) <> 32 THEN
 RAISE EXCEPTION 'sync right input rejected' USING ERRCODE='42501';
END IF;
SELECT g.recovery_generation,g.state INTO STRICT current_epoch,gate_state
 FROM public.rg1_restore_gate g WHERE g.singleton_id=1;
IF current_epoch IS NULL OR gate_state <> 'open' THEN
 RAISE EXCEPTION 'sync recovery unavailable' USING ERRCODE='55000';
END IF;
"""
_RIGHT_EXISTS = """EXISTS (
 SELECT 1 FROM public.recording_generations r WHERE r.tenant_id=p_tenant_id
 AND r.game_id=p_game_id AND r.generation=p_internal_generation AND r.kind='normal'
 AND r.holder_device=p_device_id::text AND r.revoked_at IS NULL
 AND r.retired_at IS NULL AND r.recovery_generation=current_epoch
 AND r.proof_digest=p_proof_digest)"""
_BIND_DECL = "stored_digest bytea; revoked timestamptz;"
_RIGHT_DECL = "current_epoch bigint; gate_state text;"
_FUNCTIONS = (
    (
        "bind_device",
        "uuid,uuid,uuid,bytea,uuid,uuid,bytea",
        _COMMON + ",p_credential_digest bytea",
        "device_matches boolean",
        _BIND_DECL,
        _BIND_HEAD + f"RETURN QUERY SELECT {_BIND_MATCH};\n",
    ),
    (
        "check_current_right",
        "uuid,uuid,uuid,bytea,uuid,uuid,bigint,bigint,bytea",
        _COMMON
        + (
            ",p_internal_generation bigint,p_recovery_generation bigint,"
            "p_proof_digest bytea"
        ),
        "recovery_matches boolean,right_matches boolean",
        _RIGHT_DECL,
        _RIGHT_HEAD
        + """IF current_epoch <> p_recovery_generation THEN
 RETURN QUERY SELECT false,false;
 RETURN;
END IF;
-- game→generation lockは既prefix核が保持。本関数で先取りしない。
RETURN QUERY SELECT true,"""
        + _RIGHT_EXISTS
        + ";\n",
    ),
)


def render_sync_right_sql() -> str:
    """未供給の制御照合ABIを参照するexact2 SQL/列ACL候補を返す。"""
    chunks = [
        f"""-- U1未登録候補。U2/正式受理前の適用禁止。
CREATE ROLE {_OWNER} NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT
 NOCREATEROLE NOCREATEDB NOREPLICATION;
CREATE SCHEMA sync_right_api AUTHORIZATION {_OWNER};
REVOKE ALL ON SCHEMA sync_right_api FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO {_OWNER};
GRANT USAGE ON SCHEMA sync_right_api TO pitchlog_app;
GRANT SELECT (tenant_id,device_id,credential_digest,revoked_at),UPDATE (revoked_at)
 ON TABLE public.trusted_devices TO {_OWNER};
GRANT SELECT (tenant_id,game_id,generation,kind,holder_device,revoked_at,
 retired_at,proof_digest,recovery_generation)
 ON TABLE public.recording_generations TO {_OWNER};
GRANT SELECT (singleton_id,state,recovery_generation)
 ON TABLE public.rg1_restore_gate TO {_OWNER};
"""
    ]
    for table in ("trusted_devices", "recording_generations"):
        chunks.append(f"""ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY;
CREATE POLICY sync_first_ball_select ON public.{table} FOR SELECT TO {_OWNER}
 USING (tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
""")
    chunks.append(f"""CREATE POLICY sync_first_ball_device_lock
 ON public.trusted_devices
 FOR UPDATE TO {_OWNER}
 USING (tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK (tenant_id=NULLIF(
 pg_catalog.current_setting('app.tenant_id',true),'')::uuid);
""")
    chunks.append(f"""CREATE POLICY sync_first_ball_gate ON public.rg1_restore_gate
 FOR SELECT TO {_OWNER} USING (singleton_id=1);
-- U2実関数が未供給なら権限適用もできない。
GRANT USAGE ON SCHEMA sync_fence_api TO {_OWNER};
GRANT EXECUTE ON FUNCTION sync_fence_api.assert_writer_binding(
 uuid,uuid,uuid,bytea,uuid,uuid) TO {_OWNER};
""")
    for name, signature, args, results, declarations, body in _FUNCTIONS:
        identity = f"sync_right_api.{name}({signature})"
        chunks.append(f"""CREATE FUNCTION sync_right_api.{name}({args})
RETURNS TABLE ({results}) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog,pg_temp AS $function$
DECLARE {declarations}
BEGIN
{_ASSERT}{body}END;
$function$;
ALTER FUNCTION {identity} OWNER TO {_OWNER};
REVOKE ALL ON FUNCTION {identity} FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {identity} TO pitchlog_app;
""")
    return "\n".join(chunks)


# ---- 書込印(sync_fence.first_ball_write_admissions)を発行する2 body ----
# 既存のbind_device/check_current_rightの実成功と同じ関数呼び出しの中でだけ印を書く。
# 状態やboolを入力に受ける関数は作らない。上の共有断片(_BIND_HEAD等)から生成し、
# 既存のrender_sync_right_sql()の出力は変えない。

_STAMP_COLS = (
    "tenant_id,attempt_id,phase_id,authority_id,control_instance,business_instance,"
    "restore_epoch,control_version,issuer,lease_id,device_id,game_id,wire_d4,"
    "internal_generation,recovery_generation,codec_version,request_fingerprint,d5,"
    "event_fingerprint,system_identifier,database_oid,postmaster_started_at,"
    "backend_pid,backend_start,transaction_id,nonce_digest,expires_at"
)
_STAMP_B_COLS = ",".join("b." + c for c in _STAMP_COLS.split(","))
_STAMP_KEY = "(p_tenant_id,p_attempt_id,p_phase_id)"
_STAMP_REJECT = "RAISE EXCEPTION 'first ball stamp rejected' USING ERRCODE='42501';"
_STAMP_DECL = " own_xid text; stamp_state text; row_xmin text;"

# 前状態がinvalid/consumedなら据え置く(終端)。それ以外で成立しない事象はinvalid。
_STAMP_BIND_INSERT = "CASE WHEN matches THEN 'device_verified' ELSE 'invalid' END"
_STAMP_BIND_UPDATE = """CASE
  WHEN s.state='device_verified' AND matches THEN 'device_verified'
  WHEN s.state IN ('invalid','consumed') THEN s.state
  ELSE 'invalid' END"""
_STAMP_RIGHT_INSERT = "'invalid'"
_STAMP_RIGHT_UPDATE = """CASE
  WHEN s.state IN ('device_verified','right_verified') AND recovery_ok AND right_ok
   AND s.internal_generation=p_internal_generation
   AND s.recovery_generation=p_recovery_generation THEN 'right_verified'
  WHEN s.state IN ('invalid','consumed') THEN s.state
  ELSE 'invalid' END"""


def _stamp_write(insert_state: str, update_state: str) -> str:
    """印の行を読み(FOR UPDATE)、無ければINSERT、有ればUPDATEし、毎回xminを照合する。

    書込とxminのtop-level照合はEXCEPTION節を持つblockの外に置く。EXCEPTION節の中で
    書くとxminがsubxidになり、照合が常に失敗する。

    Args:
        insert_state: 行が無いときに入れるstateの式。
        update_state: 行があるときに設定するstateの式(sは印の行)。

    Returns:
        関数本文へ差し込むplpgsql断片。
    """
    return f"""own_xid := pg_catalog.pg_current_xact_id()::text;
SELECT s.state INTO stamp_state FROM sync_fence.first_ball_write_admissions s
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)={_STAMP_KEY} FOR UPDATE;
IF NOT FOUND THEN
 INSERT INTO sync_fence.first_ball_write_admissions({_STAMP_COLS},state)
 SELECT {_STAMP_B_COLS},{insert_state}
 FROM sync_fence.writer_bindings b
 WHERE (b.tenant_id,b.attempt_id,b.phase_id)={_STAMP_KEY}
 AND b.transaction_id=own_xid
 RETURNING xmin::text INTO row_xmin;
ELSE
 UPDATE sync_fence.first_ball_write_admissions s SET state={update_state}
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)={_STAMP_KEY}
 AND s.transaction_id=own_xid
 RETURNING s.xmin::text INTO row_xmin;
END IF;
IF NOT FOUND OR row_xmin IS NULL
 OR row_xmin::numeric<>pg_catalog.mod(own_xid::numeric,4294967296::numeric) THEN
 {_STAMP_REJECT}
END IF;
"""


_STAMP_BIND_BODY = (
    _BIND_HEAD
    + f"matches := {_BIND_MATCH};\n"
    + _stamp_write(_STAMP_BIND_INSERT, _STAMP_BIND_UPDATE)
    + "RETURN QUERY SELECT matches;\n"
)
_STAMP_RIGHT_BODY = (
    _RIGHT_HEAD
    + "recovery_ok := current_epoch = p_recovery_generation;\n"
    + "right_ok := false;\n"
    + "IF recovery_ok THEN\n right_ok := "
    + _RIGHT_EXISTS
    + ";\nEND IF;\n"
    + _stamp_write(_STAMP_RIGHT_INSERT, _STAMP_RIGHT_UPDATE)
    + "RETURN QUERY SELECT recovery_ok,right_ok;\n"
)
_STAMPED = (
    (
        "bind_device",
        _COMMON + ",p_credential_digest bytea",
        "device_matches boolean",
        _BIND_DECL + " matches boolean;\n" + _STAMP_DECL,
        _STAMP_BIND_BODY,
    ),
    (
        "check_current_right",
        _COMMON
        + (
            ",p_internal_generation bigint,p_recovery_generation bigint,"
            "p_proof_digest bytea"
        ),
        "recovery_matches boolean,right_matches boolean",
        _RIGHT_DECL + " recovery_ok boolean; right_ok boolean;\n" + _STAMP_DECL,
        _STAMP_RIGHT_BODY,
    ),
)


def render_stamped_function_sql() -> dict[str, str]:
    """印を発行するbind_device/check_current_rightの`CREATE OR REPLACE`文を返す。

    戻りの列・型・引数名・language・security・search_pathは既存と同じで、変わるのは
    本文だけである。所有者とACLは既存関数のものを保つ。正式資産へは登録しない
    (登録は正式profileのunit C)。適用は呼び出し側(試験fixture等)が行う。

    Returns:
        関数名から`CREATE OR REPLACE FUNCTION`文への写像。
    """
    return {
        name: f"""CREATE OR REPLACE FUNCTION sync_right_api.{name}({args})
RETURNS TABLE ({results}) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog,pg_temp AS $function$
DECLARE {declarations}
BEGIN
{_ASSERT}{body}END;
$function$;
"""
        for name, args, results, declarations, body in _STAMPED
    }
