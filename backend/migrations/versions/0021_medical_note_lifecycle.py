"""カルテ所見を親の削除系統へ従わせる。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_medical_note_lifecycle"
down_revision: str | Sequence[str] | None = "0020_play_row_destinations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """カルテ所見から独自の非表示時刻を撤去する。"""
    op.drop_column("medical_notes", "hidden_at")


def downgrade() -> None:
    """カルテ所見の非表示時刻を NULL 可で復元する。"""
    op.add_column(
        "medical_notes",
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
    )
