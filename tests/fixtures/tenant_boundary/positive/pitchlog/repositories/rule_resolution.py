"""段階Aの登録済み固定関数SELECT factoryだけを許可する正例。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (  # ty: ignore[unresolved-import]
    Boolean,
    String,
    Uuid,
    bindparam,
    func,
    select,
)
from sqlalchemy.sql.selectable import Select  # ty: ignore[unresolved-import]


def _build_stage_a_rule_statement() -> Select[Any]:
    """scope注入UUIDと固定3入力で単一関数を呼び出す。"""
    return select(
        func.public.resolve_stage_a_rule(
            bindparam("tenant_id", type_=Uuid()),
            bindparam("game_type_key", type_=String()),
            bindparam("tournament_key", type_=String()),
            bindparam("has_override", type_=Boolean()),
        ).label("resolution")
    )
