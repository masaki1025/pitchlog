"""タイブレーク開始確定の同TX receipt 原本。"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)

from pitchlog.db.base import Base


class TiebreakStartWriteReceipt(Base):
    """対象playを偽造しないタイブレーク開始確定の最小保存印。"""

    __table__ = Table(
        "tiebreak_start_write_receipts",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("attempt_id", Uuid, nullable=False),
        Column("phase_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("source_event_id", Uuid, nullable=False),
        Column("source_d1", BigInteger, nullable=False),
        Column("checkpoint_id", Uuid, nullable=False),
        Column("before_revision", BigInteger, nullable=False),
        Column("after_revision", BigInteger, nullable=False),
        Column("after_digest", Text, nullable=False),
        PrimaryKeyConstraint("tenant_id", "attempt_id", "phase_id"),
        UniqueConstraint("tenant_id", "source_event_id"),
        ForeignKeyConstraint(
            ["tenant_id", "attempt_id", "phase_id"],
            [
                "sync_fence.nonplay_write_admissions.tenant_id",
                "sync_fence.nonplay_write_admissions.attempt_id",
                "sync_fence.nonplay_write_admissions.phase_id",
            ],
            name="tiebreak_receipt_admission_fkey",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="tiebreak_receipt_game_fkey",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="tiebreak_receipt_event_fkey",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "checkpoint_id"],
            [
                "sync_fence.ordinary_pitch_checkpoints.tenant_id",
                "sync_fence.ordinary_pitch_checkpoints.id",
            ],
            name="tiebreak_receipt_checkpoint_fkey",
            ondelete="NO ACTION",
        ),
        CheckConstraint(
            "source_d1>0 AND before_revision>0 AND after_revision=before_revision+1",
            name="ck_tiebreak_start_receipt_sequence",
        ),
        CheckConstraint(
            "after_digest ~ '^[a-f0-9]{64}$'",
            name="ck_tiebreak_start_receipt_digest",
        ),
        schema="sync_fence",
    )
