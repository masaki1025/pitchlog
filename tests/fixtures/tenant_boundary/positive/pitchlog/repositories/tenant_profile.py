"""テナント表示情報の登録済み単一表readだけを許可する正例。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (  # ty: ignore[unresolved-import]
    Column,
    Integer,
    MetaData,
    Table,
    select,
)
from sqlalchemy.sql.selectable import Select  # ty: ignore[unresolved-import]

_TENANTS = Table("tenants", MetaData(), Column("id", Integer))


def _tenant_profile_statement() -> Select[Any]:
    """テナント表示情報の単一表SELECT文を作る。"""
    return select(_TENANTS.c.id)
