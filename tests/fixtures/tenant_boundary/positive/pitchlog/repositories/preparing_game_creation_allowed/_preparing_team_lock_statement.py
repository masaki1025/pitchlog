"""作成固定factoryの限定API正例。実行/接続を許可しない。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.sql.selectable import Select


class preparing_game_creation:
    """宣言fixtureにだけ適用する既存class-qualified対応。"""

    @staticmethod
    def _preparing_team_lock_statement() -> Select[Any]:
        """当該固定文種別だけを構築する。"""
        return select(1)
