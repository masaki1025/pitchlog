"""RG1の2固定関数SELECTだけの正例。"""

from typing import Literal

from sqlalchemy import Uuid, bindparam, func, select  # ty: ignore[unresolved-import]
from sqlalchemy.sql.selectable import Select  # ty: ignore[unresolved-import]


def _build_rg1_read_statement(kind: Literal["precheck", "commit_check"]) -> Select[tuple[bool]]:
    """許可された2種だけを構築する。"""
    tenant_id = bindparam("tenant_id", type_=Uuid())
    if kind == "precheck":
        return select(func.rg1_api.rg1_read_open(tenant_id).label("is_open"))
    if kind == "commit_check":
        return select(func.rg1_api.rg1_assert_open_before_commit(tenant_id).label("is_open"))
    raise ValueError("未登録種別")
