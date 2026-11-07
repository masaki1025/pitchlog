"""0049の固定DDLを公式型元の全構造・default-denyと比較する。"""

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
from pitchlog.db.game_state.pitcher_appearance_models import PitcherEntrySource

_MIGRATION = (
    Path(__file__).parents[1] / "migrations/versions/0049_pitcher_entry_sources.py"
)


def _normalized(statement: str) -> str:
    """SQLトークンを落とさず、描画時の空白だけを比較から除く。"""
    return re.sub(r"\s+", " ", statement).strip()


def test_frozen_ddl_keeps_every_model_column_constraint_and_index():
    """17列の型/null/defaultとPK/FK/CHECK/indexをDDL全値で照合する。"""
    assert all_models.IMPORTED_MODEL_MODULE_NAMES
    table = PitcherEntrySource.__table__
    statements = run_path(str(_MIGRATION))["_STATEMENTS"]
    assert len(table.columns) == 17
    assert tuple(table.primary_key.columns.keys()) == (
        "tenant_id",
        "game_id",
        "proof_sha256",
    )
    assert sum(isinstance(c, ForeignKeyConstraint) for c in table.constraints) == 5
    assert sum(isinstance(c, CheckConstraint) for c in table.constraints) == 4
    assert len(table.indexes) == 1
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
        "REVOKE ALL ON TABLE sync_fence.pitcher_entry_sources FROM "
        "PUBLIC,pitchlog_app,pitchlog_initial_actor,pitchlog_initial_fn_owner,"
        "pitchlog_sync_right_fn_owner,pitchlog_sync_binding_actor,"
        "pitchlog_rg1_control_actor"
    )
    assert tuple(_normalized(s) for s in statements[1:5]) == (
        "ALTER TABLE sync_fence.pitcher_entry_sources OWNER TO pitchlog_owner",
        "ALTER TABLE sync_fence.pitcher_entry_sources ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE sync_fence.pitcher_entry_sources FORCE ROW LEVEL SECURITY",
        expected_deny,
    )
    assert len(statements) == 6
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
    """0048からの単線revisionと、命令実行前のdowngrade拒否を保持する。"""
    source = run_path(str(_MIGRATION))
    assert source["revision"] == "0049_pitcher_entry_sources"
    assert source["down_revision"] == "0048_p3_projection_storage"
    assert source["branch_labels"] is None and source["depends_on"] is None
    previous = run_path(str(_MIGRATION.with_name("0048_p3_projection_storage.py")))
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
