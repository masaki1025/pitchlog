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
    LargeBinary,
    PrimaryKeyConstraint,
    SmallInteger,
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


class RG1RestoreGate(LifecycleMixin, Base):
    """復元調整中の通常書込みを止める全体共通の単一状態行。"""

    __tablename__ = "rg1_restore_gate"
    __table_args__ = (
        CheckConstraint("singleton_id = 1", name="ck_rg1_restore_gate_singleton_id"),
        CheckConstraint(
            "state IN ('closed', 'open')", name="ck_rg1_restore_gate_state"
        ),
        CheckConstraint(
            "recovery_generation IS NULL OR recovery_generation > 0",
            name="ck_rg1_restore_gate_recovery_generation",
        ),
        PrimaryKeyConstraint(
            "singleton_id",
            name="pk_rg1_restore_gate",
            info={"roles": ("primary_key", "fk_target")},
        ),
    )

    singleton_id: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, autoincrement=False
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    recovery_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset({"singleton_id"}),
        allowed_update_columns=frozenset({"state"}),
        conditional_update_columns=frozenset({"recovery_generation"}),
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
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
        CheckConstraint(
            "proof_digest IS NULL OR octet_length(proof_digest) = 32",
            name="ck_recording_generations_proof_digest",
        ),
        CheckConstraint(
            "recovery_generation IS NULL OR recovery_generation > 0",
            name="ck_recording_generations_recovery_generation",
        ),
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
    proof_digest: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    recovery_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
            {
                "generation",
                "kind",
                "issuance_order",
                "holder_device",
                "granted_at",
                "proof_digest",
                "recovery_generation",
            }
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


class TrustedDevice(TenantMixin, LifecycleMixin, Base):
    """原資格を保持せず、端末資格digestと失効だけを保持する。"""

    __tablename__ = "trusted_devices"
    __table_args__ = (
        PrimaryKeyConstraint(
            "tenant_id",
            "device_id",
            name="pk_trusted_devices",
            info={"roles": ("primary_key", "fk_target")},
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_trusted_devices_tenant",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        CheckConstraint(
            "octet_length(credential_digest) = 32",
            name="ck_trusted_devices_credential_digest",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_trusted_devices_revoked_at",
        ),
    )
    device_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    credential_digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lifecycle = Lifecycle(
        DeletionLifecycle.DISABLED, AppendMode.MUTABLE, MigrationRetirement.NONE
    )
    immutability = Immutability(
        frozenset({"tenant_id", "device_id", "credential_digest", "created_at"}),
        frozenset(),
        ImmutabilityCoverage.EXHAUSTIVE,
        conditional_update_columns=frozenset({"revoked_at"}),
    )


