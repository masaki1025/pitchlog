"""交代の固定関数が旧取消の物理副作用を再利用しないことを確認する。"""

from pitchlog.authz.substitution_sql import candidate_substitution_function_body


def test_substitution_sql_binds_event_ledger_cp_and_never_hides_play():
    """確定event/台帳/CP全原本を同一writer印で照合する。"""
    sql = candidate_substitution_function_body()
    for required in (
        "stamp.state<>'right_verified'",
        "s.transaction_id=own_xid",
        "e.event_kind='substitution'",
        "e.id=(p->>'eventId')::uuid",
        "l.source_fingerprint=stamp.event_fingerprint",
        "cp.content IS DISTINCT FROM before_cp",
        "own_event.payload->'expectedCheckpoint' IS DISTINCT FROM before_cp->'ref'",
        "p->'afterSource'->'activeStack' IS DISTINCT FROM "
        "p->'beforeSource'->'activeStack'",
        "UPDATE sync_fence.ordinary_pitch_checkpoints SET",
        "INSERT INTO sync_fence.substitution_write_receipts",
    ):
        assert required in sql
    for forbidden in (
        "DELETE FROM",
        "TRUNCATE",
        "UPDATE public.play_rows SET hidden_at",
        "INSERT INTO public.play_rows",
        "EXCEPTION WHEN",
    ):
        assert forbidden not in sql
