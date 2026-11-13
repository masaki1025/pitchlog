"""タイブレーク開始SQLが世代・試合・復旧世代を弱めずに拒否することを固定する。"""

from pitchlog.authz.tiebreak_sql import candidate_tiebreak_start_function_body


def test_tiebreak_consume_binds_exact_game_generation_and_recovery():
    """CPは同一試合・同一内部世代・同一復旧世代・currentだけを一点ロックする。"""
    sql = candidate_tiebreak_start_function_body()
    for required in (
        "SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints c",
        "WHERE c.tenant_id=p_tenant_id AND c.game_id=p_game_id",
        "AND c.internal_generation=stamp.internal_generation AND c.state='current'",
        "AND c.recovery_generation=stamp.recovery_generation FOR UPDATE",
        "e.id=(p->>'eventId')::uuid AND e.d5=stamp.d5",
        "AND e.generation=stamp.internal_generation",
        "e.event_kind='tiebreak_start'",
    ):
        assert required in sql


def test_tiebreak_consume_never_falls_back_to_other_generation_or_copies_identity():
    """旧世代・別試合・別復旧世代の代替行やCPからの資格流用を許さない。"""
    sql = candidate_tiebreak_start_function_body()
    for forbidden in (
        "DELETE FROM",
        "TRUNCATE",
        "EXCEPTION WHEN",
        "OR c.state",
        "c.internal_generation<=stamp.internal_generation",
        "c.recovery_generation<>stamp.recovery_generation",
        "ORDER BY c.revision DESC LIMIT 1",
        "stamp.internal_generation:=cp.internal_generation",
        "stamp.recovery_generation:=cp.recovery_generation",
    ):
        assert forbidden not in sql
