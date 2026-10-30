"""通常投球の独立資格・現在checkpoint・有限履歴のprivate原本。"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

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
from pitchlog.sync.control_provider.writer_binding_models import WriterBinding


def _lifecycle(append: bool = False) -> Lifecycle:
    """private原本を物理削除せず保持する。"""
    return Lifecycle(
        deletion=DeletionLifecycle.NOT_APPLICABLE,
        append_mode=AppendMode.APPEND_ONLY if append else AppendMode.MUTABLE,
        migration_retirement=MigrationRetirement.NONE,
    )


def _immutability(table: Table, mutable: frozenset[str]) -> Immutability:
    """可変列だけを閉列挙する。"""
    return Immutability(
        protected_columns=frozenset(table.c.keys()) - mutable,
        allowed_update_columns=frozenset(),
        conditional_update_columns=mutable,
        coverage=ImmutabilityCoverage.EXHAUSTIVE,
    )


class OrdinaryPitchCheckpoint(LifecycleMixin, Base):
    """同game/current世代の現在値。実admission消費と不可分に更新する。"""

    __table__ = Table(
        "ordinary_pitch_checkpoints",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("internal_generation", BigInteger, nullable=False),
        Column("id", Uuid, nullable=False),
        Column("revision", BigInteger, nullable=False),
        Column("history_version", BigInteger, nullable=False),
        Column("recovery_generation", BigInteger, nullable=False),
        Column("confirmed_watermark", BigInteger, nullable=False),
        Column("applied_watermark", BigInteger, nullable=False),
        Column("content_digest", Text, nullable=False),
        Column("content", JSONB, nullable=False),
        Column("roster", JSONB, nullable=False),
        Column("state", Text, nullable=False),
        Column("saved_at", DateTime(timezone=True), nullable=False),
        PrimaryKeyConstraint("tenant_id", "game_id", "internal_generation"),
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            ondelete="NO ACTION",
        ),
        CheckConstraint(
            "internal_generation>0 AND revision>0 AND history_version>0 "
            "AND recovery_generation>0 AND confirmed_watermark>=0 "
            "AND confirmed_watermark=applied_watermark",
            name="ck_ordinary_checkpoint_positions",
        ),
        CheckConstraint(
            "state IN ('current','invalidated')", name="ck_ordinary_checkpoint_state"
        ),
        CheckConstraint(
            "content_digest ~ '^[a-f0-9]{64}$' AND octet_length(content_digest)=64",
            name="ck_ordinary_checkpoint_digest",
        ),
        CheckConstraint(
            "jsonb_typeof(content)='object' AND jsonb_typeof(roster)='object'",
            name="ck_ordinary_checkpoint_json",
        ),
        schema="sync_fence",
    )
    lifecycle = _lifecycle()
    immutability = _immutability(
        __table__,
        frozenset(
            {
                "revision",
                "history_version",
                "confirmed_watermark",
                "applied_watermark",
                "content_digest",
                "content",
                "roster",
                "state",
                "saved_at",
            }
        ),
    )


class OrdinaryPitchWriteAdmission(LifecycleMixin, Base):
    """実qualificationとframe/checkpointを同TXで結ぶ独立ordinary資格。"""

    __table__ = Table(
        "ordinary_pitch_write_admissions",
        Base.metadata,
        # 型付きwriter identityだけを再利用し、初球資格表は参照しない。
        *(
            Column(c.name, c.type.copy(), nullable=False)
            for c in WriterBinding.__table__.c
            if c.name not in {"state", "close_id"}
        ),
        Column("state", Text, nullable=False),
        *(
            Column(name, Uuid, nullable=True)
            for name in ("checkpoint_id", "frame_id", "source_event_id", "play_row_id")
        ),
        *(
            Column(name, BigInteger, nullable=True)
            for name in (
                "checkpoint_revision",
                "prefix_length",
                "source_d1",
                "source_d2",
            )
        ),
        *(
            Column(name, Text, nullable=True)
            for name in ("checkpoint_digest", "frame_digest", "artifact_sha256")
        ),
        *(
            Column(name, JSONB, nullable=True)
            for name in (
                "checkpoint_content",
                "next_checkpoint_content",
                "roster_snapshot",
                "history_entry",
                "expected_play_row",
            )
        ),
        Column("consumed_at", DateTime(timezone=True), nullable=True),
        PrimaryKeyConstraint("tenant_id", "attempt_id", "phase_id"),
        UniqueConstraint("tenant_id", "frame_id"),
        UniqueConstraint("tenant_id", "source_event_id"),
        UniqueConstraint("tenant_id", "play_row_id"),
        ForeignKeyConstraint(
            ["tenant_id", "checkpoint_id"],
            [
                "sync_fence.ordinary_pitch_checkpoints.tenant_id",
                "sync_fence.ordinary_pitch_checkpoints.id",
            ],
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "attempt_id", "phase_id"],
            [
                "sync_fence.writer_bindings.tenant_id",
                "sync_fence.writer_bindings.attempt_id",
                "sync_fence.writer_bindings.phase_id",
            ],
            match="FULL",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "play_row_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "state IN ('device_verified','right_verified','evaluated',"
            "'consumed','invalid')",
            name="ck_ordinary_admission_state",
        ),
        CheckConstraint(
            "transaction_id ~ '^[1-9][0-9]{0,19}$' AND "
            "transaction_id !~ '[^0-9]' AND "
            "transaction_id::numeric<=18446744073709551615",
            name="ck_ordinary_admission_xid8",
        ),
        CheckConstraint(
            "octet_length(nonce_digest)=32", name="ck_ordinary_admission_nonce"
        ),
        CheckConstraint(
            "request_fingerprint ~ '^(wire-request-v1:)?[a-f0-9]{64}$' "
            "AND octet_length(request_fingerprint) IN (64,80) "
            "AND event_fingerprint ~ '^(wire-v1:)?[a-f0-9]{64}$' "
            "AND octet_length(event_fingerprint) IN (64,72)",
            name="ck_ordinary_admission_fingerprints",
        ),
        CheckConstraint(
            "state NOT IN ('evaluated','consumed') OR (checkpoint_id IS NOT NULL "
            "AND checkpoint_revision IS NOT NULL AND checkpoint_revision>0 "
            "AND prefix_length IS NOT NULL AND prefix_length>=0 "
            "AND frame_id IS NOT NULL "
            "AND frame_digest IS NOT NULL AND checkpoint_digest IS NOT NULL "
            "AND artifact_sha256 IS NOT NULL AND source_event_id IS NOT NULL "
            "AND source_d1 IS NOT NULL AND source_d1>0 AND source_d2 IS NOT NULL "
            "AND source_d2>=0 "
            "AND play_row_id IS NOT NULL AND checkpoint_content IS NOT NULL "
            "AND next_checkpoint_content IS NOT NULL AND roster_snapshot IS NOT NULL "
            "AND history_entry IS NOT NULL AND expected_play_row IS NOT NULL)",
            name="ck_ordinary_admission_evaluated",
        ),
        CheckConstraint(
            "(state='consumed')=(consumed_at IS NOT NULL)",
            name="ck_ordinary_admission_consumed",
        ),
        CheckConstraint(
            "state NOT IN ('evaluated','consumed') OR ("
            "checkpoint_digest ~ '^[a-f0-9]{64}$' "
            "AND octet_length(checkpoint_digest)=64 "
            "AND frame_digest ~ '^[a-f0-9]{64}$' AND octet_length(frame_digest)=64 "
            "AND artifact_sha256 ~ '^[a-f0-9]{64}$' "
            "AND octet_length(artifact_sha256)=64 "
            "AND jsonb_typeof(checkpoint_content)='object' "
            "AND jsonb_typeof(next_checkpoint_content)='object' "
            "AND jsonb_typeof(roster_snapshot)='object' "
            "AND jsonb_typeof(history_entry)='object' "
            "AND jsonb_typeof(expected_play_row)='object')",
            name="ck_ordinary_admission_values",
        ),
        schema="sync_fence",
    )
    lifecycle = _lifecycle()
    immutability = _immutability(
        __table__,
        frozenset(
            {
                "state",
                "checkpoint_id",
                "checkpoint_revision",
                "checkpoint_digest",
                "prefix_length",
                "frame_id",
                "frame_digest",
                "artifact_sha256",
                "source_event_id",
                "source_d1",
                "source_d2",
                "play_row_id",
                "consumed_at",
                "checkpoint_content",
                "next_checkpoint_content",
                "roster_snapshot",
                "history_entry",
                "expected_play_row",
            }
        ),
    )


class OrdinaryPitchHistory(LifecycleMixin, Base):
    """確定sourceと対応する今回entryだけを持つ有限ページの原本。"""

    __table__ = Table(
        "ordinary_pitch_history",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("internal_generation", BigInteger, nullable=False),
        Column("history_version", BigInteger, nullable=False),
        Column("source_event_id", Uuid, nullable=False),
        Column("d1", BigInteger, nullable=False),
        Column("d2", BigInteger, nullable=False),
        Column("entry", JSONB, nullable=False),
        # 再構築後も旧導出を物理削除せず、同原本の版別履歴を保持する。
        PrimaryKeyConstraint("tenant_id", "source_event_id", "history_version"),
        UniqueConstraint(
            "tenant_id", "game_id", "internal_generation", "history_version", "d1"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "internal_generation>0 AND history_version>0 AND d1>0 AND d2>=0",
            name="ck_ordinary_history_positive",
        ),
        CheckConstraint(
            "jsonb_typeof(entry)='object'", name="ck_ordinary_history_entry"
        ),
        schema="sync_fence",
    )
    lifecycle = _lifecycle(True)
    immutability = _immutability(__table__, frozenset())
