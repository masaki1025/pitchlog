"""tenant内の有効球種だけを固定文と有限ページで取得する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import Integer, Table, Text, bindparam, select
from sqlalchemy.sql.selectable import Select

from pitchlog.api.schemas.games import decode_preparation_options_cursor
from pitchlog.api.schemas.pitch_type_options import PitchTypeOptionsRequest
from pitchlog.db.tenant_isolation.models import TenantVocabulary
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
    RequiredBinding,
)
from pitchlog.repositories.tokens import TenantOperationToken

_TABLE = cast(Table, TenantVocabulary.__table__)


@dataclass(frozen=True, slots=True)
class PitchTypeOptionsToken(TenantOperationToken):
    """categoryとtenantを外部から受けない球種ページの要求。"""

    limit: int = 20
    cursor: str | None = None

    def __post_init__(self) -> None:
        """強制書換え後もexact型と閉じた要求を検査する。"""
        if type(self.limit) is not int:
            raise ValueError("球種件数は整数が必要")
        PitchTypeOptionsRequest(limit=self.limit, cursor=self.cursor)

    @property
    def capability_id(self) -> str:
        """既存のtenant語彙readだけを用いる。"""
        return "CAP:tenant_vocabularies:read"


def _statement(cursor: str | None = None) -> Select[Any]:
    """tenant/category/有効行をDBで絞り、key順の有限ページを返す。"""
    statement = (
        select(_TABLE.c.key, _TABLE.c.display_name)
        .where(_TABLE.c.tenant_id == bindparam("tenant_id"))
        .where(_TABLE.c.category == bindparam("category"))
        .where(_TABLE.c.disabled == bindparam("disabled"))
    )
    if cursor is not None:
        statement = statement.where(_TABLE.c.key > bindparam("cursor_key", type_=Text))
    return statement.order_by(_TABLE.c.key).limit(bindparam("limit", type_=Integer))


def _prepare(token: TenantOperationToken) -> PreparedOperation:
    """正規型のtokenだけから固定category・有効条件と上限を束縛する。"""
    if type(token) is not PitchTypeOptionsToken:
        raise ValueError("球種一覧tokenが必要")
    token.__post_init__()
    cursor = decode_preparation_options_cursor(token.cursor) if token.cursor else None
    params: dict[str, object] = {
        "category": "pitch_type",
        "disabled": False,
        "limit": token.limit + 1,
    }
    if cursor is not None:
        params["cursor_key"] = cursor
    return _statement(cursor), params


# 正式registryへの追記と認可資産の受理は統合主担当が直列に実施する。
PITCH_TYPE_OPTIONS_OPERATIONS = (
    OperationRegistration(
        PitchTypeOptionsToken,
        "CAP:tenant_vocabularies:read",
        _statement(),
        _TABLE.c.tenant_id,
        _prepare,
        required_bindings=(
            RequiredBinding(_TABLE.c.category, "category", "pitch_type"),
            RequiredBinding(_TABLE.c.disabled, "disabled", False),
        ),
        required_limit_parameter="limit",
        required_limit_max=101,
    ),
)
