"""migration候補と実モデルの全CHECK/列/索引がずれないことを確認する。"""

import importlib.util
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

import pitchlog.db.all_models  # noqa: F401
from pitchlog.db.writer_binding.lifecycle_models import (
    GameLifecycleHead,
    LifecycleWriteAdmission,
)


def test_migration_creates_exact_models_and_default_deny(monkeypatch):
    """実DDLを捕捉し、DB接続なしで旧42不変更/ACL/物理削除拒否を確かめる。"""
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/0043_game_lifecycle.py"
    )
    spec = importlib.util.spec_from_file_location(
        ("candidate_lifecycle_migration"), path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statements = []
    monkeypatch.setattr(module.op, "execute", statements.append)
    module.upgrade()
    assert module.down_revision == "0042_nonplay_write_admission"
    dialect = postgresql.dialect()
    for model in (LifecycleWriteAdmission, GameLifecycleHead):
        table = model.__table__
        assert str(CreateTable(table).compile(dialect=dialect)) in statements
        for index in table.indexes:
            assert str(CreateIndex(index).compile(dialect=dialect)) in statements
        assert (
            f"ALTER TABLE sync_fence.{table.name} FORCE ROW LEVEL SECURITY"
            in statements
        )
    all_sql = "\n".join(statements)
    assert "GRANT " not in all_sql
    assert "TG_OP IN ('DELETE','TRUNCATE')" in all_sql
    assert "OLD.state<>'evaluated' OR NEW.state<>'consumed'" in all_sql
    assert "current_user<>'pitchlog_sync_right_fn_owner'" in all_sql
