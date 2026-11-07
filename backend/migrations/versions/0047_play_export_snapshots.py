"""保存済み毎球CSV原本と監査索引を配置し、認可適用前は閉じる。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0047_play_export_snapshots"
down_revision = "0046_sync_attempt_retirement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """原本10列/全制約/3索引を同じmigration transactionへ配置する。"""
    op.create_table(
        "play_export_snapshots",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("play_row_id", sa.Uuid(), nullable=False),
        sa.Column("plays_csv_json", postgresql.JSONB(), nullable=False),
        sa.Column("full_innings_json", postgresql.JSONB(), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("play_version", sa.BigInteger(), nullable=False),
        sa.Column("recording_generation", sa.BigInteger(), nullable=False),
        sa.Column("event_sequence", sa.BigInteger(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("pg_catalog.now()"),
        ),
        sa.CheckConstraint(
            "play_version > 0", name="play_export_snapshots_play_version_check"
        ),
        sa.CheckConstraint(
            "pg_catalog.jsonb_typeof(plays_csv_json) = 'object' AND "
            "pg_catalog.jsonb_typeof(full_innings_json) = 'array'",
            name="ck_play_export_snapshot_shapes",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "play_row_id", name="play_export_snapshots_pkey"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="play_export_snapshots_tenant_id_game_id_fkey",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "play_row_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            name="play_export_snapshots_tenant_id_play_row_id_fkey",
            ondelete="NO ACTION",
        ),
        schema="public",
    )
    op.execute("ALTER TABLE public.play_export_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.play_export_snapshots FORCE ROW LEVEL SECURITY")
    op.execute(
        "REVOKE ALL ON TABLE public.play_export_snapshots FROM PUBLIC,pitchlog_app"
    )
    op.create_index(
        "ix_play_export_snapshots_game_captured",
        "play_export_snapshots",
        ["tenant_id", "game_id", "captured_at", "play_row_id"],
        schema="public",
    )
    op.create_index(
        "ix_play_rows_export_audit",
        "play_rows",
        ["tenant_id", "game_id", "play_number", "id"],
        schema="public",
    )
    op.create_index(
        "ix_operation_events_export_audit",
        "operation_events",
        ["tenant_id", "game_id", "d2", "id"],
        schema="public",
        postgresql_where=sa.text("ledger_kind = 'accepted'"),
    )


def downgrade() -> None:
    """監査原本の物理削除を拒否する。"""
    raise RuntimeError("毎球CSVの記録時原本を物理削除できません")
