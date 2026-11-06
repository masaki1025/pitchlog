"""終了再開だけの私有admission/現在head。undoのtarget制約は変更しない。"""

from sqlalchemy import (
    BigInteger,
    Boolean,
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
)
from sqlalchemy.dialects.postgresql import JSONB

from pitchlog.db.base import Base
from pitchlog.db.mixins import LifecycleMixin
from pitchlog.db.writer_binding.nonplay_models import _IDENTITY
from pitchlog.db.writer_binding.ordinary_models import _immutability, _lifecycle
from pitchlog.sync.control_provider.writer_binding_models import WriterBinding


class LifecycleWriteAdmission(LifecycleMixin, Base):
    """同binding/同TX/nonceへ結ぶ専用印。偽play対象を保持しない。"""

    __table__ = Table(
        "lifecycle_write_admissions",
        Base.metadata,
        *(
            Column(n, WriterBinding.__table__.c[n].type.copy(), nullable=False)
            for n in _IDENTITY
        ),
        Column("state", Text, nullable=False),
        Column("frame_id", Uuid),
        Column("frame_digest", Text),
        Column("artifact_sha256", Text),
        Column("source_event_id", Uuid),
        Column("source_d1", BigInteger),
        Column("source_d2", BigInteger),
        Column("checkpoint_id", Uuid),
        Column("checkpoint_revision", BigInteger),
        Column("checkpoint_digest", Text),
        Column("receipt_id", Uuid),
        Column("action", Text),
        Column("preparation_json", Text),
        Column("preparation", JSONB),
        Column("consumed_at", DateTime(timezone=True)),
        PrimaryKeyConstraint("tenant_id", "attempt_id", "phase_id"),
        UniqueConstraint("tenant_id", "frame_id"),
        UniqueConstraint("tenant_id", "source_event_id"),
        UniqueConstraint("tenant_id", "receipt_id"),
        ForeignKeyConstraint(
            ["tenant_id", "attempt_id", "phase_id"],
            [
                "sync_fence.writer_bindings." + n
                for n in ("tenant_id", "attempt_id", "phase_id")
            ],
            name="fk_lifecycle_admission_binding",
            match="FULL",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_lifecycle_admission_game",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_lifecycle_admission_event",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "state IN ('evaluated','consumed')",
            name="ck_lifecycle_admission_state",
        ),
        CheckConstraint(
            (
                "octet_length(nonce_digest)=32 AND internal_generation>0"
                " AND recovery_generation>0 AND codec_version=1"
            ),
            name="ck_lifecycle_admission_identity",
        ),
        CheckConstraint(
            "control_version>0 AND backend_pid>0 AND "
            "transaction_id ~ '^[1-9][0-9]{0,19}$' AND "
            "transaction_id !~ '[^0-9]' AND "
            "transaction_id::numeric<=18446744073709551615",
            name="ck_lifecycle_admission_xid",
        ),
        CheckConstraint(
            "(state='consumed')=(consumed_at IS NOT NULL)",
            name="ck_lifecycle_admission_consumed",
        ),
        CheckConstraint(
            (
                "state NOT IN ('evaluated','consumed') OR (frame_id IS N"
                "OT NULL AND frame_digest IS NOT NULL AND artifact_sha25"
                "6 IS NOT NULL AND source_event_id IS NOT NULL AND sourc"
                "e_d1 IS NOT NULL AND source_d1>0 AND source_d2 IS NOT N"
                "ULL AND source_d2>=0 AND checkpoint_id IS NOT NULL AND "
                "checkpoint_revision IS NOT NULL AND checkpoint_revision"
                ">0 AND checkpoint_digest IS NOT NULL AND receipt_id IS "
                "NOT NULL AND action IS NOT NULL AND action IN ('end','r"
                "eopen') AND preparation_json IS NOT NULL AND preparatio"
                "n IS NOT NULL)"
            ),
            name="ck_lifecycle_admission_evaluated",
        ),
        CheckConstraint(
            (
                "state NOT IN ('evaluated','consumed') OR (frame_digest "
                "~ '^[a-f0-9]{64}$' AND octet_length(frame_digest)=64 AN"
                "D artifact_sha256 ~ '^[a-f0-9]{64}$' AND octet_length(a"
                "rtifact_sha256)=64 AND checkpoint_digest ~ '^[a-f0-9]{6"
                "4}$' AND octet_length(checkpoint_digest)=64 AND jsonb_t"
                "ypeof(preparation)='object')"
            ),
            name="ck_lifecycle_admission_values",
        ),
        Index(
            "ix_lifecycle_game_source",
            "tenant_id",
            "game_id",
            "internal_generation",
            "source_d1",
        ),
        schema="sync_fence",
    )
    lifecycle = _lifecycle()
    immutability = _immutability(__table__, frozenset({"state", "consumed_at"}))


class GameLifecycleHead(LifecycleMixin, Base):
    """状態と最新終了確定版pointer。同eventの再送は新versionを発行しない。"""

    __table__ = Table(
        "game_lifecycle_heads",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("last_version", BigInteger, nullable=False),
        Column("is_finished", Boolean, nullable=False),
        Column("active_end_event_id", Uuid),
        Column("active_receipt_id", Uuid),
        Column("active_stats_version_id", Uuid),
        Column("last_control_event_id", Uuid, nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        PrimaryKeyConstraint("tenant_id", "game_id"),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_lifecycle_head_game",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "last_control_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_lifecycle_head_control",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "active_end_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_lifecycle_head_end",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "active_stats_version_id"],
            [
                "sync_fence.stats_fact_versions.tenant_id",
                "sync_fence.stats_fact_versions.game_id",
                "sync_fence.stats_fact_versions.id",
            ],
            name="fk_lifecycle_head_stats",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("last_version>0", name="ck_lifecycle_head_version"),
        CheckConstraint(
            (
                "(is_finished AND active_end_event_id IS NOT NULL AND ac"
                "tive_receipt_id IS NOT NULL AND active_stats_version_id"
                " IS NOT NULL) OR (NOT is_finished AND active_end_event_"
                "id IS NULL AND active_receipt_id IS NULL AND active_sta"
                "ts_version_id IS NULL)"
            ),
            name="ck_lifecycle_head_active",
        ),
        schema="sync_fence",
    )
    lifecycle = _lifecycle()
    immutability = _immutability(
        __table__,
        frozenset(
            {
                "last_version",
                "is_finished",
                "active_end_event_id",
                "active_receipt_id",
                "active_stats_version_id",
                "last_control_event_id",
                "updated_at",
            }
        ),
    )
