"""固定SQL ABIとcontrol原本証拠の同一性境界を検査する。"""

import pytest

from pitchlog.authz.game_lifecycle_sql import (
    candidate_function_bodies,
    control_bridge_guard,
)
from pitchlog.authz.nonplay_prefix_read_sql import candidate_read_function_bodies
from pitchlog.authz.nonplay_prefix_sql import (
    candidate_function_bodies as nonplay_bodies,
)
from pitchlog.repositories.lifecycle_function_operations import _verify_renderer


def test_control_proof_has_no_caller_chosen_sql_site():
    """SQL識別子文字列を任意bindへ昇格しない。"""
    for arguments in [
        {"content": "caller"},
        {"game": "other_game"},
        {"generation": "1;DROP TABLE games"},
    ]:
        with pytest.raises(ValueError):
            control_bridge_guard(**arguments)


def test_closed_renderer_and_read_bridge_provenance():
    """既writer/right関数と新read/prepare/consumeを同じABIで提供する。"""
    _verify_renderer()
    bodies = candidate_function_bodies()
    assert set(bodies) == {
        "read_lifecycle_state",
        "prepare_game_lifecycle",
        "consume_game_lifecycle",
        "read_lifecycle_display",
    }
    read = candidate_read_function_bodies()["read_nonplay_active_history"]
    assert "UNION ALL SELECT 1 FROM sync_fence.lifecycle_write_admissions a" in read
    assert "FROM sync_fence.nonplay_write_admissions n" in read
    assert (
        "UNION ALL SELECT 1 FROM sync_fence.ordinary_pitch_write_admissions a" in read
    )
    assert "LIMIT p_page_size+1" in read
    guard = control_bridge_guard()
    assert guard in nonplay_bodies()["lock_nonplay_checkpoint"]
    assert guard in bodies["prepare_game_lifecycle"]
    assert guard in bodies["consume_game_lifecycle"]
    assert "e.xmin=a.xmin AND l.xmin=a.xmin" in guard
    assert "original_binding" in guard
    assert "game_lifecycle_heads lifecycle_head" in guard
    assert "game_lifecycle_heads h " not in guard
    assert (
        "control_event.event_kind IN ('game_end_declaration','game_reopen')"
    ) in guard


def test_head_read_uses_existing_game_lock_without_update_rls():
    """未消費の終了印でUPDATE RLSを要求せず、gate別名と衝突しない。"""
    bodies = candidate_function_bodies()
    for name in (
        "read_lifecycle_state",
        "prepare_game_lifecycle",
        "consume_game_lifecycle",
    ):
        body = bodies[name]
        assert "game_row record;" in body
        assert "g record;" not in body
        assert "FROM public.rg1_restore_gate g" in body
        assert "INTO STRICT game_row FROM public.games x" in body
        assert "AND x.import_batch_id IS NULL;" in body
        assert "WHERE x.tenant_id=p_tenant_id AND x.game_id=p_game_id;" in body


def test_v3_physical_and_logical_digest_are_not_equated():
    """旧v3の物理digestとreader導出の論理digestを取り違えない。"""
    for name in ("prepare_game_lifecycle", "consume_game_lifecycle"):
        body = candidate_function_bodies()[name]
        assert "cp.content->>'version' IS DISTINCT FROM '3' AND" in body
        assert "cp.content_digest)" in body
        assert "cp.content->>'version'='3' AND" in body
        assert "'^[a-f0-9]{64}$'" in body


def test_jsonb_key_removal_keeps_extraction_precedence():
    """literal同士の減算を作らずcheckpoint/targetのkindだけを除く。"""
    for name in ("prepare_game_lifecycle", "consume_game_lifecycle"):
        body = candidate_function_bodies()[name]
        assert "((own_event.payload->'checkpointRef')-'kind')" in body
        assert "(own_event.payload->'target')-'kind'" in body
        assert "->'checkpointRef'-'kind'" not in body
        assert "->'target'-'kind'" not in body


def test_lifecycle_admission_digest_tracks_logical_bridge():
    """旧v3の物理digestとcontrolBridgeの論理refを混用しない。"""
    body = candidate_function_bodies()["prepare_game_lifecycle"]
    assert "checkpoint_digest" in body
    assert "before_cp->'ref'->>'digest'" in body
    assert "a.checkpoint_digest=b.value->'checkpointBefore'->>'digest'" in (
        control_bridge_guard()
    )
