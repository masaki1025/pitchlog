"""P3 slot v2 の証明だけを非play reader に追加する対向。"""

import json
from pathlib import Path

import pytest

from pitchlog.authz.game_lifecycle_sql import (
    candidate_function_bodies as lifecycle_bodies,
)
from pitchlog.authz.nonplay_prefix_read_sql import candidate_read_function_bodies
from pitchlog.authz.nonplay_prefix_sql import (
    _active_evidence_query,
    candidate_function_bodies,
)
from pitchlog.authz.p3_nonplay_bridge_sql import (
    _p3_active_evidence_query,
    candidate_function_bodies_p3_nonplay_bridge,
    candidate_lifecycle_p3_body,
)
from pitchlog.domaingen.core import generate_native_primitive_sql_bundle
from pitchlog.domaingen.pregen_checks import validate_undo_selection_profile


def test_p3_nonplay_bridge_changes_only_slot_qualification() -> None:
    """元 event/admission/physical の式を保持し、slot2 は別証明を要求する。"""
    old = _active_evidence_query()
    new = _p3_active_evidence_query()
    assert new != old
    assert "AND es.confirmed_version IN (1,2)" in new
    assert "es.confirmed_version=1 AND es.xmin=a.xmin" in new
    assert "es.confirmed_version=2 AND EXISTS(" in new
    for source_guard in (
        "AND e.xmin=a.xmin AND l.xmin=a.xmin AND pr.xmin=a.xmin",
        "AND h.entry=a.history_entry",
        "AND a.next_checkpoint_content->'projection_snapshot' IS NOT NULL",
        "AND es.xmin=pa.xmin AND ce.xmin=pa.xmin",
        "AND ep.xmin=pa.xmin AND pc.xmin=pa.xmin AND pi.xmin=pa.xmin",
        "AND ph.xmin=pa.xmin",
        "AND pi.original_payload=e.payload",
        "AND pi.original_history_entry=h.entry",
    ):
        assert source_guard in new
    assert new.count("p3_projection_heads") == 1
    assert old.count("p3_projection_heads") == 0


def test_p3_nonplay_bridge_renders_both_readers() -> None:
    """既二関数の旧版句を別資格へ置換し、通常原本は保持する。"""
    candidate = candidate_function_bodies_p3_nonplay_bridge()
    assert set(candidate) == {
        "read_nonplay_history_page",
        "read_nonplay_active_history",
    }
    old_writer = candidate_function_bodies()["read_nonplay_history_page"]
    old_reader = candidate_read_function_bodies()["read_nonplay_active_history"]
    assert candidate["read_nonplay_history_page"].count("p3_projection_heads") == 1
    assert candidate["read_nonplay_active_history"].count("p3_projection_heads") == 6
    for name, old in (
        ("read_nonplay_history_page", old_writer),
        ("read_nonplay_active_history", old_reader),
    ):
        assert old.count("p3_projection_heads") == 0
        assert "AND a.source_event_id=e.id" in candidate[name]
        assert "AND es.confirmed_version=1" in candidate[name]


def test_p3_lifecycle_bridge_changes_only_generated_selectors() -> None:
    """終了consumeは唯一生成Sの二section以外を保持し、未知bindを拒否する。"""
    from pitchlog.authz.game_lifecycle_sql import _bind
    from pitchlog.authz.stats_primitive_sql import _ROOT, _verified_inputs

    _, sections, _, _ = _verified_inputs(_ROOT)
    root = Path(__file__).resolve().parents[2]
    profile = json.loads(
        (root / "backend/domain/play-export-undo-selection.model.json").read_text()
    )
    profile.update(
        version=2,
        kind="accepted-play-slot-consumed-undo-p3-v2",
        p3={
            "heads": "sync_fence.p3_projection_heads",
            "capsules": "sync_fence.p3_projection_capsules",
            "items": "sync_fence.p3_projection_capsule_items",
        },
    )
    validate_undo_selection_profile(profile)
    bundle = generate_native_primitive_sql_bundle(
        json.loads((root / "backend/domain/play-export.model.json").read_text()),
        json.loads((root / "backend/domain/stats.model.json").read_text()),
        profile,
    )
    source = bundle["backend/src/pitchlog/exports/generated/play_primitives_native.sql"]
    p3_sections = {
        part.split("\n", 1)[0]: part.split("\n", 1)[1].strip()
        for part in source.split("-- pitchlog-query: ")[1:]
    }
    health = p3_sections["canonical_health"]
    members = p3_sections["canonical_source_members"]
    old = lifecycle_bodies()["consume_game_lifecycle"]
    new = candidate_lifecycle_p3_body(health, members)
    assert new != old
    assert new.count("p3_projection_heads") == 2
    assert new.count("pg_catalog.to_jsonb(p.*)") == 2
    assert "pg_catalog.to_jsonb(p)" not in new
    expected_health = _bind(health).replace(
        "pg_catalog.to_jsonb(p)", "pg_catalog.to_jsonb(p.*)", 1
    )
    expected_members = _bind(members).replace(
        "pg_catalog.to_jsonb(p)", "pg_catalog.to_jsonb(p.*)", 1
    )
    assert (
        new.replace(expected_health, _bind(sections["canonical_health"]), 1).replace(
            expected_members, _bind(sections["canonical_source_members"]), 1
        )
        == old
    )
    with pytest.raises(ValueError, match="未知bind"):
        candidate_lifecycle_p3_body(health + " :unbound", members)
    with pytest.raises(ValueError, match="行参照"):
        candidate_lifecycle_p3_body(
            health.replace("pg_catalog.to_jsonb(p)", "pg_catalog.to_jsonb(other)"),
            members,
        )
