"""同期writerの資格原本と同一取引admissionを保持する。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from pitchlog.db.base import Base
from pitchlog.db.mixins import LifecycleMixin
from pitchlog.db.model_metadata import (
    AppendMode,
    DeletionLifecycle,
    Immutability,
    ImmutabilityCoverage,
    Lifecycle,
    MigrationRetirement,
)


class WriterBinding(LifecycleMixin, Base):
    """外部leaseと実writerへ固定し、入口の閉鎖だけを許す原本。"""

    __tablename__ = "writer_bindings"
    __table_args__ = (
        PrimaryKeyConstraint(
            "tenant_id",
            "attempt_id",
            "phase_id",
            name="pk_sync_writer_bindings",
            info={"roles": ("primary_key", "fk_target")},
        ),
        UniqueConstraint(
            "lease_id",
            name="uq_sync_writer_binding_lease",
            info={"roles": ("business_unique",)},
        ),
        UniqueConstraint(
            "nonce_digest",
            name="uq_sync_writer_binding_nonce",
            info={"roles": ("business_unique",)},
        ),
        CheckConstraint(
            "state IN ('open','closed') AND ((state='open' AND close_id IS "
            "NULL) OR (state='closed' AND close_id IS NOT NULL))",
            name="ck_sync_writer_binding_state",
        ),
        CheckConstraint(
            "octet_length(nonce_digest)=32", name="ck_sync_writer_binding_nonce"
        ),
        CheckConstraint(
            "control_version>0 AND internal_generation>0 AND "
            "recovery_generation>0 AND codec_version>0 AND backend_pid>0",
            name="ck_sync_writer_binding_positive",
        ),
        CheckConstraint(
            "transaction_id ~ '^[1-9][0-9]{0,19}$' AND transaction_id::numeric"
            " <= 18446744073709551615",
            name="ck_sync_writer_binding_xid8",
        ),
        CheckConstraint(
            "wire_d4<>'' AND request_fingerprint<>'' AND event_fingerprint<>''"
            " AND system_identifier<>'' AND database_oid<>''",
            name="ck_sync_writer_binding_text",
        ),
        ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_sync_writer_binding_tenant",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ("tenant_id", "game_id"),
            ("games.tenant_id", "games.id"),
            name="fk_sync_writer_binding_game",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        {"schema": "sync_fence"},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    phase_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    authority_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    control_instance: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    business_instance: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    restore_epoch: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    control_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issuer: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    lease_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    device_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    game_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    wire_d4: Mapped[str] = mapped_column(Text, nullable=False)
    internal_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recovery_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    codec_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    d5: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    system_identifier: Mapped[str] = mapped_column(Text, nullable=False)
    database_oid: Mapped[str] = mapped_column(Text, nullable=False)
    postmaster_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    backend_pid: Mapped[int] = mapped_column(Integer, nullable=False)
    backend_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    transaction_id: Mapped[str] = mapped_column(Text, nullable=False)
    nonce_digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    close_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            [
                "tenant_id",
                "attempt_id",
                "phase_id",
                "authority_id",
                "control_instance",
                "business_instance",
                "restore_epoch",
                "control_version",
                "issuer",
                "lease_id",
                "device_id",
                "game_id",
                "wire_d4",
                "internal_generation",
                "recovery_generation",
                "codec_version",
                "request_fingerprint",
                "d5",
                "event_fingerprint",
                "system_identifier",
                "database_oid",
                "postmaster_started_at",
                "backend_pid",
                "backend_start",
                "transaction_id",
                "nonce_digest",
                "expires_at",
            ]
        ),
        allowed_update_columns=frozenset(),
        conditional_update_columns=frozenset({"state", "close_id"}),
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
    )


class WriterAdmission(LifecycleMixin, Base):
    """同一業務取引でのみ作る入口通過行。業務成功結果ではない。"""

    __tablename__ = "writer_admissions"
    __table_args__ = (
        PrimaryKeyConstraint(
            "tenant_id",
            "attempt_id",
            "phase_id",
            name="pk_sync_writer_admissions",
            info={"roles": ("primary_key",)},
        ),
        ForeignKeyConstraint(
            ("tenant_id", "attempt_id", "phase_id"),
            (
                "sync_fence.writer_bindings.tenant_id",
                "sync_fence.writer_bindings.attempt_id",
                "sync_fence.writer_bindings.phase_id",
            ),
            name="fk_sync_writer_admission_binding",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        CheckConstraint(
            "transaction_id ~ '^[1-9][0-9]{0,19}$' AND transaction_id::numeric"
            " <= 18446744073709551615",
            name="ck_sync_writer_admission_xid8",
        ),
        {"schema": "sync_fence"},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    phase_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    lease_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    transaction_id: Mapped[str] = mapped_column(Text, nullable=False)

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.APPEND_ONLY,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=frozenset(
            {"tenant_id", "attempt_id", "phase_id", "lease_id", "transaction_id"}
        ),
        allowed_update_columns=frozenset(),
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
    )


class FirstBallWriteAdmission(LifecycleMixin, Base):
    """未適用の初球書込印。順序付き成功証跡と一回consumeだけを保持する。"""

    __tablename__ = "first_ball_write_admissions"
    __table_args__ = (
        PrimaryKeyConstraint(
            "tenant_id",
            "attempt_id",
            "phase_id",
            name="pk_first_ball_write_admissions",
            info={"roles": ("primary_key",)},
        ),
        ForeignKeyConstraint(
            ("tenant_id", "attempt_id", "phase_id"),
            (
                "sync_fence.writer_bindings.tenant_id",
                "sync_fence.writer_bindings.attempt_id",
                "sync_fence.writer_bindings.phase_id",
            ),
            name="fk_first_ball_write_admission_binding",
            match="FULL",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ("tenant_id", "source_event_id"),
            ("operation_events.tenant_id", "operation_events.id"),
            name="fk_first_ball_write_admission_event",
            match="SIMPLE",
            ondelete="NO ACTION",
            info={"cross_tenant": False},
        ),
        ForeignKeyConstraint(
            ("tenant_id", "play_row_id"),
            ("play_rows.tenant_id", "play_rows.id"),
            name="fk_first_ball_write_admission_projection",
            match="SIMPLE",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
            info={"cross_tenant": False},
        ),
        CheckConstraint(
            "state IN ('device_verified','right_verified','invalid','consumed') AND "
            "((state='consumed' AND source_event_id IS NOT NULL AND p"
            "lay_row_id IS NOT NULL "
            "AND consumed_at IS NOT NULL) OR (state<>'consumed' AND s"
            "ource_event_id IS NULL "
            "AND play_row_id IS NULL AND consumed_at IS NULL))",
            name="ck_first_ball_write_state",
        ),
        CheckConstraint(
            "octet_length(nonce_digest)=32", name="ck_first_ball_write_nonce"
        ),
        CheckConstraint(
            "control_version>0 AND internal_generation>0 AND recovery_generation>0 "
            "AND codec_version>0 AND backend_pid>0",
            name="ck_first_ball_write_positive",
        ),
        CheckConstraint(
            "transaction_id ~ '^[1-9][0-9]{0,19}$' AND transaction_id::numeric"
            " <= 18446744073709551615",
            name="ck_first_ball_write_xid8",
        ),
        CheckConstraint(
            "wire_d4<>'' AND request_fingerprint<>'' AND event_fingerprint<>''"
            " AND system_identifier<>'' AND database_oid<>''",
            name="ck_first_ball_write_text",
        ),
        {"schema": "sync_fence"},
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    phase_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    authority_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    control_instance: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    business_instance: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    restore_epoch: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    control_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issuer: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    lease_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    device_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    game_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    wire_d4: Mapped[str] = mapped_column(Text, nullable=False)
    internal_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recovery_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    codec_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    d5: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    system_identifier: Mapped[str] = mapped_column(Text, nullable=False)
    database_oid: Mapped[str] = mapped_column(Text, nullable=False)
    postmaster_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    backend_pid: Mapped[int] = mapped_column(Integer, nullable=False)
    backend_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    transaction_id: Mapped[str] = mapped_column(Text, nullable=False)
    nonce_digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    state: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    play_row_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lifecycle = Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )
    immutability = Immutability(
        protected_columns=WriterBinding.immutability.protected_columns,
        allowed_update_columns=frozenset(),
        conditional_update_columns=frozenset(
            {"state", "source_event_id", "play_row_id", "consumed_at"}
        ),
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
    )
