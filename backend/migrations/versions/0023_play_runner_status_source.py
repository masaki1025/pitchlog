"""走者状況に手動上書きか自動計算かを示す由来列を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_play_runner_status_source"
down_revision: str | Sequence[str] | None = "0022_operation_event_state_diff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """既定値を補わず、必須の走者状況由来列を追加する。"""
    op.add_column(
        "play_runners",
        sa.Column("status_source", sa.Text(), nullable=False),
    )
    op.create_check_constraint(
        "ck_play_runners_status_source",
        "play_runners",
        "status_source IN ('auto', 'manual')",
    )


def downgrade() -> None:
    """走者状況由来の CHECK と列を削除する。"""
    op.drop_constraint(
        "ck_play_runners_status_source",
        "play_runners",
        type_="check",
    )
    op.drop_column("play_runners", "status_source")
