"""データ移行領域の隔離モデルを定義する。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, Index, LargeBinary, PrimaryKeyConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from pitchlog.db.base import Base
from pitchlog.db.mixins import ImportBatchMixin, LifecycleMixin
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
