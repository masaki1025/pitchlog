"""作成固定factoryの限定API正例。実行/接続を許可しない。"""

from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, Table, insert  # ty: ignore[unresolved-import]
from sqlalchemy.sql.dml import Insert  # ty: ignore[unresolved-import]

_TABLE = Table("probe", MetaData(), Column("id", Integer))


class preparing_game_creation:
    """宣言fixtureにだけ適用する既存class-qualified対応。"""

    @staticmethod
    def _preparing_game_insert_statement() -> Insert:
        """当該固定文種別だけを構築する。"""
        return insert(_TABLE)
