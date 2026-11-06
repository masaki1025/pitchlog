"""P3専用の実端末・現記録権照合関数候補を描画する。"""

from pitchlog.authz.sync_right_sql import (
    _ASSERT,
    _BIND_DECL,
    _BIND_HEAD,
    _BIND_MATCH,
    _COMMON,
    _RIGHT_DECL,
    _RIGHT_EXISTS,
    _RIGHT_HEAD,
)


def candidate_sql() -> dict[str, str]:
    """既B5/B6述語を実bound writerで評価する二関数を返す。"""
    bind = f"""CREATE FUNCTION sync_right_api.bind_p3_device(
{_COMMON},p_credential_digest bytea)
RETURNS TABLE(device_matches boolean) LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_bind$
DECLARE {_BIND_DECL}
BEGIN
{_ASSERT}
{_BIND_HEAD}
RETURN QUERY SELECT {_BIND_MATCH};
END;
$p3_bind$;
ALTER FUNCTION sync_right_api.bind_p3_device(uuid,uuid,uuid,bytea,uuid,uuid,bytea)
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.bind_p3_device(
 uuid,uuid,uuid,bytea,uuid,uuid,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.bind_p3_device(
 uuid,uuid,uuid,bytea,uuid,uuid,bytea) TO pitchlog_app;
"""
    right = f"""CREATE FUNCTION sync_right_api.check_p3_right(
{_COMMON},p_internal_generation bigint,p_recovery_generation bigint,
p_proof_digest bytea)
RETURNS TABLE(recovery_matches boolean,right_matches boolean)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $p3_right$
DECLARE {_RIGHT_DECL}
BEGIN
{_ASSERT}
{_RIGHT_HEAD}
RETURN QUERY SELECT current_epoch=p_recovery_generation,
 CASE WHEN current_epoch=p_recovery_generation THEN {_RIGHT_EXISTS}
 ELSE false END;
END;
$p3_right$;
ALTER FUNCTION sync_right_api.check_p3_right(
 uuid,uuid,uuid,bytea,uuid,uuid,bigint,bigint,bytea)
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.check_p3_right(
 uuid,uuid,uuid,bytea,uuid,uuid,bigint,bigint,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sync_right_api.check_p3_right(
 uuid,uuid,uuid,bytea,uuid,uuid,bigint,bigint,bytea) TO pitchlog_app;
"""
    return {"bind_p3_device": bind, "check_p3_right": right}
