"""未適用SQL候補の固定境界を確認する。DB成功試験ではない。"""

from pitchlog.authz.sync_right_sql import render_sync_right_sql


def test_exact_sql_boundary() -> None:
    """有限関数/秘密非射影/未供給binding参照を保持する。"""
    sql = render_sync_right_sql()
    assert sql.count("CREATE FUNCTION sync_right_api.") == 2
    assert sql.count("PERFORM sync_fence_api.assert_writer_binding(") == 2
    assert sql.count("SECURITY DEFINER") == 2
    assert sql.count("SET search_path = pg_catalog,pg_temp") == 2
    assert "FOR SHARE" in sql
    assert "UPDATE (revoked_at)" in sql
    assert "UPDATE (credential_digest)" not in sql
    assert "CREATE FUNCTION sync_fence_api." not in sql
    assert "pitchlog_initial_actor" not in sql
    assert "recording_right_deliveries" not in sql
    assert "ciphertext" not in sql
    assert "WHEN OTHERS" not in sql
    assert "RETURNS TABLE (device_matches boolean)" in sql
    assert "RETURNS TABLE (recovery_matches boolean,right_matches boolean)" in sql
    assert (
        "p_internal_generation bigint,p_recovery_generation bigint,p_proof_digest bytea"
        in sql
    )
    assert "p_binding_nonce) <> 32" in sql
    assert "p_proof_digest) <> 32" in sql
    assert sql.count("GRANT EXECUTE ON FUNCTION sync_right_api.") == 2
    assert "NOBYPASSRLS" in sql and "FORCE ROW LEVEL SECURITY" in sql
