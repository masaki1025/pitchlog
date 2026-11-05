"""固定SQLの資格/原子境界の有限検査。実PG成功の代替ではない。"""

from pitchlog.authz.nonplay_prefix_sql import candidate_function_bodies


def test_exact_closed_function_set():
    """新自由関数/任意SQLを足さない。"""
    sql = candidate_function_bodies()
    assert set(sql) == {
        "bind_nonplay_device",
        "check_nonplay_right",
        "lock_nonplay_checkpoint",
        "read_nonplay_history_page",
        "prepare_nonplay_undo",
        "consume_nonplay_undo",
    }
    for name, text in sql.items():
        assert "sync_right_api." + name + "(" in text
        assert "SECURITY DEFINER" in text
        assert "SET search_path" in text
        assert "assert_writer_binding" in text
        assert "p_binding_nonce" in text
        assert "pitchlog_app" in text
        assert "pitchlog_sync_right_fn_owner" in text
        assert "sync_fence.nonplay_write_admissions" in text
        assert "DELETE FROM" not in text and "TRUNCATE" not in text
        assert "EXCEPTION WHEN" not in text


def test_prepare_checks_actual_source_and_complete_bindings():
    """旧play印を偽造せず実ledger/slot/target/CP全値へ束縛する。"""
    sql = candidate_function_bodies()["prepare_nonplay_undo"]
    for clause in [
        "s.transaction_id=own_xid",
        "a.xmin::text",
        "b.expires_at>",
        "stamp.state<>'right_verified'",
        "public.event_slots",
        "public.idempotency_ledger",
        "e.event_kind='undo'",
        "e.d2 IS NULL",
        "e.state_diff IS NULL",
        "target_generation",
        "activeHead",
        "cp.revision+1",
        "pg_catalog.max(r.play_number)+1",
        "preparation_json=p_request_json",
        "target_play_id=target_play.id",
    ]:
        assert clause in sql
    assert "SET state='evaluated'" in sql
    assert "play_row_id=" not in sql and "source_d2=" not in sql


def test_consume_exact_snapshot_and_single_atomic_statement_family():
    """本体は同TXに留まり、失敗は外側へ伝播する。"""
    sql = candidate_function_bodies()["consume_nonplay_undo"]
    for clause in [
        "stamp.state<>'evaluated'",
        "stamp.preparation_json IS DISTINCT FROM p_request_json",
        "stamp.preparation IS DISTINCT FROM p",
        "FOR UPDATE",
        "UPDATE public.play_rows SET hidden_at=",
        "source_event_id=stamp.target_event_id",
        "UPDATE sync_fence.ordinary_pitch_checkpoints",
        "SET state='consumed'",
        "IF NOT FOUND THEN",
    ]:
        assert clause in sql
    assert "SAVEPOINT" not in sql and "COMMIT" not in sql
    assert "INSERT INTO public.play_rows" not in sql


def test_history_is_finite_keyset_and_missing_original_not_silent():
    """source全読込集計にせず、欠測をINNER JOINで隠さない。"""
    sql = candidate_function_bodies()["read_nonplay_history_page"]
    assert "LIMIT 100" in sql and "OFFSET" not in sql
    assert "ORDER BY v.issuance_order DESC,v.d1 DESC,v.source_event_id DESC" in sql
    assert "LEFT JOIN public.operation_events" in sql
    assert "LEFT JOIN public.play_rows" in sql
    assert "n.target_event_id=e.id AND n.state='consumed'" in sql
    assert "nonplay_active_history_evidence" not in sql


def test_saved_evidence_profile_preserves_raw_fingerprint_and_original_tx():
    """原wireを再生せず、同原取引の保存原本と印の閉対応を返す。"""
    sql = candidate_function_bodies()["read_nonplay_history_page"]
    for text in (
        "accepted-ordinary-admission-v1",
        "'storedEvent'",
        "'qualified',COALESCE",
        "a.history_entry",
        "h.internal_generation=e.generation",
        "a.source_d2=e.d2",
        "a.event_fingerprint=l.source_fingerprint",
        "f.event_fingerprint=l.source_fingerprint",
        "a.xmin::text::numeric",
        "f.xmin::text::numeric",
        "e.xmin=a.xmin",
        "l.xmin=a.xmin",
        "pr.xmin=a.xmin",
        "es.xmin=a.xmin",
        "e.xmin=f.xmin",
        "es.confirmed_version=1",
        "'event',pg_catalog.to_jsonb(e)",
        "'ledger',pg_catalog.to_jsonb(l)",
        "'slot',pg_catalog.to_jsonb(es)",
        "'admission',pg_catalog.to_jsonb(a)",
        "'admission',pg_catalog.to_jsonb(f)",
    ):
        assert text in sql
    assert "'original'," not in sql
    assert "digest(" not in sql and "sha256(" not in sql
