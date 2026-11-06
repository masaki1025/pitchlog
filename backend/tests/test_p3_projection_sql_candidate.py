"""0046候補SQLが既生成Sと旧二段triggerを正確に再利用する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitchlog.authz.p3_projection_sql import candidate_current_read_sql
from pitchlog.authz.p3_projection_sql import candidate_sql as persist_sql
from pitchlog.authz.p3_projection_trigger_patch import candidate_sql as trigger_sql
from pitchlog.authz.stats_primitive_sql import (
    _verified_inputs,
    candidate_function_bodies,
)
from pitchlog.domaingen.core import generate_native_primitive_sql_bundle
from pitchlog.domaingen.pregen_checks import validate_undo_selection_profile

_ROOT = Path(__file__).resolve().parents[2]


def _health() -> str:
    """既正式v1入力から閉じたP3候補profileを作る。"""
    selector = json.loads(
        (_ROOT / "backend/domain/play-export-undo-selection.model.json").read_text()
    )
    selector.update(
        version=2,
        kind="accepted-play-slot-consumed-undo-p3-v2",
        p3={
            "heads": "sync_fence.p3_projection_heads",
            "capsules": "sync_fence.p3_projection_capsules",
            "items": "sync_fence.p3_projection_capsule_items",
        },
    )
    validate_undo_selection_profile(selector)
    common = json.loads((_ROOT / "backend/domain/play-export.model.json").read_text())
    consumer = json.loads((_ROOT / "backend/domain/stats.model.json").read_text())
    bundle = generate_native_primitive_sql_bundle(common, consumer, selector)
    source = bundle["backend/src/pitchlog/exports/generated/play_primitives_native.sql"]
    sections = {
        section.split("\n", 1)[0]: section.split("\n", 1)[1].strip()
        for section in source.split("-- pitchlog-query: ")[1:]
    }
    assert set(sections) == {
        "window",
        "count",
        "current_totals",
        "canonical_members",
        "canonical_health",
        "canonical_source_members",
    }
    return sections["canonical_health"]


def test_p3_candidate_keeps_official_v1_exact_and_requires_v2_selector() -> None:
    """v1生成物の全byte固定を保持し、P3版なしでは保存SQLを出さない。"""
    _verified_inputs(_ROOT)
    with pytest.raises(ValueError, match="P3生成canonical selector"):
        persist_sql()
    health = _health()
    sql = persist_sql(health_sql=health)
    assert "__HEALTH__" not in sql
    assert ":tenant_id" not in sql
    assert ":game_id" not in sql
    assert "sync_fence.p3_projection_heads p3h" in sql
    assert "original_eval IS DISTINCT FROM old_source.metric_states" in sql
    assert "pg_catalog.jsonb_each(effective_eval->'metrics')" in sql
    assert "health.canonical_source_set_sha256" in sql
    assert "p3_projection_write_admissions" in sql
    assert "l.source_fingerprint=c->>'ledger_fingerprint'" in sql
    assert "l.source_fingerprint=binding.event_fingerprint" not in sql
    assert "CASE WHEN current_d1=target_d1 THEN c->>'ledger_fingerprint'" in sql
    assert "CASE WHEN current_d1=target_d1 THEN binding.event_fingerprint" not in sql
    reader = candidate_current_read_sql(health_sql=health)
    assert "__HEALTH__" not in reader
    assert "cp.confirmed_watermark NOT BETWEEN c.watermark AND c.watermark+1" in reader
    assert (
        "health.canonical_source_set_sha256 IS DISTINCT FROM v.source_set_sha256"
        in reader
    )
    assert "'suffix',suffix_member,'stats_sources',source_rows" in reader
    with pytest.raises(ValueError, match="P3生成canonical selector"):
        candidate_current_read_sql(
            health_sql=health.replace("p3_projection_heads p3h", "other p3h")
        )
    assert "slot.d1<=p3c.watermark" in health
    assert "p3i.d1 IS NULL" in health
    profile = json.loads(
        (_ROOT / "backend/domain/play-export-undo-selection.model.json").read_text()
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
    bodies = candidate_function_bodies(p3_selector_profile=profile)
    assert len(bodies) == 4
    assert all("p3_projection_heads" in body for body in bodies.values())
    profile["p3"]["heads"] = "sync_fence.other_heads"
    with pytest.raises(ValueError, match="未登録の取消canonical"):
        candidate_function_bodies(p3_selector_profile=profile)
    with pytest.raises(ValueError, match="P3生成canonical selector"):
        persist_sql(health_sql=health.replace("p3_projection_heads p3h", "other p3h"))


def test_p3_trigger_candidate_preserves_old_function_boundaries() -> None:
    """旧triggerを別実装せず、P3実印分岐だけを固定位置へ足す。"""
    sql = trigger_sql()
    assert sql.count("CREATE OR REPLACE FUNCTION") == 2
    assert sql.count("p3_projection_write_admissions") >= 2
    assert "a.expected_play_row=pg_catalog.to_jsonb(NEW)" in sql
    assert "a.xmin::text::numeric=pg_catalog.mod(" in sql
    assert "l.source_fingerprint=a.ledger_fingerprint" in sql
    assert "l.source_fingerprint=b.event_fingerprint" not in sql
    assert sql.index("P3 play row admission rejected") < sql.index(
        "-- 既核と同じgame→current generationの順"
    )
