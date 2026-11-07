"""旧試行の後着適用を永久遮断する0046原本の私有モデル。"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    Table,
    Text,
    Uuid,
)

from pitchlog.db.base import Base


class SyncAttemptRetirement(Base):
    """更新・削除しない試行識別。一般の試合状態や資格を保存しない。"""

    __table__ = Table(
        "attempt_retirements",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("attempt_id", Uuid, nullable=False),
        Column("device_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("d5", Uuid, nullable=False),
        Column("authority_id", Uuid, nullable=False),
        Column("wire_d4", Text, nullable=False),
        Column("codec_version", BigInteger, nullable=False),
        Column("request_fingerprint", Text, nullable=False),
        Column("event_fingerprint", Text, nullable=False),
        Column("recovery_generation", BigInteger, nullable=False),
        CheckConstraint(
            "wire_d4<>'' AND request_fingerprint<>'' AND event_fingerprint<>''",
            name="ck_sync_attempt_retirement_text",
        ),
        CheckConstraint(
            "codec_version>0 AND recovery_generation>0",
            name="ck_sync_attempt_retirement_positive",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_sync_attempt_retirement_game",
            ondelete="NO ACTION",
            match="FULL",
        ),
        PrimaryKeyConstraint(
            "tenant_id", "attempt_id", name="pk_sync_attempt_retirements"
        ),
        schema="sync_fence",
        info={"append_only": True},
    )
