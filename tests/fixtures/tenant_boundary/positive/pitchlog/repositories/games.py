"""準備中試合のlist文構築にSELECTだけを許す正例。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.sql.selectable import Select


def _preparing_game_list_statement(
    cursor_position: tuple[datetime, UUID] | None = None,
) -> Select[Any]:
    """実行や任意SQLを含めず、許可されたSELECTだけを構築する。"""
    return select(1)
