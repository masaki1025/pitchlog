"""試合・スタメン記憶・背番号スナップショット・出場区間を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_games_lineups_participation"
down_revision: str | Sequence[str] | None = "0002_tenants_teams_players"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIGGER_FUNCTION = "prevent_game_lineups_entries_update"
_TRIGGER = "trg_game_lineups_entries_immutable"


def upgrade() -> None:
    """4 表と先発時の背番号スナップショット保護を追加する。"""
    op.create_table(
        "games",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("game_type_key", sa.Text(), nullable=False),
        sa.Column("tournament_key", sa.Text(), nullable=False),
        sa.Column("away_team_record_id", sa.Uuid(), nullable=False),
        sa.Column("home_team_record_id", sa.Uuid(), nullable=False),
        sa.Column("plate_umpire", sa.Text(), nullable=True),
        sa.Column("section_label", sa.Text(), nullable=True),
        sa.Column("week_label", sa.Text(), nullable=True),
        sa.Column("day_label", sa.Text(), nullable=True),
        sa.Column("game_number_label", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'preparing'"),
            nullable=False,
        ),
        sa.Column("applied_rules", postgresql.JSONB(), nullable=False),
        sa.Column("rule_override", postgresql.JSONB(), nullable=True),
        sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('preparing', 'in_progress', 'finished', 'trashed', 'hidden')"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "away_team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_games_away_team",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "home_team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_games_home_team",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_games"),
    )
    op.create_index(
        "ix_games_list",
        "games",
        ["tenant_id", sa.text("scheduled_at DESC"), sa.text("id DESC")],
        unique=False,
        postgresql_where=sa.text("trashed_at IS NULL AND hidden_at IS NULL"),
    )
    op.create_table(
        "lineup_memories",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_record_id", sa.Uuid(), nullable=False),
        sa.Column("lineup", postgresql.JSONB(), nullable=False),
        sa.Column(
            "migration_preserved_only",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_lineup_memories_team",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_lineup_memories"),
    )
    op.create_index(
        "uq_lineup_memories_active",
        "lineup_memories",
        ["tenant_id", "team_record_id"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.create_table(
        "game_lineups",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("team_record_id", sa.Uuid(), nullable=False),
        sa.Column(
            "entries_with_uniform_number_snapshot",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_game_lineups_game",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_game_lineups_team",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_game_lineups"),
    )
    op.create_index(
        "ix_game_lineups_game",
        "game_lineups",
        ["tenant_id", "game_id", "team_record_id"],
        unique=False,
    )
    op.create_table(
        "participation_intervals",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("slot_kind", sa.Text(), nullable=False),
        sa.Column("slot", sa.Text(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("valid_from_d2", sa.BigInteger(), nullable=False),
        sa.Column("valid_until_d2", sa.BigInteger(), nullable=True),
        sa.Column("uniform_number_snapshot", sa.Text(), nullable=True),
        sa.Column(
            "unknown_for_migration",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("slot_kind IN ('batting_order', 'fielding_position')"),
        sa.CheckConstraint("valid_until_d2 IS NULL OR valid_until_d2 > valid_from_d2"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_participation_intervals_game",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "player_id"],
            ["players.tenant_id", "players.id"],
            name="fk_participation_intervals_player",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_participation_intervals"),
    )
    op.create_index(
        "uq_participation_intervals_active",
        "participation_intervals",
        ["tenant_id", "game_id", "slot_kind", "slot", "valid_from_d2"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.create_index(
        "ix_participation_intervals_range",
        "participation_intervals",
        ["tenant_id", "game_id", "valid_from_d2", "valid_until_d2"],
        unique=False,
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.execute(
        f"""
        CREATE FUNCTION {_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.entries_with_uniform_number_snapshot IS DISTINCT FROM
               OLD.entries_with_uniform_number_snapshot THEN
                RAISE EXCEPTION
                    'game_lineups.entries_with_uniform_number_snapshot is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER}
        BEFORE UPDATE OF entries_with_uniform_number_snapshot ON game_lineups
        FOR EACH ROW
        EXECUTE FUNCTION {_TRIGGER_FUNCTION}()
        """
    )


def downgrade() -> None:
    """4 表と先発時の背番号スナップショット保護を除去する。"""
    op.execute(f"DROP TRIGGER {_TRIGGER} ON game_lineups")
    op.execute(f"DROP FUNCTION {_TRIGGER_FUNCTION}()")
    op.drop_index(
        "ix_participation_intervals_range",
        table_name="participation_intervals",
    )
    op.drop_index(
        "uq_participation_intervals_active",
        table_name="participation_intervals",
    )
    op.drop_table("participation_intervals")
    op.drop_index("ix_game_lineups_game", table_name="game_lineups")
    op.drop_table("game_lineups")
    op.drop_index("uq_lineup_memories_active", table_name="lineup_memories")
    op.drop_table("lineup_memories")
    op.drop_index("ix_games_list", table_name="games")
    op.drop_table("games")
