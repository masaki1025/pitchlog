"""0047の保存済み88列と監査keysetを型元へ登録する。"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    Table,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from pitchlog.db.base import Base
from pitchlog.db.game_state.models import PlayRow
from pitchlog.db.sync_protocol.models import OperationEvent


class PlayExportSnapshot(Base):
    """記録TXで確定した投球原本。現在名簿からの再生成を行わない。"""

    __table__ = Table(
        "play_export_snapshots",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("play_row_id", Uuid, nullable=False),
        Column("plays_csv_json", JSONB, nullable=False),
        Column("full_innings_json", JSONB, nullable=False),
        Column("source_event_id", Uuid, nullable=False),
        Column("play_version", BigInteger, nullable=False),
        Column("recording_generation", BigInteger, nullable=False),
        Column("event_sequence", BigInteger, nullable=False),
        Column(
            "captured_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
        ),
        CheckConstraint(
            "play_version > 0", name="play_export_snapshots_play_version_check"
        ),
        CheckConstraint(
            "jsonb_typeof(plays_csv_json) = 'object' AND "
            "jsonb_typeof(full_innings_json) = 'array'",
            name="ck_play_export_snapshot_shapes",
        ),
        PrimaryKeyConstraint(
            "tenant_id", "play_row_id", name="play_export_snapshots_pkey"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="play_export_snapshots_tenant_id_game_id_fkey",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "play_row_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            name="play_export_snapshots_tenant_id_play_row_id_fkey",
            ondelete="NO ACTION",
        ),
        schema="public",
        info={"append_only": True},
    )


snapshot_game_index = Index(
    "ix_play_export_snapshots_game_captured",
    PlayExportSnapshot.__table__.c.tenant_id,
    PlayExportSnapshot.__table__.c.game_id,
    PlayExportSnapshot.__table__.c.captured_at,
    PlayExportSnapshot.__table__.c.play_row_id,
)
play_audit_index = Index(
    "ix_play_rows_export_audit",
    PlayRow.__table__.c.tenant_id,
    PlayRow.__table__.c.game_id,
    PlayRow.__table__.c.play_number,
    PlayRow.__table__.c.id,
)
event_audit_index = Index(
    "ix_operation_events_export_audit",
    OperationEvent.__table__.c.tenant_id,
    OperationEvent.__table__.c.game_id,
    OperationEvent.__table__.c.d2,
    OperationEvent.__table__.c.id,
    postgresql_where=text("ledger_kind = 'accepted'"),
)
