"""初球PlayRowの固定SELECT構築だけの正例。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.sql.selectable import Select


class first_ball_operations:
    """製品モジュールの登録symbolを表す。"""

    @staticmethod
    def _read_statement() -> Select[Any]:
        """固定SELECT構築だけを表す。"""
        return select(1)
