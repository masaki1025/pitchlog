"""ORM モデル共通 mixin と表単位メタデータを単体検査する。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import Column, DateTime, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from pitchlog.db.base import Base
from pitchlog.db.mixins import (
    ImportBatchMixin,
    LifecycleMixin,
    RetirementMixin,
    TenantMixin,
)
from pitchlog.db.model_metadata import (
    AppendMode,
    DeletionLifecycle,
    Immutability,
    Lifecycle,
    MigrationRetirement,
)


class _TestBase(DeclarativeBase):
    """製品 Base.metadata を汚さないテスト専用基底。"""


class _TenantModel(TenantMixin, _TestBase):
    """テナント列 mixin の検査専用モデル。"""

    __tablename__ = "test_tenant_mixin"

    id: Mapped[int] = mapped_column(primary_key=True)


class _LifecycleModel(LifecycleMixin, _TestBase):
    """表単位メタデータの検査専用モデル。"""

    __tablename__ = "test_lifecycle_mixin"

    id: Mapped[int] = mapped_column(primary_key=True)
    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.APPEND_ONLY,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"id"}),
        allowed_update_columns=frozenset(),
    )


class _ImportBatchModel(ImportBatchMixin, _TestBase):
    """取り込みバッチ識別子 mixin の検査専用モデル。"""

    __tablename__ = "test_import_batch_mixin"

    id: Mapped[int] = mapped_column(primary_key=True)


class _RetirementModel(RetirementMixin, _TestBase):
    """退役述語 mixin の検査専用モデル。"""

    __tablename__ = "test_retirement_mixin"

    id: Mapped[int] = mapped_column(primary_key=True)


def _column(table_name: str, column_name: str) -> Column[Any]:
    """テスト専用 metadata から列を返す。"""
    return _TestBase.metadata.tables[table_name].columns[column_name]


def test_tenant_mixin_adds_required_uuid_column() -> None:
    """テナント列が UUID・NOT NULL・既定値なしであることを検査する。"""
    column = _column("test_tenant_mixin", "tenant_id")

    assert isinstance(column.type, Uuid)
    assert column.type.as_uuid
    assert not column.nullable
    assert column.default is None
    assert column.server_default is None


def test_lifecycle_axes_are_independent_and_closed() -> None:
    """ライフサイクルの 3 軸を独立に選べ、値域外を拒否することを検査する。"""
    lifecycle = _LifecycleModel.lifecycle

    assert set(_TestBase.metadata.tables["test_lifecycle_mixin"].columns.keys()) == {
        "id"
    }
    assert lifecycle == Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.APPEND_ONLY,
        migration_retirement=MigrationRetirement.NONE,
    )
    assert replace(lifecycle, deletion=DeletionLifecycle.TRASH).append_mode == (
        AppendMode.APPEND_ONLY
    )
    assert replace(lifecycle, append_mode=AppendMode.MUTABLE).deletion == (
        DeletionLifecycle.NOT_APPLICABLE
    )
    assert (
        replace(
            lifecycle,
            migration_retirement=MigrationRetirement.HAS_PREDICATE,
        ).deletion
        == DeletionLifecycle.NOT_APPLICABLE
    )

    assert {item.value for item in DeletionLifecycle} == {
        "ゴミ箱",
        "非表示",
        "無効化",
        "終了・離脱",
        "対象外",
        "親に従う",
    }
    assert {item.value for item in AppendMode} == {"追記専用", "更新可"}
    assert {item.value for item in MigrationRetirement} == {
        "退役述語を持つ",
        "持たない",
    }
    with pytest.raises(ValueError):
        DeletionLifecycle("削除対象外・追記専用")


def test_import_batch_mixin_adds_optional_uuid_column() -> None:
    """取り込みバッチ列が UUID・NULL 可・既定値なしであることを検査する。"""
    column = _column("test_import_batch_mixin", "import_batch_id")

    assert isinstance(column.type, Uuid)
    assert column.type.as_uuid
    assert column.nullable
    assert column.default is None
    assert column.server_default is None


def test_retirement_mixin_adds_optional_timezone_aware_timestamp() -> None:
    """退役述語が timezone 付き日時・NULL 可・既定値なしであることを検査する。"""
    column = _column("test_retirement_mixin", "retired_at")

    assert isinstance(column.type, DateTime)
    assert column.type.timezone
    assert column.nullable
    assert column.default is None
    assert column.server_default is None


def test_immutability_metadata_rejects_overlapping_columns() -> None:
    """不変列マトリクスで同じ列を保護側と許可側へ置けないことを検査する。"""
    assert _LifecycleModel.immutability == Immutability(
        protected_columns=frozenset({"id"}),
        allowed_update_columns=frozenset(),
    )

    with pytest.raises(ValueError, match="保護列と許可更新列が重複している: state"):
        Immutability(
            protected_columns=frozenset({"state"}),
            allowed_update_columns=frozenset({"state"}),
        )


def test_test_models_do_not_modify_production_metadata() -> None:
    """テスト専用モデルが製品 Base.metadata に登録されないことを検査する。"""
    assert _TestBase.metadata is not Base.metadata
    assert set(_TestBase.metadata.tables).isdisjoint(Base.metadata.tables)
