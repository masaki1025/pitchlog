"""同期を通らない変更による無効化意図を同一トランザクションに記録する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from uuid import UUID

from sqlalchemy import Table, Text, bindparam, insert
from sqlalchemy.sql.dml import Insert

from pitchlog.db.sync_protocol.models import InvalidationIntent
from pitchlog.repositories.cache_invalidation import (
    CacheInvalidationRequest,
    CacheInvalidationTrigger,
    CacheScope,
    SharedAggregateTargetSelector,
)
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

if TYPE_CHECKING:
    from pitchlog.repositories.transaction import _TenantTransaction

__all__ = ("InvalidationIntentInsertToken", "record_invalidation_intent")

_INTENTS = cast(Table, InvalidationIntent.__table__)
_SCOPE_KIND_BY_SCOPE: dict[CacheScope, str] = {
    CacheScope.MATCH: "game",
    CacheScope.PLAYER_CAREER: "player_total",
    CacheScope.TEAM_AGGREGATE: "team_total",
    CacheScope.SHARED_AGGREGATE: "shared_total",
    CacheScope.ANALYTICS_CHART: "chart",
}


@dataclass(frozen=True, slots=True)
class InvalidationIntentInsertToken(TenantOperationToken):
    """実行中のテナントに帰属する共有集計意図を 1 行書く。"""

    trigger: CacheInvalidationTrigger
    operation_id: UUID
    row_discriminator: CacheScope

    def __post_init__(self) -> None:
        """本 PR が行規則を持つトリガーと識別子だけを許す。"""
        if self.trigger is not CacheInvalidationTrigger.ROSTER_STATUS_CHANGE:
            raise ValueError("在籍区分変更トリガーだけを記録できる")
        if type(self.operation_id) is not UUID:
            raise ValueError("operation_id は UUID が必要")
        if self.row_discriminator is not CacheScope.SHARED_AGGREGATE:
            raise ValueError("行の識別子は shared_aggregate が必要")

    @property
    def intent_id(self) -> str:
        """正本 B06 の骨格から意図 ID を導出する。"""
        return (
            f"{self.trigger.value}:{self.operation_id}:{self.row_discriminator.value}"
        )

    @property
    def capability_id(self) -> str:
        """無効化意図の追加 capability を返す。"""
        return "CAP:invalidation_intents:insert"


def _build_invalidation_intent_statement() -> Insert:
    """対象テナントを束縛済みテナントへ固定した INSERT 文を作る。"""
    return insert(_INTENTS).values(
        tenant_id=bindparam("tenant_id"),
        intent_id=bindparam("intent_id", type_=Text),
        scope_kind=bindparam(
            "scope_kind", _SCOPE_KIND_BY_SCOPE[CacheScope.SHARED_AGGREGATE], type_=Text
        ),
        target_tenant_id=bindparam("tenant_id"),
    )


def _prepare_invalidation_intent_insert(
    operation: TenantOperationToken,
) -> PreparedOperation:
    """Token 内で導出した意図 ID だけを実行文へ渡す。"""
    token = cast(InvalidationIntentInsertToken, operation)
    return _build_invalidation_intent_statement(), {"intent_id": token.intent_id}


INVALIDATION_INTENT_OPERATIONS: tuple[OperationRegistration, ...] = (
    OperationRegistration(
        InvalidationIntentInsertToken,
        "CAP:invalidation_intents:insert",
        _build_invalidation_intent_statement(),
        _INTENTS.c.tenant_id,
        _prepare_invalidation_intent_insert,
    ),
)


def record_invalidation_intent(
    scope: _TenantTransaction,
    request: CacheInvalidationRequest,
    operation_id: UUID,
) -> TenantOperationResult:
    """在籍区分の変更による意図を同じトランザクションへ 1 行書く。

    Args:
        scope: 状態変更を実行したテナントのトランザクション。
        request: 純粋な要求生成器が検証した無効化要求。
        operation_id: 呼び出し側が 1 要求ごとに採番した ID。

    Returns:
        INSERT の実行結果を表す不変 DTO。

    Raises:
        ValueError: 未定義のトリガー・鍵形・帰属、または操作 ID の型違反。
    """
    if type(request) is not CacheInvalidationRequest:
        raise ValueError("検証済みの無効化要求が必要")
    if (
        request.trigger is not CacheInvalidationTrigger.ROSTER_STATUS_CHANGE
        or len(request.keys) != 1
        or type(request.keys[0]) is not SharedAggregateTargetSelector
    ):
        raise ValueError("在籍区分変更の対象テナント選択子 1 件だけを記録できる")
    selector = request.keys[0]
    if selector.tenant_id != scope._bound_tenant_id:
        raise ValueError("対象テナントは実行中のテナント文脈と一致する必要がある")
    return scope.run(
        InvalidationIntentInsertToken(
            request.trigger, operation_id, CacheScope.SHARED_AGGREGATE
        )
    )
