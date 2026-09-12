"""migration 管理を開始する最小 revision。"""

from collections.abc import Sequence

revision: str = "0001_initialize_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """最初の revision へ進める。"""


def downgrade() -> None:
    """Migration 適用前の状態へ戻す。"""
