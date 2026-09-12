"""退避したイベント原本を記録権領域で保持するモデルを定義する。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
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


class EvacuatedEventOriginal(TenantMixin, ImportBatchMixin, LifecycleMixin, Base):
    """記録権の不一致や復元収集で退避したイベント原本を保持する。"""

    __tablename__ = "evacuated_event_originals"
    __table_args__ = (
        CheckConstraint("kind = 'evacuated'"),
        CheckConstraint("origin IN ('authority_mismatch', 'restore_collection')"),
        CheckConstraint(
            "status IN ('pending', 'imported', 'not_imported', 'discarded')"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_evacuated_event_originals_game",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "d5", "kind"],
            [
                "idempotency_ledger.tenant_id",
                "idempotency_ledger.d5",
                "idempotency_ledger.kind",
            ],
            name="fk_evacuated_event_originals_ledger",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "imported_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_evacuated_event_originals_imported_event",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_evacuated_event_originals",
            info={"roles": ("primary_key", "fk_target")},
        ),
        UniqueConstraint(
            "tenant_id",
            "game_id",
            "old_generation",
            "original_d1",
            name="uq_evacuated_event_originals_source",
            info={"roles": ("business_unique",)},
        ),
        UniqueConstraint(
            "tenant_id",
            "d5",
            name="uq_evacuated_event_originals_d5",
            info={"roles": ("business_unique",)},
        ),
        Index(
            "ix_evacuated_event_originals_retention",
            "tenant_id",
            "retention_deadline",
            postgresql_where=text(
                "retention_deadline IS NOT NULL AND discarded_at IS NULL"
            ),
            info={"purpose": "range_sort"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    game_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    old_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_d1: Mapped[int] = mapped_column(BigInteger, nullable=False)
    d5: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'evacuated'")
    )
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    recovered_device: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    imported_event_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    retention_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    discarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {"game_id", "old_generation", "original_d1", "d5", "kind", "origin"}
        ),
        allowed_update_columns=frozenset(
            {"status", "imported_event_id", "retention_deadline", "discarded_at"}
        ),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="TSK-372",
    )


class RecordingGeneration(
    TenantMixin, ImportBatchMixin, RetirementMixin, LifecycleMixin, Base
):
    """試合の記録権世代と確定済み D3 を保持する。"""

    __tablename__ = "recording_generations"
    __table_args__ = (
        CheckConstraint("kind IN ('normal', 'migration')"),
        CheckConstraint("confirmed_watermark >= 0"),
        CheckConstraint("applied_prefix >= 0"),
        CheckConstraint("kind <> 'migration' OR holder_device IS NULL"),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_recording_generations_game",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "game_id",
            "generation",
            name="pk_recording_generations",
            info={"roles": ("primary_key", "fk_target")},
        ),
        Index(
            "uq_recording_generations_current",
            "tenant_id",
            "game_id",
            unique=True,
            postgresql_where=text("kind = 'normal' AND revoked_at IS NULL"),
            info={"roles": ("business_unique",)},
        ),
        Index(
            "uq_recording_generations_migration",
            "tenant_id",
            "game_id",
            unique=True,
            postgresql_where=text("kind = 'migration' AND retired_at IS NULL"),
            info={"roles": ("business_unique",)},
        ),
        UniqueConstraint(
            "tenant_id",
            "game_id",
            "issuance_order",
            name="uq_recording_generations_issuance_order",
            info={"roles": ("business_unique",)},
        ),
    )

    game_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'normal'")
    )
    issuance_order: Mapped[int] = mapped_column(BigInteger, nullable=False)
    holder_device: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_watermark: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    applied_prefix: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.HAS_PREDICATE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {"generation", "kind", "issuance_order", "holder_device", "granted_at"}
        ),
        allowed_update_columns=frozenset(
            {"applied_prefix", "revoked_at", "retired_at"}
        ),
        conditional_update_columns=frozenset({"confirmed_watermark"}),
        coverage=ImmutabilityCoverage.PARTIAL,
        unclassified_handoff="TSK-372",
    )


Index(
    "ix_recording_generations_history",
    RecordingGeneration.__table__.c.tenant_id,
    RecordingGeneration.__table__.c.game_id,
    RecordingGeneration.__table__.c.issuance_order.desc(),
    info={"purpose": "range_sort"},
)
