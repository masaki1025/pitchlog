"""作成固定factoryの限定API正例。実行/接続を許可しない。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select  # ty: ignore[unresolved-import]
from sqlalchemy.sql.selectable import Select  # ty: ignore[unresolved-import]


class preparing_game_creation:
    """宣言fixtureにだけ適用する既存class-qualified対応。"""

    @staticmethod
    def _preparing_tournament_options_statement(cursor_key: str | None=None) -> Select[Any]:
        """当該固定文種別だけを構築する。"""
        return select(1)
