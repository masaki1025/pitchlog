"""規則セットと試合区分・大会名への割り当てを追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_rule_sets"
down_revision: str | Sequence[str] | None = "0003_games_lineups_participation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """規則セットと2種類の割り当て表を追加する。"""
    op.create_table(
        "rule_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("regulation_innings", sa.Integer(), nullable=False),
        sa.Column("called_game_conditions", postgresql.JSONB(), nullable=False),
        sa.Column("extra_innings_limit", sa.Integer(), nullable=True),
        sa.Column("tiebreak_rule", postgresql.JSONB(), nullable=True),
        sa.Column(
            "uses_dh",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.CheckConstraint("regulation_innings > 0"),
        sa.CheckConstraint(
            "extra_innings_limit IS NULL OR extra_innings_limit >= regulation_innings"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rule_sets"),
    )
    op.create_table(
        "game_type_rule_defaults",
        sa.Column("game_type_key", sa.Text(), nullable=False),
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["rule_set_id"],
            ["rule_sets.id"],
            name="fk_game_type_rule_defaults_rule",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "game_type_key",
            name="pk_game_type_rule_defaults",
        ),
    )
    op.create_table(
        "tournament_rule_assignments",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tournament_key", sa.Text(), nullable=False),
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["rule_set_id"],
            ["rule_sets.id"],
            name="fk_tournament_rule_assignments_rule",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "tournament_key",
            name="pk_tournament_rule_assignments",
        ),
    )


def downgrade() -> None:
    """規則セットと2種類の割り当て表を除去する。"""
    op.drop_table("tournament_rule_assignments")
    op.drop_table("game_type_rule_defaults")
    op.drop_table("rule_sets")
