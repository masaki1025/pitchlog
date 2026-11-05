"""非play評価の独立印。play行/D2を偽造せず同TXへ閉じる。"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from pitchlog.db.base import Base
from pitchlog.db.mixins import LifecycleMixin
from pitchlog.db.writer_binding.ordinary_models import _immutability, _lifecycle
from pitchlog.sync.control_provider.writer_binding_models import WriterBinding

# 値の意味は既binding原典。別の識別/採番を作らず同じ型/nullableを複製する。
_IDENTITY = (
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
)
_MUTABLE = frozenset(
    {
        "state",
        "frame_id",
        "frame_digest",
        "artifact_sha256",
        "source_event_id",
        "source_d1",
        "target_event_id",
        "target_generation",
        "target_d1",
        "target_play_id",
        "checkpoint_id",
        "checkpoint_revision",
        "checkpoint_digest",
        "preparation_json",
        "preparation",
        "consumed_at",
    }
)


class NonplayWriteAdmission(LifecycleMixin, Base):
    """真正device/right→評価→一回consumeの不可分原本。"""

    __table__ = Table(
        "nonplay_write_admissions",
        Base.metadata,
        *(
            Column(name, WriterBinding.__table__.c[name].type.copy(), nullable=False)
            for name in _IDENTITY
        ),
        Column("state", Text, nullable=False),
        Column("frame_id", Uuid),
        Column("frame_digest", Text),
        Column("artifact_sha256", Text),
        Column("source_event_id", Uuid),
        Column("source_d1", BigInteger),
        Column("target_event_id", Uuid),
        Column("target_generation", BigInteger),
        Column("target_d1", BigInteger),
        Column("target_play_id", Uuid),
        Column("checkpoint_id", Uuid),
        Column("checkpoint_revision", BigInteger),
        Column("checkpoint_digest", Text),
        Column("preparation_json", Text),
        Column("preparation", JSONB),
        Column("consumed_at", DateTime(timezone=True)),
        PrimaryKeyConstraint("tenant_id", "attempt_id", "phase_id"),
        UniqueConstraint("tenant_id", "frame_id"),
        UniqueConstraint("tenant_id", "source_event_id"),
        ForeignKeyConstraint(
            ["tenant_id", "attempt_id", "phase_id"],
            [
                "sync_fence.writer_bindings.tenant_id",
                "sync_fence.writer_bindings.attempt_id",
                "sync_fence.writer_bindings.phase_id",
            ],
            match="FULL",
            ondelete="NO ACTION",
            name="fk_nonplay_admission_binding",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            ondelete="NO ACTION",
            name="fk_nonplay_admission_game",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
            name="fk_nonplay_admission_event",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            ondelete="NO ACTION",
            name="fk_nonplay_admission_target",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_play_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            ondelete="NO ACTION",
            name="fk_nonplay_admission_target_play",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "checkpoint_id"],
            [
                "sync_fence.ordinary_pitch_checkpoints.tenant_id",
                "sync_fence.ordinary_pitch_checkpoints.id",
            ],
            ondelete="NO ACTION",
            name="fk_nonplay_admission_checkpoint",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "internal_generation", "source_d1"],
            [
                "event_slots.tenant_id",
                "event_slots.game_id",
                "event_slots.generation",
                "event_slots.d1",
            ],
            ondelete="NO ACTION",
            name="fk_nonplay_admission_source_slot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "target_generation", "target_d1"],
            [
                "event_slots.tenant_id",
                "event_slots.game_id",
                "event_slots.generation",
                "event_slots.d1",
            ],
            ondelete="NO ACTION",
            name="fk_nonplay_admission_target_slot",
        ),
        CheckConstraint(
            (
                "state IN "
                "('device_verified','right_verified','evaluated','consumed','invalid')"
            ),
            name="ck_nonplay_admission_state",
        ),
        CheckConstraint(
            (
                "control_version>0 AND internal_generation>0 AND "
                "recovery_generation>0 AND codec_version=1 AND backend_pid>0"
            ),
            name="ck_nonplay_admission_identity",
        ),
        CheckConstraint(
            "octet_length(nonce_digest)=32", name="ck_nonplay_admission_nonce"
        ),
        CheckConstraint(
            (
                "transaction_id ~ '^[1-9][0-9]{0,19}$' AND transaction_id !~ "
                "'[^0-9]' AND transaction_id::numeric<=18446744073709551615"
            ),
            name="ck_nonplay_admission_xid8",
        ),
        CheckConstraint(
            (
                "request_fingerprint ~ '^(wire-request-v1:)?[a-f0-9]{64}$' AND "
                "octet_length(request_fingerprint) IN (64,80) AND "
                "event_fingerprint ~ '^(wire-v1:)?[a-f0-9]{64}$' AND "
                "octet_length(event_fingerprint) IN (64,72)"
            ),
            name="ck_nonplay_admission_fingerprints",
        ),
        CheckConstraint(
            "(state='consumed')=(consumed_at IS NOT NULL)",
            name="ck_nonplay_admission_consumed",
        ),
        CheckConstraint(
            (
                "state NOT IN ('evaluated','consumed') OR (frame_id IS NOT NULL "
                "AND frame_digest IS NOT NULL AND artifact_sha256 IS NOT NULL AND "
                "source_event_id IS NOT NULL AND source_d1 IS NOT NULL AND "
                "source_d1>0 AND target_event_id IS NOT NULL AND target_generation"
                " IS NOT NULL AND target_generation>0 AND target_d1 IS NOT NULL "
                "AND target_d1>0 AND target_play_id IS NOT NULL AND checkpoint_id "
                "IS NOT NULL AND checkpoint_revision IS NOT NULL AND "
                "checkpoint_revision>0 AND checkpoint_digest IS NOT NULL AND "
                "preparation_json IS NOT NULL AND preparation IS NOT NULL)"
            ),
            name="ck_nonplay_admission_evaluated",
        ),
        CheckConstraint(
            (
                "state NOT IN ('evaluated','consumed') OR (frame_digest ~ "
                "'^[a-f0-9]{64}$' AND octet_length(frame_digest)=64 AND "
                "artifact_sha256 ~ '^[a-f0-9]{64}$' AND "
                "octet_length(artifact_sha256)=64 AND checkpoint_digest ~ "
                "'^[a-f0-9]{64}$' AND octet_length(checkpoint_digest)=64 AND "
                "jsonb_typeof(preparation)='object')"
            ),
            name="ck_nonplay_admission_values",
        ),
        Index(
            "uq_nonplay_consumed_target",
            "tenant_id",
            "game_id",
            "target_event_id",
            unique=True,
            postgresql_where=text("state = 'consumed'"),
        ),
        schema="sync_fence",
    )
    lifecycle = _lifecycle()
    immutability = _immutability(__table__, _MUTABLE)
