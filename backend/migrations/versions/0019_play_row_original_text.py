"""プレイ行の列 47・55 の原本列を text へ是正する。"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_play_row_original_text"
down_revision: str | Sequence[str] | None = "0018_migration_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """旧 TEXT 由来の原本列を情報損失のない text 型へ変更する。"""
    op.execute("ALTER TABLE play_rows ALTER COLUMN raw_fielder_position TYPE text")
    op.execute("ALTER TABLE play_rows ALTER COLUMN raw_error_position TYPE text")


def downgrade() -> None:
    """原本列を integer 型へ戻し、変換不能な値は失敗させる。"""
    op.execute(
        "ALTER TABLE play_rows "
        "ALTER COLUMN raw_error_position TYPE integer "
        "USING raw_error_position::integer"
    )
    op.execute(
        "ALTER TABLE play_rows "
        "ALTER COLUMN raw_fielder_position TYPE integer "
        "USING raw_fielder_position::integer"
    )
