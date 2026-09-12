"""ORM モデル共通 mixin と表単位メタデータを単体検査する。"""

from __future__ import annotations

from dataclasses import MISSING, fields, replace
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
    ImmutabilityCoverage,
    Lifecycle,
    MigrationRetirement,
    is_task_handoff_id,
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
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
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


@pytest.mark.parametrize(
    ("protected", "allowed", "conditional"),
    (
        (frozenset({"state"}), frozenset({"state"}), frozenset()),
        (frozenset({"state"}), frozenset(), frozenset({"state"})),
        (frozenset(), frozenset({"state"}), frozenset({"state"})),
    ),
    ids=("protected-allowed", "protected-conditional", "allowed-conditional"),
)
def test_immutability_metadata_rejects_overlapping_columns(
    protected: frozenset[str],
    allowed: frozenset[str],
    conditional: frozenset[str],
) -> None:
    """不変列マトリクスの 3 集合を相互に重複させられないことを検査する。"""
    assert _LifecycleModel.immutability == Immutability(
        protected_columns=frozenset({"id"}),
        allowed_update_columns=frozenset(),
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
    )

    with pytest.raises(ValueError, match="不変列マトリクスの分類が重複している: state"):
        Immutability(
            protected_columns=protected,
            allowed_update_columns=allowed,
            conditional_update_columns=conditional,
            coverage=ImmutabilityCoverage.EXHAUSTIVE,
        )


def test_immutability_metadata_requires_explicit_coverage() -> None:
    """被覆状態に既定値がなく、新しい表で明示宣言が必要なことを検査する。"""
    coverage_field = next(
        field for field in fields(Immutability) if field.name == "coverage"
    )

    assert coverage_field.default is MISSING
    assert coverage_field.default_factory is MISSING


def test_partial_immutability_requires_unclassified_handoff() -> None:
    """部分被覆に未分類列の受け取り先がなければ拒否する。"""
    with pytest.raises(ValueError, match="部分被覆には未分類列の受け取り先が必要"):
        Immutability(
            protected_columns=frozenset(),
            allowed_update_columns=frozenset(),
            coverage=ImmutabilityCoverage.PARTIAL,
        )


def test_exhaustive_immutability_rejects_unclassified_handoff() -> None:
    """全列分類済みに未分類列の受け取り先があれば拒否する。"""
    with pytest.raises(
        ValueError, match="全列分類済みに未分類列の受け取り先は指定できない"
    ):
        Immutability(
            protected_columns=frozenset(),
            allowed_update_columns=frozenset(),
            coverage=ImmutabilityCoverage.EXHAUSTIVE,
            unclassified_handoff="TSK-372",
        )


def test_partial_immutability_rejects_non_task_handoff_id() -> None:
    """部分被覆の受け取り先に仮文字列を指定した負例を拒否する。"""
    with pytest.raises(ValueError, match=r"TSK-<数字> 形式"):
        Immutability(
            protected_columns=frozenset(),
            allowed_update_columns=frozenset(),
            coverage=ImmutabilityCoverage.PARTIAL,
            unclassified_handoff="follow-up-A",
        )

    assert is_task_handoff_id("TSK-372")
    assert not is_task_handoff_id("follow-up-A")


def test_test_models_do_not_modify_production_metadata() -> None:
    """テスト専用モデルが製品 Base.metadata に登録されないことを検査する。"""
    assert _TestBase.metadata is not Base.metadata
    assert set(_TestBase.metadata.tables).isdisjoint(Base.metadata.tables)
