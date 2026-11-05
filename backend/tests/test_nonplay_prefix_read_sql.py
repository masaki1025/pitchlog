"""有限read SQL/全旧body保持と新storage branchの構文を検査する。PGではない。"""

from pitchlog.authz.nonplay_prefix_read_sql import candidate_read_function_bodies


def test_readonly_bounded_and_no_private_output():
    """返却profileの閉列と非play除外根拠を独立に確認する。"""
    sql = candidate_read_function_bodies()["read_nonplay_active_history"]
    assert "LIMIT p_page_size+1" in sql and "p_page_size NOT BETWEEN 1 AND 100" in sql
    assert "'qualified' IS DISTINCT FROM 'true'::jsonb" in sql
    assert "p_logical_version::text" in sql and "c.history_version=p_epoch" in sql
    output = sql.split("items:=items||")[1].split("END LOOP")[0]
    assert "'admission'," not in output and "'ledger'," not in output
    assert "binding_nonce" not in output and "lease_id" not in output
    assert not any(
        x in sql for x in ("INSERT INTO", "UPDATE sync_fence", "DELETE FROM")
    )
