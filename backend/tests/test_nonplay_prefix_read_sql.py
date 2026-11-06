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


def test_bootstrap_legacy_branch_keeps_signature_and_all_saved_qualification():
    """能力を増やさずv3の保存原本/全page/世代連結を同じSQL内で検査する。"""
    sql = candidate_read_function_bodies()["read_nonplay_active_history"]
    assert sql.count("CREATE FUNCTION") == 1
    assert "c.content->>'version'='3'" in sql
    assert "a.next_checkpoint_content=cp.content" in sql
    assert "a.xmin=cp.xmin" in sql and "es.xmin=a.xmin" in sql
    assert "l.source_fingerprint=a.event_fingerprint" in sql
    assert "c.content->'storage_anchor'->>'history_epoch'=p_epoch::text" in sql
    assert "'generationChain',chain" in sql
    assert "total::text IS DISTINCT FROM cp.content->>'history_depth'" in sql
    assert "FOR SHARE OF c,g" not in sql
    assert sql.count("FOR SHARE OF c;") == 2
    assert "LIMIT p_page_size+1" in sql
    assert "LIMIT 100;" not in sql


def test_generation_join_and_both_branch_guards_remain():
    """g rowlockだけを外し、NP/旧v3のtenant/世代/水位条件を保持する。"""
    sql = candidate_read_function_bodies()["read_nonplay_active_history"]
    assert sql.count("FOR SHARE OF c;") == 2
    assert sql.count("JOIN public.recording_generations g") == 2
    assert sql.count("g.recovery_generation=c.recovery_generation") == 2
    assert sql.count("g.confirmed_watermark=p_d3 AND g.applied_prefix=p_d3") == 2
    assert sql.count("g.kind='normal'") == 2
    assert sql.count("g.revoked_at IS NULL AND g.retired_at IS NULL") == 2
    assert sql.count("g.import_batch_id IS NULL") == 2
    assert sql.count("p_tenant_id IS DISTINCT FROM") == 2
    assert sql.count("p_after_order=0 AND (p_after_d1<>0") == 2
    assert sql.count("LIMIT p_page_size+1") == 2
