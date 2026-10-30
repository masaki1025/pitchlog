"""球種の固定SELECT factoryだけを許可し、実行/接続は許可しない。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select  # ty: ignore[unresolved-import]
from sqlalchemy.sql.selectable import Select  # ty: ignore[unresolved-import]


class pitch_type_options:
    """宣言fixtureにだけ用いるclass-qualified対応。"""

    @staticmethod
    def _statement(cursor: str | None=None) -> Select[Any]:
        """球種一覧用SELECT構築だけを表す。"""
        return select(1)
