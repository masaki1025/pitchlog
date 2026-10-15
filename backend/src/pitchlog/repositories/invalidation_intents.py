"""同期を通らない変更による無効化意図を同一トランザクションに記録する。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch
from types import MappingProxyType
from typing import TYPE_CHECKING, cast
from uuid import UUID

from sqlalchemy import Table, Text, Uuid, bindparam, insert, null
from sqlalchemy.sql.dml import Insert

from pitchlog.db.sync_protocol.models import InvalidationIntent
from pitchlog.repositories.cache_invalidation import (
    CacheInvalidationRequest,
    CacheInvalidationTrigger,
    CacheScope,
    MatchCacheKey,
    SharedAggregateTargetSelector,
    build_cache_invalidation_request,
)
from pitchlog.repositories.operation_registration import (
    OperationRegistration,
    PreparedOperation,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

if TYPE_CHECKING:
    from pitchlog.repositories.transaction import _TenantTransaction

__all__ = (
    "InvalidationIntentInsertToken",
    "SCOPE_KIND_BY_SCOPE",
    "StoredIntentTargetKind",
    "classify_stored_intent_target",
    "record_game_invalidation_intents",
    "record_invalidation_intent",
)

_INTENTS = cast(Table, InvalidationIntent.__table__)
SCOPE_KIND_BY_SCOPE = MappingProxyType(
    {
        CacheScope.MATCH: "game",
        CacheScope.PLAYER_CAREER: "player_total",
        CacheScope.TEAM_AGGREGATE: "team_total",
        CacheScope.SHARED_AGGREGATE: "shared_total",
        CacheScope.ANALYTICS_CHART: "chart",
    }
)
_SELECTOR_KIND_BY_SCOPE: dict[CacheScope, str] = {
    CacheScope.MATCH: "concrete_game",
    CacheScope.PLAYER_CAREER: "tenant_scope",
    CacheScope.TEAM_AGGREGATE: "tenant_scope",
    CacheScope.SHARED_AGGREGATE: "shared_target_tenant",
    CacheScope.ANALYTICS_CHART: "tenant_scope",
}


class StoredIntentTargetKind(StrEnum):
    """配信側へ渡す保存行の判別結果。"""

    EXPLICIT_SELECTOR = "explicit_selector"
    LEGACY_SHARED_SELECTOR = "legacy_shared_selector"
    LEGACY_PHYSICAL_KEY = "legacy_physical_key"
    DELIVERY_HOLD = "delivery_hold"


_CANONICAL_UUID = (
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}"
)


def classify_stored_intent_target(
    intent: InvalidationIntent,
) -> StoredIntentTargetKind:
    """旧行を共有選択子・物理鍵・配信保留へ厳密に分ける。

    新形式行はDB制約が保証した明示選択子として返す。旧行のNULLを
    暗黙の全件指定へ変換しない。配信器本体は後続の所有単位が実装する。
    """
    if intent.target_selector_kind is not None:
        return StoredIntentTargetKind.EXPLICIT_SELECTOR
    empty = (
        intent.game_id is None
        and intent.player_id is None
        and intent.group_id is None
        and intent.requesting_tenant_id is None
        and intent.period is None
        and intent.chart_kind is None
    )
    if intent.intent_id.startswith("roster_status_change:"):
        if (
            fullmatch(
                rf"roster_status_change:{_CANONICAL_UUID}:shared_aggregate",
                intent.intent_id,
            )
            and intent.scope_kind == "shared_total"
            and intent.target_tenant_id == intent.tenant_id
            and empty
        ):
            return StoredIntentTargetKind.LEGACY_SHARED_SELECTOR
        return StoredIntentTargetKind.DELIVERY_HOLD

    physical_shape = (
        (
            intent.scope_kind == "game"
            and intent.game_id is not None
            and intent.player_id is None
            and intent.group_id is None
            and intent.requesting_tenant_id is None
            and intent.target_tenant_id is None
            and intent.period is None
            and intent.chart_kind is None
        )
        or (
            intent.scope_kind == "player_total"
            and intent.player_id is not None
            and intent.period is not None
            and intent.game_id is None
            and intent.group_id is None
            and intent.requesting_tenant_id is None
            and intent.target_tenant_id is None
            and intent.chart_kind is None
        )
        or (
            intent.scope_kind == "team_total"
            and intent.period is not None
            and intent.game_id is None
            and intent.player_id is None
            and intent.group_id is None
            and intent.requesting_tenant_id is None
            and intent.target_tenant_id is None
            and intent.chart_kind is None
        )
        or (
            intent.scope_kind == "shared_total"
            and intent.group_id is not None
            and intent.requesting_tenant_id is not None
            and intent.target_tenant_id == intent.tenant_id
            and intent.period is not None
            and intent.game_id is None
            and intent.player_id is None
            and intent.chart_kind is None
        )
        or (
            intent.scope_kind == "chart"
            and (intent.game_id is None) != (intent.player_id is None)
            and isinstance(intent.chart_kind, str)
            and bool(intent.chart_kind.strip())
            and intent.group_id is None
            and intent.requesting_tenant_id is None
            and intent.target_tenant_id is None
            and intent.period is None
        )
    )
    if physical_shape:
        return StoredIntentTargetKind.LEGACY_PHYSICAL_KEY
    return StoredIntentTargetKind.DELIVERY_HOLD


@dataclass(frozen=True, slots=True)
class InvalidationIntentInsertToken(TenantOperationToken):
    """既知の非同期トリガー1範囲の意図をテナント内へ書く。"""

    trigger: CacheInvalidationTrigger
    operation_id: UUID
    row_discriminator: CacheScope
    game_id: UUID | None = None

    def __post_init__(self) -> None:
        """許可したトリガーの行形と同期意図 ID との非衝突を検証する。"""
        if isinstance(
            self.trigger, CacheInvalidationTrigger
        ) and self.trigger.value.startswith("sync"):
            raise ValueError("同期意図 ID と衝突するトリガー値は使えない")
        if type(self.operation_id) is not UUID:
            raise ValueError("operation_id は UUID が必要")
        if self.trigger is CacheInvalidationTrigger.ROSTER_STATUS_CHANGE:
            if self.row_discriminator is not CacheScope.SHARED_AGGREGATE:
                raise ValueError("行の識別子は shared_aggregate が必要")
            if self.game_id is not None:
                raise ValueError("在籍区分変更には試合IDを渡せない")
        elif self.trigger is CacheInvalidationTrigger.GAME_DELETE_RESTORE_OR_RESUME:
            if type(self.row_discriminator) is not CacheScope:
                raise ValueError("行識別子は定義済みの範囲が必要")
            if type(self.game_id) is not UUID:
                raise ValueError("試合状態変更には試合IDが必要")
        else:
            raise ValueError("在籍区分変更トリガーか試合状態変更だけを記録できる")

    @property
    def intent_id(self) -> str:
        """正本 B06 の骨格から意図 ID を導出する。"""
        if self.trigger is CacheInvalidationTrigger.GAME_DELETE_RESTORE_OR_RESUME:
            return (
                f"{self.trigger.value}:{self.operation_id}:"
                f"{self.game_id}:{self.row_discriminator.value}"
            )
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
            "scope_kind", SCOPE_KIND_BY_SCOPE[CacheScope.SHARED_AGGREGATE], type_=Text
        ),
        target_tenant_id=bindparam("tenant_id"),
    )


def _prepare_invalidation_intent_insert(
    operation: TenantOperationToken,
) -> PreparedOperation:
    """トリガーごとに許可した列だけを実行文へ渡す。"""
    token = cast(InvalidationIntentInsertToken, operation)
    if token.trigger is CacheInvalidationTrigger.GAME_DELETE_RESTORE_OR_RESUME:
        statement = _build_invalidation_intent_statement().values(
            scope_kind=bindparam("scope_kind", type_=Text),
            target_selector_kind=bindparam("target_selector_kind", type_=Text),
            game_id=bindparam("game_id", type_=Uuid(as_uuid=True)),
            target_tenant_id=(
                bindparam("tenant_id")
                if token.row_discriminator is CacheScope.SHARED_AGGREGATE
                else null()
            ),
        )
        return statement, {
            "intent_id": token.intent_id,
            "scope_kind": SCOPE_KIND_BY_SCOPE[token.row_discriminator],
            "target_selector_kind": _SELECTOR_KIND_BY_SCOPE[token.row_discriminator],
            "game_id": (
                token.game_id if token.row_discriminator is CacheScope.MATCH else None
            ),
        }
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


def record_game_invalidation_intents(
    scope: _TenantTransaction,
    request: CacheInvalidationRequest,
    operation_id: UUID,
    changed_game_id: UUID,
) -> tuple[TenantOperationResult, ...]:
    """状態が変わった1試合の5意図を呼出し元のトランザクションへ保存する。

    Args:
        scope: 状態更新と共有するテナントのトランザクション。
        request: 純粋生成器が検証した試合状態変更要求。
        operation_id: サーバーが要求単位で採番したID。
        changed_game_id: 呼出し元が状態変更済みと検証した試合ID。

    Returns:
        5範囲それぞれのINSERT結果。

    Raises:
        ValueError: 対象外要求、テナント・試合の不一致、またはIDの型違反。
    """
    if type(request) is not CacheInvalidationRequest:
        raise ValueError("検証済みの無効化要求が必要")
    if request.trigger is not CacheInvalidationTrigger.GAME_DELETE_RESTORE_OR_RESUME:
        raise ValueError("試合状態変更トリガーだけを記録できる")
    if type(operation_id) is not UUID or type(changed_game_id) is not UUID:
        raise ValueError("操作IDと変更済み試合IDはUUIDが必要")
    validated = build_cache_invalidation_request(request.trigger, request.keys)
    if validated != request:
        raise ValueError("要求の検証済み属性が不一致")
    match_keys = [key for key in request.keys if type(key) is MatchCacheKey]
    if len(match_keys) != 1:
        raise ValueError("試合の具体鍵がちょうど1件必要")
    match_key = match_keys[0]
    if (
        match_key.tenant_id != scope._bound_tenant_id
        or match_key.match_id != changed_game_id
    ):
        raise ValueError("変更済み試合とテナント文脈が要求に一致しない")
    return tuple(
        scope.run(
            InvalidationIntentInsertToken(
                request.trigger,
                operation_id,
                scope_id,
                changed_game_id,
            )
        )
        for scope_id in CacheScope
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
