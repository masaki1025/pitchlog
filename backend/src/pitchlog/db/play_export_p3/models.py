"""過去訂正capsuleの全D1に対応するCSV原本を宣言する。"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from pitchlog.db.base import Base


class PlayExportP3Snapshot(Base):
    """同一TXのcapsule/itemと版に束縛された追記専用の出力原本。"""

    __table__ = Table(
        "play_export_p3_snapshots",
        Base.metadata,
        Column("tenant_id", Uuid, nullable=False),
        Column("game_id", Uuid, nullable=False),
        Column("internal_generation", BigInteger, nullable=False),
        Column("capsule_id", Uuid, nullable=False),
        Column("d1", BigInteger, nullable=False),
        Column("original_play_row_id", Uuid, nullable=False),
        Column("effective_event_id", Uuid, nullable=False),
        Column("effective_play_row_id", Uuid, nullable=False),
        Column("play_row_version", BigInteger, nullable=False),
        Column("item_digest", Text, nullable=False),
        Column("capsule_source_set_digest", Text, nullable=False),
        Column("capsule_stats_version_id", Uuid, nullable=False),
        Column("plays_csv_json", JSONB, nullable=False),
        Column("full_innings_json", JSONB, nullable=False),
        Column("runner_rows_json", JSONB, nullable=False),
        Column("reference_json", JSONB, nullable=True),
        Column(
            "captured_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=text("pg_catalog.clock_timestamp()"),
        ),
        PrimaryKeyConstraint(
            "tenant_id",
            "game_id",
            "internal_generation",
            "capsule_id",
            "d1",
            name="play_export_p3_snapshots_pkey",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "internal_generation", "capsule_id", "d1"],
            [
                f"sync_fence.p3_projection_capsule_items.{c}"
                for c in (
                    "tenant_id",
                    "game_id",
                    "internal_generation",
                    "capsule_id",
                    "d1",
                )
            ],
            name="fk_play_export_p3_item",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "original_play_row_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            name="fk_play_export_p3_original",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "effective_play_row_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            name="fk_play_export_p3_effective",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "effective_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_play_export_p3_event",
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "game_id", "capsule_stats_version_id"],
            [
                f"sync_fence.stats_fact_versions.{c}"
                for c in ("tenant_id", "game_id", "id")
            ],
            name="fk_play_export_p3_stats",
            ondelete="NO ACTION",
        ),
        *[
            CheckConstraint(condition, name=f"ck_play_export_p3_{name}")
            for name, condition in (
                ("generation", "internal_generation > 0"),
                ("d1", "d1 > 0"),
                ("version", "play_row_version > 0"),
                ("item_digest", "item_digest ~ '^[a-f0-9]{64}$'"),
                ("source_digest", "capsule_source_set_digest ~ '^[a-f0-9]{64}$'"),
                ("plays", "jsonb_typeof(plays_csv_json) = 'object'"),
                ("innings", "jsonb_typeof(full_innings_json) = 'array'"),
                ("runners", "jsonb_typeof(runner_rows_json) = 'array'"),
                (
                    "reference",
                    "reference_json IS NULL OR jsonb_typeof(reference_json) = 'object'",
                ),
            )
        ],
        schema="sync_fence",
        info={"append_only": True, "storage_owner": "pitchlog_owner"},
    )
