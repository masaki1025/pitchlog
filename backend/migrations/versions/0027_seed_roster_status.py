"""在籍区分のシステム固定語彙を投入する。

シード資産 ``contracts/seeds/roster-status.json`` が正で、その 3 行を DB へ
投入する二段構成とする(正本 ``data-model.md:1946``)。
試合区分は本 revision の射程外とする。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_seed_roster_status"
down_revision: str | Sequence[str] | None = "0026_operation_event_c12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """在籍区分の 3 行を投入する。"""
    op.bulk_insert(
        sa.table(
            "system_vocabularies",
            sa.column("key", sa.Text()),
            sa.column("category", sa.Text()),
            sa.column("display_name", sa.Text()),
        ),
        [
            {"key": "active", "category": "roster_status", "display_name": "現役"},
            {"key": "other", "category": "roster_status", "display_name": "その他"},
            {"key": "ob", "category": "roster_status", "display_name": "OB"},
        ],
    )


def downgrade() -> None:
    """本 revision で投入した在籍区分の 3 行を取り除く。"""
    op.execute(
        "DELETE FROM system_vocabularies WHERE category = 'roster_status' "
        "AND key IN ('active', 'other', 'ob')"
    )