class GameStartRequest(TenantMixin, LifecycleMixin, Base):
    """同一開始要求の端末とserver側要求digestを不変に束縛する。"""

    __tablename__ = "game_start_requests"
    __table_args__ = (
        PrimaryKeyConstraint(
            "tenant_id",
            "game_id",
            "start_request_id",
            name="pk_game_start_requests",
            info={"roles": ("primary_key", "fk_target")},
        ),
        UniqueConstraint(
            "tenant_id",
            "game_id",
            "start_request_id",
            "device_id",
            name="uq_game_start_requests_owner",
            info={"roles": ("fk_target",)},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_game_start_requests_game",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "device_id"],
            ["trusted_devices.tenant_id", "trusted_devices.device_id"],
            name="fk_game_start_requests_device",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        CheckConstraint(
            "octet_length(request_digest) = 32", name="ck_game_start_requests_digest"
        ),
    )
    game_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    start_request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    device_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    lifecycle = Lifecycle(
        DeletionLifecycle.NOT_APPLICABLE,
        AppendMode.APPEND_ONLY,
        MigrationRetirement.NONE,
    )
    immutability = Immutability(
        frozenset(
            {
                "tenant_id",
                "game_id",
                "start_request_id",
                "device_id",
                "request_digest",
                "created_at",
            }
        ),
        frozenset(),
        ImmutabilityCoverage.EXHAUSTIVE,
    )


class GameStartAttempt(TenantMixin, LifecycleMixin, Base):
    """予約前に耐久化し、結果不明をpendingのまま保持する。"""

    __tablename__ = "game_start_attempts"
    __table_args__ = (
        PrimaryKeyConstraint(
            "tenant_id",
            "attempt_id",
            name="pk_game_start_attempts",
            info={"roles": ("primary_key", "fk_target")},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "start_request_id", "device_id"],
            [
                "game_start_requests.tenant_id",
                "game_start_requests.game_id",
                "game_start_requests.start_request_id",
                "game_start_requests.device_id",
            ],
            name="fk_game_start_attempts_request",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        CheckConstraint(
            "outcome IN ('pending', 'committed', 'rolled_back')",
            name="ck_game_start_attempts_outcome",
        ),
        CheckConstraint(
            "(outcome = 'pending' AND resolved_at IS NULL) OR "
            "(outcome <> 'pending' AND resolved_at IS NOT NULL "
            "AND resolved_at >= created_at)",
            name="ck_game_start_attempts_resolution",
        ),
        Index(
            "uq_game_start_attempts_pending",
            "tenant_id",
            "game_id",
            "start_request_id",
            unique=True,
            postgresql_where=text("outcome = 'pending'"),
            info={"roles": ("business_unique",)},
        ),
    )
    attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    game_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    start_request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    device_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outcome: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    lifecycle = Lifecycle(
        DeletionLifecycle.NOT_APPLICABLE, AppendMode.MUTABLE, MigrationRetirement.NONE
    )
    immutability = Immutability(
        frozenset(
            {
                "tenant_id",
                "attempt_id",
                "game_id",
                "start_request_id",
                "device_id",
                "created_at",
            }
        ),
        frozenset(),
        ImmutabilityCoverage.EXHAUSTIVE,
        conditional_update_columns=frozenset({"outcome", "resolved_at"}),
    )


class RecordingRightDelivery(TenantMixin, LifecycleMixin, Base):
    """同一開始要求へだけ再交付する暗号文を不変に保持する。"""

    __tablename__ = "recording_right_deliveries"
    __table_args__ = (
        PrimaryKeyConstraint(
            "tenant_id",
            "game_id",
            "generation",
            name="pk_recording_right_deliveries",
            info={"roles": ("primary_key", "fk_target")},
        ),
        UniqueConstraint(
            "tenant_id",
            "game_id",
            "start_request_id",
            name="uq_recording_right_deliveries_request",
            info={"roles": ("business_unique",)},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "generation"],
            [
                "recording_generations.tenant_id",
                "recording_generations.game_id",
                "recording_generations.generation",
            ],
            name="fk_recording_right_deliveries_generation",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "start_request_id", "device_id"],
            [
                "game_start_requests.tenant_id",
                "game_start_requests.game_id",
                "game_start_requests.start_request_id",
                "game_start_requests.device_id",
            ],
            name="fk_recording_right_deliveries_request",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        CheckConstraint(
            "generation > 0", name="ck_recording_right_deliveries_generation"
        ),
        CheckConstraint("key_id <> ''", name="ck_recording_right_deliveries_key_id"),
        CheckConstraint(
            "octet_length(nonce) = 12 AND octet_length(ciphertext) = 48",
            name="ck_recording_right_deliveries_envelope",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_recording_right_deliveries_revocation",
        ),
    )
    game_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    start_request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    device_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    key_id: Mapped[str] = mapped_column(Text, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lifecycle = Lifecycle(
        DeletionLifecycle.DISABLED, AppendMode.MUTABLE, MigrationRetirement.NONE
    )
    immutability = Immutability(
        frozenset(
            {
                "tenant_id",
                "game_id",
                "generation",
                "start_request_id",
                "device_id",
                "key_id",
                "nonce",
                "ciphertext",
                "created_at",
            }
        ),
        frozenset(),
        ImmutabilityCoverage.EXHAUSTIVE,
        conditional_update_columns=frozenset({"revoked_at"}),
    )
