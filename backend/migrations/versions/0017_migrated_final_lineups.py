"""移行元最終オーダーを追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_migrated_final_lineups"
down_revision: str | Sequence[str] | None = "0016_migration_quarantine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION_NAME = "prevent_migrated_final_lineups_source_update"
_TRIGGER_NAME = "trg_migrated_final_lineups_source_immutable"


def upgrade() -> None:
    """移行元最終オーダーと不変性トリガを追加する。"""
    op.create_table(
        "migrated_final_lineups",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("team_record_id", sa.Uuid(), nullable=False),
        sa.Column("raw_lineup", sa.Text(), nullable=False),
        sa.Column("legacy_row_identifier", sa.Text(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_migrated_final_lineups_game",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_migrated_final_lineups_team",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "id",
            name="pk_migrated_final_lineups",
        ),
    )
    op.create_index(
        "uq_migrated_final_lineups_active",
        "migrated_final_lineups",
        ["tenant_id", "game_id", "team_record_id"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )

    op.execute(
        f"""
        CREATE FUNCTION {_FUNCTION_NAME}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.game_id,
                NEW.team_record_id,
                NEW.raw_lineup,
                NEW.legacy_row_identifier,
                NEW.import_batch_id
            ) IS DISTINCT FROM ROW(
                OLD.game_id,
                OLD.team_record_id,
                OLD.raw_lineup,
                OLD.legacy_row_identifier,
                OLD.import_batch_id
            ) THEN
                RAISE EXCEPTION 'migrated final lineup source is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_NAME}
        BEFORE UPDATE OF
            game_id,
            team_record_id,
            raw_lineup,
            legacy_row_identifier,
            import_batch_id
        ON migrated_final_lineups
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION_NAME}()
        """
    )


def downgrade() -> None:
    """移行元最終オーダーと不変性トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_TRIGGER_NAME} ON migrated_final_lineups")
    op.execute(f"DROP FUNCTION {_FUNCTION_NAME}()")
    op.drop_index(
        "uq_migrated_final_lineups_active",
        table_name="migrated_final_lineups",
    )
    op.drop_table("migrated_final_lineups")
