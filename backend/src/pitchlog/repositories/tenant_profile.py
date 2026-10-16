"""検証済みテナントの正規表示情報を読む固定 operation を定義する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import Table, bindparam, select
from sqlalchemy.sql.selectable import Select

from pitchlog.db.tenant_isolation.models import Tenant
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
)
from pitchlog.repositories.tokens import TenantOperationToken

__all__ = ("TenantProfileReadToken",)

_TENANTS = cast(Table, Tenant.__table__)


@dataclass(frozen=True, slots=True)
class TenantProfileReadToken(TenantOperationToken):
    """実行文脈と同じテナントの識別子と正規表示名を要求する。"""

    @property
    def capability_id(self) -> str:
        """テナント行の読み取り capability を返す。"""
        return "CAP:tenants:read"


def _tenant_profile_statement() -> Select[Any]:
    """文脈から注入されるテナント ID だけで1行を選ぶ。"""
    return select(_TENANTS.c.id, _TENANTS.c.name).where(
        _TENANTS.c.id == bindparam("tenant_id")
    )


def _prepare_tenant_profile(
    _operation: TenantOperationToken,
) -> PreparedOperation:
    """呼び出し元由来の束縛値を持たない固定文を返す。"""
    return _tenant_profile_statement(), {}


TENANT_PROFILE_OPERATIONS: tuple[OperationRegistration, ...] = (
    OperationRegistration(
        TenantProfileReadToken,
        "CAP:tenants:read",
        _tenant_profile_statement(),
        _TENANTS.c.id,
        _prepare_tenant_profile,
    ),
)
