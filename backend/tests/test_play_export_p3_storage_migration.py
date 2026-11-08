"""0050の固定DDLを公式型元の全構造・default-denyと比較する。"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from runpy import run_path

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateIndex, CreateTable

from pitchlog.db import all_models
from pitchlog.db.play_export_p3.models import PlayExportP3Snapshot

_MIGRATION = (
    Path(__file__).parents[1] / "migrations/versions/0050_play_export_p3_snapshots.py"
)


def _normalized(statement: str) -> str:
    """SQLトークンを落とさず、描画時の空白だけを比較から除く。"""
    return re.sub(r"\s+", " ", statement).strip()


def test_frozen_ddl_keeps_every_model_column_constraint_and_index():
    """17列の型/null/defaultとPK/FK/CHECK/indexをDDL全値で照合する。"""
    assert all_models.IMPORTED_MODEL_MODULE_NAMES
    table = PlayExportP3Snapshot.__table__
    statements = run_path(str(_MIGRATION))["_STATEMENTS"]
    assert len(table.columns) == 17
    assert tuple(table.primary_key.columns.keys()) == (
        "tenant_id",
        "game_id",
        "internal_generation",
        "capsule_id",
        "d1",
    )
    assert sum(isinstance(c, ForeignKeyConstraint) for c in table.constraints) == 5
    assert sum(isinstance(c, CheckConstraint) for c in table.constraints) == 9
    assert len(table.indexes) == 0
    expected_create = str(CreateTable(table).compile(dialect=dialect()))
    assert _normalized(statements[0]) == _normalized(expected_create)
    expected_indexes = tuple(
        _normalized(str(CreateIndex(i).compile(dialect=dialect())))
        for i in sorted(table.indexes, key=lambda i: str(i.name))
    )
    assert tuple(_normalized(s) for s in statements[5:]) == expected_indexes
    assert table.info["storage_owner"] == "pitchlog_owner"
    assert table.info["append_only"] is True


def test_migration_orders_owner_force_rls_and_default_deny_without_publication():
    """実upgradeの全命令を捕捉し、権限・policy・関数を追加しない。"""
    source = run_path(str(_MIGRATION))
    statements = source["_STATEMENTS"]
    expected_deny = (
        "REVOKE ALL ON TABLE sync_fence.play_export_p3_snapshots FROM "
        "PUBLIC,pitchlog_app,pitchlog_initial_actor,pitchlog_initial_fn_owner,"
        "pitchlog_sync_right_fn_owner,pitchlog_sync_binding_actor,"
        "pitchlog_rg1_control_actor"
    )
    assert tuple(_normalized(s) for s in statements[1:5]) == (
        "ALTER TABLE sync_fence.play_export_p3_snapshots OWNER TO pitchlog_owner",
        "ALTER TABLE sync_fence.play_export_p3_snapshots ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE sync_fence.play_export_p3_snapshots FORCE ROW LEVEL SECURITY",
        expected_deny,
    )
    assert len(statements) == 5
    captured = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(source["op"], "execute", captured.append)
        source["upgrade"]()
    assert captured == list(statements)
    full = "\n".join(statements).upper()
    for forbidden in (
        "GRANT ",
        "CREATE POLICY",
        "CREATE FUNCTION",
        "CREATE TRIGGER",
        "DROP ",
        "DELETE FROM ",
        "TRUNCATE ",
        "SET ROLE",
        "CREATE ROLE",
        "ALTER ROLE",
    ):
        assert forbidden not in full


def test_revision_is_linear_and_downgrade_cannot_delete_audit_source():
    """0049からの単線revisionと、命令実行前のdowngrade拒否を保持する。"""
    source = run_path(str(_MIGRATION))
    assert source["revision"] == "0050_play_export_p3_snapshots"
    assert source["down_revision"] == "0049_pitcher_entry_sources"
    assert source["branch_labels"] is None and source["depends_on"] is None
    previous = run_path(str(_MIGRATION.with_name("0049_pitcher_entry_sources.py")))
    assert source["down_revision"] == previous["revision"]
    captured = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(source["op"], "execute", captured.append)
        with pytest.raises(RuntimeError, match="物理削除できません"):
            source["downgrade"]()
    assert captured == []


def test_migration_is_frozen_and_does_not_import_the_evolving_model():
    """runtime依存をalembic.opだけに閉じ、再描画で旧revisionを変えない。"""
    tree = ast.parse(_MIGRATION.read_text())
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert len(imports) == 1
    assert imports[0].module == "alembic"
    assert [(a.name, a.asname) for a in imports[0].names] == [("op", None)]
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
    assignments = {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    frozen = ast.literal_eval(assignments["_STATEMENTS"])
    assert type(frozen) is tuple and all(type(s) is str for s in frozen)


def test_all_capsule_identity_and_public_original_foreign_keys_are_preserved():
    """全D1原本の五重キーと実プレイ・イベント・成績版を越境不能に結ぶ。"""
    table = PlayExportP3Snapshot.__table__
    actual = {
        tuple(fk.column_keys): tuple(element.target_fullname for element in fk.elements)
        for fk in table.foreign_key_constraints
    }
    expected = {
        ("tenant_id", "game_id", "internal_generation", "capsule_id", "d1"): tuple(
            f"sync_fence.p3_projection_capsule_items.{c}"
            for c in ("tenant_id", "game_id", "internal_generation", "capsule_id", "d1")
        ),
        ("tenant_id", "original_play_row_id"): ("play_rows.tenant_id", "play_rows.id"),
        ("tenant_id", "effective_play_row_id"): ("play_rows.tenant_id", "play_rows.id"),
        ("tenant_id", "effective_event_id"): (
            "operation_events.tenant_id",
            "operation_events.id",
        ),
        ("tenant_id", "game_id", "capsule_stats_version_id"): tuple(
            f"sync_fence.stats_fact_versions.{c}"
            for c in ("tenant_id", "game_id", "id")
        ),
    }
    assert actual == expected
    for fk in table.foreign_key_constraints:
        assert fk.ondelete == "NO ACTION"
        assert all(element.column is not None for element in fk.elements)
    assert tuple(c.name for c in table.columns if c.nullable) == ("reference_json",)
    defaults = {
        c.name: str(c.server_default.arg) for c in table.columns if c.server_default
    }
    assert defaults == {"captured_at": "pg_catalog.clock_timestamp()"}
    assert not table.indexes  # PK先頭からのtenant/game/capsuleの有限keysetを使用する。
