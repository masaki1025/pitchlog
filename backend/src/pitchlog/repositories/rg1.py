"""復元ゲートの事前読取と確定直前読取を固定関数へ束縛する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlalchemy import Uuid, bindparam, func, select
from sqlalchemy.sql.selectable import Select

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

if TYPE_CHECKING:
    from pitchlog.repositories.transaction import _TenantTransaction

__all__ = (
    "RG1Unavailable",
    "RG1PrecheckToken",
    "RG1CommitCheckToken",
    "RG1ScopeBindingToken",
    "read_rg1_open",
    "assert_rg1_open_before_commit",
)


class RG1Unavailable(RuntimeError):
    """復元ゲートが通常書込みを許可しないことを表す。"""


@dataclass(frozen=True, slots=True)
class RG1PrecheckToken(TenantOperationToken):
    """認可後・D5照合前の非ロック読取を表す。"""

    @property
    def capability_id(self) -> str:
        """事前読取だけのcapabilityを返す。"""
        return "CAP:rg1:precheck"


@dataclass(frozen=True, slots=True)
class RG1CommitCheckToken(TenantOperationToken):
    """確定直前のFOR SHARE NOWAIT読取を表す。"""

    @property
    def capability_id(self) -> str:
        """直前照合だけのcapabilityを返す。"""
        return "CAP:rg1:commit_check"


@dataclass(frozen=True, slots=True)
class RG1ScopeBindingToken(TenantOperationToken):
    """同一Sessionの実business識別を固定関数で観測する。"""

    @property
    def capability_id(self) -> str:
        """制御能力を含まない読取だけのcapabilityを返す。"""
        return "CAP:rg1:scope_binding"


def _build_rg1_scope_binding_statement() -> Select[tuple[str]]:
    """callerの識別値をbindせず、scopeのtenantだけを渡す。"""
    tenant_id = bindparam("tenant_id", type_=Uuid())
    return select(func.rg1_control.scope_binding(tenant_id).label("binding"))


def _build_rg1_read_statement(
    kind: Literal["precheck", "commit_check"],
) -> Select[tuple[bool]]:
    """宣言された2関数の単一SELECTだけを組み立てる。"""
    tenant_id = bindparam("tenant_id", type_=Uuid())
    if kind == "precheck":
        return select(func.rg1_api.rg1_read_open(tenant_id).label("is_open"))
    if kind == "commit_check":
        return select(
            func.rg1_api.rg1_assert_open_before_commit(tenant_id).label("is_open")
        )
    raise ValueError("未登録のRG1読取種別")


def _decode_rg1_result(result: TenantOperationResult) -> TenantOperationResult:
    """共通実行器が確認したexact結果をそのまま返す。"""
    return result


def _require_open(result: TenantOperationResult) -> None:
    """新4では製品関数の常閉結果を通常書込み拒否へ写す。"""
    if result.rows != ((True,),):
        raise RG1Unavailable("復元ゲートが閉じている")


def read_rg1_open(scope: _TenantTransaction, *, game_id: UUID | None = None) -> None:
    """認可後に復元ゲートを非ロックで確認する。"""
    del game_id
    _require_open(scope.run_function(RG1PrecheckToken()))
    scope._ensure_rg1_lease()


def assert_rg1_open_before_commit(
    scope: _TenantTransaction, *, game_id: UUID | None = None
) -> None:
    """同じscopeで直前照合と行ロックを行う。"""
    del game_id
    _require_open(scope.run_function(RG1CommitCheckToken()))
    scope._assert_rg1_lease()
