"""プレイ投影・走者・一時選手 ID 写像を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_play_projections"
down_revision: str | Sequence[str] | None = "0005_sync_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PLAY_ROW_TRIGGER_FUNCTION = "prevent_play_rows_projection_identity_update"
_PLAY_ROW_TRIGGER = "trg_play_rows_projection_identity_immutable"
_PLAYER_MAPPING_TRIGGER_FUNCTION = (
    "prevent_temporary_player_id_mappings_identity_update"
)
_PLAYER_MAPPING_TRIGGER = "trg_temporary_player_id_mappings_identity_immutable"


def upgrade() -> None:
    """3 表と投影・一時 ID 対応の不変性トリガを追加する。"""
    op.create_table(
        "play_rows",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("play_number", sa.BigInteger(), nullable=False),
        sa.Column("event_kind", sa.Text(), nullable=False),
        sa.Column("batter_id", sa.Uuid(), nullable=True),
        sa.Column("pitcher_id", sa.Uuid(), nullable=True),
        sa.Column("catcher_id", sa.Uuid(), nullable=True),
        sa.Column("course_x", sa.Numeric(), nullable=True),
        sa.Column("course_y", sa.Numeric(), nullable=True),
        sa.Column("pitch_speed", sa.Numeric(), nullable=True),
        sa.Column("raw_fielder_position", sa.Integer(), nullable=True),
        sa.Column("resolved_fielder_id", sa.Uuid(), nullable=True),
        sa.Column("raw_error_position", sa.Integer(), nullable=True),
        sa.Column("resolved_error_player_id", sa.Uuid(), nullable=True),
        sa.Column("compatibility_payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "version",
            sa.BigInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_row_identifier", sa.Text(), nullable=True),
        sa.Column(
            "migration_unverified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("event_kind IN ('pitch', 'non_pitch')"),
        sa.CheckConstraint("version > 0"),
        sa.CheckConstraint("course_x IS NULL OR course_x BETWEEN 0 AND 1"),
        sa.CheckConstraint("course_y IS NULL OR course_y BETWEEN 0 AND 1"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_play_rows_game",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_event_id"],
            ["operation_events.tenant_id", "operation_events.id"],
            name="fk_play_rows_event",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_play_rows"),
    )
    op.create_index(
        "ix_play_rows_game_order",
        "play_rows",
        ["tenant_id", "game_id", "play_number", "id"],
        unique=False,
        postgresql_where=sa.text("hidden_at IS NULL"),
    )
    op.create_table(
        "play_runners",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("play_id", sa.Uuid(), nullable=False),
        sa.Column("base", sa.Integer(), nullable=False),
        sa.Column("runner_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("responsible_pitcher_id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("base IN (1, 2, 3)"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "play_id"],
            ["play_rows.tenant_id", "play_rows.id"],
            name="fk_play_runners_play",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "runner_id"],
            ["players.tenant_id", "players.id"],
            name="fk_play_runners_runner",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "responsible_pitcher_id"],
            ["players.tenant_id", "players.id"],
            name="fk_play_runners_pitcher",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_play_runners"),
    )
    op.create_index(
        "uq_play_runners_active",
        "play_runners",
        ["tenant_id", "play_id", "base"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.create_table(
        "temporary_player_id_mappings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("temporary_id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_temporary_player_id_mappings_player",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_temporary_player_id_mappings",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "temporary_id",
            name="uq_temporary_player_id_mappings_temporary",
        ),
    )
    op.execute(
        f"""
        CREATE FUNCTION {_PLAY_ROW_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.id, NEW.source_event_id, NEW.legacy_row_identifier)
               IS DISTINCT FROM
               ROW(OLD.id, OLD.source_event_id, OLD.legacy_row_identifier) THEN
                RAISE EXCEPTION 'play_rows projection identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_PLAY_ROW_TRIGGER}
        BEFORE UPDATE OF id, source_event_id, legacy_row_identifier ON play_rows
        FOR EACH ROW
        EXECUTE FUNCTION {_PLAY_ROW_TRIGGER_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_PLAYER_MAPPING_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.temporary_id, NEW.player_id)
               IS DISTINCT FROM ROW(OLD.temporary_id, OLD.player_id) THEN
                RAISE EXCEPTION 'temporary player ID mapping is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_PLAYER_MAPPING_TRIGGER}
        BEFORE UPDATE OF temporary_id, player_id ON temporary_player_id_mappings
        FOR EACH ROW
        EXECUTE FUNCTION {_PLAYER_MAPPING_TRIGGER_FUNCTION}()
        """
    )


def downgrade() -> None:
    """3 表と投影・一時 ID 対応の不変性トリガを除去する。"""
    op.execute(
        f"DROP TRIGGER {_PLAYER_MAPPING_TRIGGER} ON temporary_player_id_mappings"
    )
    op.execute(f"DROP FUNCTION {_PLAYER_MAPPING_TRIGGER_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_PLAY_ROW_TRIGGER} ON play_rows")
    op.execute(f"DROP FUNCTION {_PLAY_ROW_TRIGGER_FUNCTION}()")
    op.drop_table("temporary_player_id_mappings")
    op.drop_index("uq_play_runners_active", table_name="play_runners")
    op.drop_table("play_runners")
    op.drop_index("ix_play_rows_game_order", table_name="play_rows")
    op.drop_table("play_rows")
