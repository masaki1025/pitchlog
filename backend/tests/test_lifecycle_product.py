"""終了再開の正式認可publisherが新表と旧stats境界を閉じて扱う検査。"""

from __future__ import annotations

import copy
from typing import Any, cast

import pytest

from pitchlog.authz import lifecycle_product
from pitchlog.authz.lifecycle_storage_profile import declarations as guard_declarations
from pitchlog.authz.lifecycle_storage_profile import trigger_expectations


def test_lifecycle_product_declares_only_fixed_owner_and_consumed_gate() -> None:
    """4関数・2表と既表の必要最小書込だけを同TX印へ束縛する。"""
    declarations, bodies = lifecycle_product.candidate_declarations()
    assert {k: len(v) for k, v in declarations.items()} == {
        "tables": 2,
        "functions": 4,
        "policies": 11,
        "acl_expectations": 1,
        "column_acl_expectations": 54,
    }
    assert len(bodies) == 72
    assert {row["table_id"] for row in declarations["tables"]} == {
        "lifecycle_write_admissions",
        "game_lifecycle_heads",
    }
    assert all(
        row["owner_role_id"] == "pitchlog_sync_right_fn_owner"
        for row in declarations["functions"]
    )
    assert not any(
        row["grantee_role_id"] == "pitchlog_app"
        for row in declarations["column_acl_expectations"]
    )
    policies = {row["policy_id"]: row for row in declarations["policies"]}
    for key in (
        "POLICY:games:lifecycle_status_update",
        "POLICY:stats_fact_versions:lifecycle_end_insert",
        "POLICY:stats_fact_versions:lifecycle_reopen_update",
        "POLICY:stats_primitive_sources:lifecycle_end_insert",
        "POLICY:stats_primitive_facts:lifecycle_end_insert",
    ):
        row = policies[key]
        predicate = row["with_check_expression"] or row["using_expression"]
        assert "lifecycle_write_admissions" in predicate
        assert "pg_current_xact_id()::text" in predicate
    assert (
        "a.game_id=games.id"
        in policies["POLICY:games:lifecycle_status_update"]["using_expression"]
    )


def test_lifecycle_product_rejects_model_or_function_drift(monkeypatch) -> None:
    """固定モデルや関数属性の緩和を自動的な権限拡大へ伝播させない。"""
    original = lifecycle_product._TABLES
    altered = cast(dict[str, Any], copy.copy(original))
    model, count, digest, mutable = altered["game_lifecycle_heads"]
    altered["game_lifecycle_heads"] = (model, count, "sha256:" + "0" * 64, mutable)
    with monkeypatch.context() as patch:
        patch.setattr(lifecycle_product, "_TABLES", altered)
        with pytest.raises(ValueError, match="固定列"):
            lifecycle_product.candidate_declarations()
    originals = lifecycle_product.candidate_function_bodies()
    altered_bodies = dict(originals)
    altered_bodies["read_lifecycle_display"] = altered_bodies[
        "read_lifecycle_display"
    ].replace("SECURITY DEFINER", "SECURITY INVOKER", 1)
    with monkeypatch.context() as patch:
        patch.setattr(
            lifecycle_product, "candidate_function_bodies", lambda: altered_bodies
        )
        with pytest.raises(ValueError, match="関数署名"):
            lifecycle_product.candidate_declarations()


def test_migration_guard_and_trigger_set_remains_closed() -> None:
    """0043 migrationの内部二関数と四triggerを原本から照合する。"""
    rows = guard_declarations()
    assert len(rows) == 2
    assert all(row["function_kind"] == "migration_trigger" for row, _ in rows)
    assert {row["function_name"] for row, _ in rows} == {
        "protect_lifecycle_write_admissions",
        "protect_game_lifecycle_heads",
    }
    assert len(trigger_expectations()) == 4
