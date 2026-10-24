"""RG1の真正な初回世代を保持するnullable列だけを追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_rg1_initial_fresh_epoch"
down_revision: str | Sequence[str] | None = "0034_stage_a_rule_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """既存stateを変えず、旧行へ推測した世代を補完しない。"""
    op.add_column(
        "rg1_restore_gate",
        sa.Column("recovery_generation", sa.BigInteger(), nullable=True),
        schema="public",
    )
    op.create_check_constraint(
        "ck_rg1_restore_gate_recovery_generation",
        "rg1_restore_gate",
        "recovery_generation IS NULL OR recovery_generation > 0",
        schema="public",
    )


def downgrade() -> None:
    """束縛済みの世代証拠を失う巻戻しを拒否する。"""
    op.execute(
        "DO $body$ BEGIN "
        "LOCK TABLE public.rg1_restore_gate IN ACCESS EXCLUSIVE MODE; "
        "IF EXISTS (SELECT 1 FROM public.rg1_restore_gate "
        "WHERE recovery_generation IS NOT NULL) THEN "
        "RAISE EXCEPTION 'bound RG1 epoch cannot be removed'; "
        "END IF; END $body$"
    )
    op.drop_constraint(
        "ck_rg1_restore_gate_recovery_generation",
        "rg1_restore_gate",
        type_="check",
        schema="public",
    )
    op.drop_column("rg1_restore_gate", "recovery_generation", schema="public")
