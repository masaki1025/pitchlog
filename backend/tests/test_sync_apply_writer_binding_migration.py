"""writer補助表の凍結DDLと単一モデルの一致を検査する。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from sqlalchemy.schema import SchemaItem

from pitchlog.db import all_models
from pitchlog.db.base import Base
from pitchlog.sync.control_provider.writer_binding_models import (
    WriterAdmission,
    WriterBinding,
)

_REVISION = (
    Path(__file__).resolve().parents[1]
    / "migrations/versions/0037_sync_writer_binding.py"
)


class _DDLRecorder:
    """Alembicの構造化DDLをSQLAlchemy表として捕捉する。"""

    def __init__(self) -> None:
        self.metadata = sa.MetaData()
        self.tables: list[sa.Table] = []
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)

    def create_table(self, name: str, *elements: SchemaItem, schema: str) -> None:
        self.tables.append(sa.Table(name, self.metadata, *elements, schema=schema))


def _revision_module() -> ModuleType:
    """製品revisionそのものを独立名で読み込む。"""
    spec = importlib.util.spec_from_file_location("writer_binding_revision", _REVISION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _constraint_shape(constraint: sa.Constraint) -> tuple[object, ...]:
    """全制約の型、名前、列、条件、参照動作を順序付きで返す。"""
    if isinstance(constraint, sa.CheckConstraint):
        return ("check", constraint.name, str(constraint.sqltext))
    if isinstance(constraint, sa.ForeignKeyConstraint):
        return (
            "foreign_key",
            constraint.name,
            tuple(element.parent.name for element in constraint.elements),
            tuple(element.target_fullname for element in constraint.elements),
            constraint.match,
            constraint.ondelete,
        )
    assert isinstance(constraint, (sa.PrimaryKeyConstraint, sa.UniqueConstraint))
    return (
        type(constraint).__name__,
        constraint.name,
        tuple(column.name for column in constraint.columns),
    )


def test_migration_preserves_every_model_column_and_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2表全列・全制約を一致させ、未供給ACLではdefault-denyにする。"""
    recorder = _DDLRecorder()
    revision = _revision_module()
    monkeypatch.setattr(revision, "op", recorder)
    revision.upgrade()
    assert revision.revision == "0037_sync_writer_binding"
    assert revision.down_revision == "0036_initial_right_storage"
    binding_table = WriterBinding.__table__
    admission_table = WriterAdmission.__table__
    assert isinstance(binding_table, sa.Table)
    assert isinstance(admission_table, sa.Table)
    expected_tables = [binding_table, admission_table]
    assert [len(table.columns) for table in expected_tables] == [29, 5]
    assert [table.key for table in recorder.tables] == [
        table.key for table in expected_tables
    ]
    for actual, expected in zip(recorder.tables, expected_tables, strict=True):
        assert [
            (column.name, str(column.type), column.nullable, column.server_default)
            for column in actual.columns
        ] == [
            (column.name, str(column.type), column.nullable, column.server_default)
            for column in expected.columns
        ]
        assert {_constraint_shape(item) for item in actual.constraints} == {
            _constraint_shape(item) for item in expected.constraints
        }
        assert list(actual.indexes) == list(expected.indexes) == []
    assert recorder.statements == [
        "CREATE SCHEMA sync_fence AUTHORIZATION pitchlog_owner",
        "REVOKE ALL ON SCHEMA sync_fence FROM PUBLIC",
        "ALTER TABLE sync_fence.writer_bindings ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE sync_fence.writer_bindings FORCE ROW LEVEL SECURITY",
        "REVOKE ALL ON TABLE sync_fence.writer_bindings FROM PUBLIC",
        "ALTER TABLE sync_fence.writer_admissions ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE sync_fence.writer_admissions FORCE ROW LEVEL SECURITY",
        "REVOKE ALL ON TABLE sync_fence.writer_admissions FROM PUBLIC",
    ]


def test_migration_refuses_to_erase_writer_history() -> None:
    """逆適用で資格・終結の証拠を消さない。"""
    with pytest.raises(RuntimeError, match="writer資格の履歴を消す逆適用は許可しない"):
        _revision_module().downgrade()


def test_single_writer_model_is_discovered_without_a_duplicate() -> None:
    """既モデル走査経由で同じ2Tableだけを登録する。"""
    assert "pitchlog.db.writer_binding.models" in all_models.IMPORTED_MODEL_MODULE_NAMES
    from pitchlog.db.writer_binding import models

    assert models.writer_bindings is WriterBinding.__table__
    assert models.writer_admissions is WriterAdmission.__table__
    assert Base.metadata.tables["sync_fence.writer_bindings"] is models.writer_bindings
    assert (
        Base.metadata.tables["sync_fence.writer_admissions"] is models.writer_admissions
    )
