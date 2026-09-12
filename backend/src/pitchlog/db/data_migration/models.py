"""隔離領域・移行元最終オーダー・移行レポートのモデルを定義する。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    PrimaryKeyConstraint,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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
)


class MigrationQuarantine(ImportBatchMixin, LifecycleMixin, Base):
    """正規化できない移行元の行を原本のまま隔離する。

    raw ペイロードの内容へ意味制約・FK・CHECK を掛けない。
    取り込み単位の識別子と技術的 PK は raw 内容への制約ではないので許す。
    """

    __tablename__ = "migration_quarantine"
    __table_args__ = (
        ForeignKeyConstraint(
            ["import_batch_id"],
            ["migration_runs.id"],
            name="fk_migration_quarantine_run",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "id",
            name="pk_migration_quarantine",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "ix_migration_quarantine_source",
            "import_batch_id",
            "source_read_order",
            info={"purpose": "lookup"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    import_batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_read_order: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.APPEND_ONLY,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {"id", "import_batch_id", "source_read_order", "raw_payload"}
        ),
        allowed_update_columns=frozenset(),
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
    )


class MigratedFinalLineup(
    TenantMixin, ImportBatchMixin, RetirementMixin, LifecycleMixin, Base
):
    """移行元の最終オーダーを未解決の原文として保持する。"""

    __tablename__ = "migrated_final_lineups"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_migrated_final_lineups_game",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_migrated_final_lineups_team",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_migrated_final_lineups",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "uq_migrated_final_lineups_active",
            "tenant_id",
            "game_id",
            "team_record_id",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
            info={"roles": ("business_unique",)},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    game_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    team_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    raw_lineup: Mapped[str] = mapped_column(Text, nullable=False)
    legacy_row_identifier: Mapped[str] = mapped_column(Text, nullable=False)
    import_batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.HAS_PREDICATE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {
                "game_id",
                "team_record_id",
                "raw_lineup",
                "legacy_row_identifier",
                "import_batch_id",
            }
        ),
        allowed_update_columns=frozenset({"retired_at"}),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="follow-up-A",
    )


class MigrationRun(RetirementMixin, LifecycleMixin, Base):
    """全テナント横断の移行結果と検証状況を保持する。"""

    __tablename__ = "migration_runs"
    __table_args__ = (
        CheckConstraint("completed_at IS NULL OR completed_at >= started_at"),
        PrimaryKeyConstraint(
            "id",
            name="pk_migration_runs",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_counts: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    generated_copy_counts: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False
    )
    validation_results: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"id", "started_at", "source_counts"}),
        allowed_update_columns=frozenset(
            {
                "completed_at",
                "generated_copy_counts",
                "validation_results",
                "retired_at",
            }
        ),
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
    )


Index(
    "ix_migration_runs_time",
    MigrationRun.__table__.c.started_at.desc(),
    MigrationRun.__table__.c.id.desc(),
    info={"purpose": "range_sort"},
)


class MigrationResolutionReport(ImportBatchMixin, LifecycleMixin, Base):
    """移行元の値を解決できなかった事実を追記専用で保持する。"""

    __tablename__ = "migration_resolution_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["import_batch_id"],
            ["migration_runs.id"],
            name="fk_migration_resolution_reports_run",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "id",
            name="pk_migration_resolution_reports",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "ix_migration_resolution_reports_run",
            "import_batch_id",
            "source_kind",
            "id",
            info={"purpose": "lookup"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    import_batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    legacy_row_identifier: Mapped[str] = mapped_column(Text, nullable=False)
    issue: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.APPEND_ONLY,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {"id", "import_batch_id", "source_kind", "legacy_row_identifier", "issue"}
        ),
        allowed_update_columns=frozenset(),
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
    )


class MigrationWarningReport(ImportBatchMixin, LifecycleMixin, Base):
    """移行元の重複や変換時の警告を追記専用で保持する。

    移行元の重複は 1 行に潰さず 2 行として取り込み、
    重複の事実は警告レポートに記録する。DB は重複を拒否しない。
    """

    __tablename__ = "migration_warning_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["import_batch_id"],
            ["migration_runs.id"],
            name="fk_migration_warning_reports_run",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "id",
            name="pk_migration_warning_reports",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "ix_migration_warning_reports_run",
            "import_batch_id",
            "warning_kind",
            "id",
            info={"purpose": "lookup"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    import_batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    legacy_row_identifier: Mapped[str] = mapped_column(Text, nullable=False)
    warning_kind: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.FOLLOWS_PARENT,
        append_mode=AppendMode.APPEND_ONLY,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {
                "id",
                "import_batch_id",
                "source_kind",
                "legacy_row_identifier",
                "warning_kind",
                "details",
            }
        ),
        allowed_update_columns=frozenset(),
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
    )
