"""RG1の単一状態行を常閉で初期化する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_rg1_restore_gate"
down_revision: str | Sequence[str] | None = "0031_intent_selectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """単一状態表を作り、closedの1行だけを投入する。"""
    op.create_table(
        "rg1_restore_gate",
        sa.Column(
            "singleton_id", sa.SmallInteger(), nullable=False, autoincrement=False
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "singleton_id = 1", name="ck_rg1_restore_gate_singleton_id"
        ),
        sa.CheckConstraint(
            "state IN ('closed', 'open')", name="ck_rg1_restore_gate_state"
        ),
        sa.PrimaryKeyConstraint("singleton_id", name="pk_rg1_restore_gate"),
    )
    op.bulk_insert(
        sa.table(
            "rg1_restore_gate",
            sa.column("singleton_id", sa.SmallInteger()),
            sa.column("state", sa.Text()),
        ),
        [{"singleton_id": 1, "state": "closed"}],
    )


def downgrade() -> None:
    """本revisionが作成した状態表を取り外す。"""
    op.drop_table("rg1_restore_gate")
