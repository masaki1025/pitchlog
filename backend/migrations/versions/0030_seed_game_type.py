"""試合区分のシステム固定語彙を投入する。

シード資産 ``contracts/seeds/game-type.json`` を正として投入値を固定する。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_seed_game_type"
down_revision: str | Sequence[str] | None = "0029_system_vocab_category_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """試合区分の 5 行を投入する。"""
    op.bulk_insert(
        sa.table(
            "system_vocabularies",
            sa.column("key", sa.Text()),
            sa.column("category", sa.Text()),
            sa.column("display_name", sa.Text()),
        ),
        [
            {"key": "game_official", "category": "game_type", "display_name": "公式戦"},
            {
                "key": "game_semi_official",
                "category": "game_type",
                "display_name": "準公式戦",
            },
            {"key": "game_open", "category": "game_type", "display_name": "オープン戦"},
            {
                "key": "game_intrasquad",
                "category": "game_type",
                "display_name": "紅白戦",
            },
            {"key": "game_other", "category": "game_type", "display_name": "その他"},
        ],
    )


def downgrade() -> None:
    """本 revision が投入した試合区分の 5 行を取り除く。"""
    op.execute(
        "DELETE FROM system_vocabularies WHERE category = 'game_type' "
        "AND key IN ('game_official', 'game_semi_official', 'game_open', "
        "'game_intrasquad', 'game_other')"
    )
