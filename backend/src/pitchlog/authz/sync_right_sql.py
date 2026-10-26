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
_FUNCTIONS = (
    (
        "bind_device",
        "uuid,uuid,uuid,bytea,uuid,uuid,bytea",
        _COMMON + ",p_credential_digest bytea",
        "device_matches boolean",
        "stored_digest bytea; revoked timestamptz;",
        """
IF p_credential_digest IS NULL OR
 pg_catalog.octet_length(p_credential_digest) <> 32 THEN
 RAISE EXCEPTION 'sync credential input rejected' USING ERRCODE='42501';
END IF;
SELECT d.credential_digest,d.revoked_at INTO stored_digest,revoked
 FROM public.trusted_devices d
 WHERE d.tenant_id=p_tenant_id AND d.device_id=p_device_id FOR SHARE;
RETURN QUERY SELECT COALESCE(FOUND AND revoked IS NULL AND
 stored_digest=p_credential_digest,false);
""",
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
        "current_epoch bigint; gate_state text;",
        """
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
IF current_epoch <> p_recovery_generation THEN
 RETURN QUERY SELECT false,false;
 RETURN;
END IF;
-- game→generation lockは既prefix核が保持。本関数で先取りしない。
RETURN QUERY SELECT true,EXISTS (
 SELECT 1 FROM public.recording_generations r WHERE r.tenant_id=p_tenant_id
 AND r.game_id=p_game_id AND r.generation=p_internal_generation AND r.kind='normal'
 AND r.holder_device=p_device_id::text AND r.revoked_at IS NULL
 AND r.retired_at IS NULL AND r.recovery_generation=current_epoch
 AND r.proof_digest=p_proof_digest);
""",
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
