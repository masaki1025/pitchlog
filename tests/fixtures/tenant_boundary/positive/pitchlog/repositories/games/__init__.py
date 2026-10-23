"""準備中試合のdetail文構築にSELECTだけを許す正例。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select  # ty: ignore[unresolved-import]
from sqlalchemy.sql.selectable import Select  # ty: ignore[unresolved-import]


def _preparing_game_detail_statement() -> Select[Any]:
    """実行や任意SQLを含めず、許可されたSELECTだけを構築する。"""
    return select(1)
