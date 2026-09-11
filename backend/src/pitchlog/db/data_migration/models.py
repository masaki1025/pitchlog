"""隔離領域と移行元最終オーダーのモデルを定義する。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    PrimaryKeyConstraint,
    Text,
    Uuid,
    text,
)
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
    )
