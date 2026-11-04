"""初球PlayRowの固定INSERT構築だけの正例。"""

from __future__ import annotations

from sqlalchemy import Insert, column, insert, table

_TABLE = table("play_rows", column("tenant_id"))


class first_ball_operations:
    """製品モジュールの登録symbolを表す。"""

    @staticmethod
    def _insert_statement() -> Insert:
        """固定INSERT構築だけを表す。"""
        return insert(_TABLE)
