"""テナント・チームレコード・選手を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_tenants_teams_players"
down_revision: str | Sequence[str] | None = "0001_initialize_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIGGER_FUNCTION = "prevent_team_records_kind_update"
_TRIGGER = "trg_team_records_kind_immutable"


def upgrade() -> None:
    """3 表とチーム種別の不変性トリガを追加する。"""
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("enabled OR disabled_at IS NOT NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
    )
    op.create_table(
        "team_records",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("kind IN ('self', 'opponent')"),
        sa.CheckConstraint("kind <> 'self' OR hidden_at IS NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_team_records_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_team_records"),
    )
    op.create_index(
        "uq_team_records_self",
        "team_records",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'self'"),
    )
    op.create_table(
        "players",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_record_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("throws", sa.Text(), nullable=True),
        sa.Column("bats", sa.Text(), nullable=True),
        sa.Column("uniform_number", sa.Text(), nullable=True),
        sa.Column("roster_status_key", sa.Text(), nullable=False),
        sa.Column("roster_label_key", sa.Text(), nullable=True),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "team_record_id"],
            ["team_records.tenant_id", "team_records.id"],
            name="fk_players_team",
            match="FULL",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_players"),
    )
    op.create_index(
        "ix_players_team",
        "players",
        ["tenant_id", "team_record_id", "id"],
        unique=False,
        postgresql_where=sa.text("hidden_at IS NULL"),
    )
    op.execute(
        f"""
        CREATE FUNCTION {_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.kind IS DISTINCT FROM OLD.kind THEN
                RAISE EXCEPTION 'team_records.kind is immutable'
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
        BEFORE UPDATE OF kind ON team_records
        FOR EACH ROW
        EXECUTE FUNCTION {_TRIGGER_FUNCTION}()
        """
    )


def downgrade() -> None:
    """3 表とチーム種別の不変性トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_TRIGGER} ON team_records")
    op.execute(f"DROP FUNCTION {_TRIGGER_FUNCTION}()")
    op.drop_index("ix_players_team", table_name="players")
    op.drop_table("players")
    op.drop_index("uq_team_records_self", table_name="team_records")
    op.drop_table("team_records")
    op.drop_table("tenants")
