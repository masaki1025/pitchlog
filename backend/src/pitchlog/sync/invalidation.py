"""同期イベントと同じトランザクションに範囲別の意図を記録する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from pitchlog.db.sync_protocol.models import InvalidationIntent
from pitchlog.repositories.cache_invalidation import CacheScope
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.invalidation_intents import SCOPE_KIND_BY_SCOPE
from pitchlog.repositories.transaction import (
    _TenantTransaction,
    tenant_transaction_scope,
)
from pitchlog.sync import port_guard
from pitchlog.sync.intent_ids import derive_sync_intent_id, is_sync_intent_id
from pitchlog.sync.ports import InvalidationSinkPort
from pitchlog.sync.tokens import (
    InvalidationIntentDeliveredToken,
    InvalidationIntentPendingToken,
    InvalidationIntentReadToken,
    SyncInvalidationIntentInsertToken,
    SyncSharedInvalidationIntentInsertToken,
)

_INTENT_COLUMNS = tuple(InvalidationIntent.__table__.c.keys())


@dataclass(frozen=True, slots=True)
class DeliveryProgress:
    """一回の走査で試みた同期意図と完了した行の数。"""

    attempted: int
    delivered: int


def _record_intents(
    scope: _TenantTransaction,
    event_identity: str,
    game_id: UUID,
) -> tuple[str, ...]:
    """B03 の五つの範囲を既存の token で同一 scope に書く。"""
    intent_ids: list[str] = []
    for cache_scope, scope_kind in SCOPE_KIND_BY_SCOPE.items():
        intent_id = derive_sync_intent_id(event_identity, scope_kind)
        intent_ids.append(intent_id)
        if scope.run(InvalidationIntentReadToken(intent_id)).rows:
            continue
        if cache_scope is CacheScope.SHARED_AGGREGATE:
            token = SyncSharedInvalidationIntentInsertToken(event_identity)
        else:
            token = SyncInvalidationIntentInsertToken(
                event_identity,
                scope_kind,
                game_id if cache_scope is CacheScope.MATCH else None,
            )
        try:
            scope.run_in_savepoint(token)
        except IntegrityError as error:
            if not _intent_primary_key_violation(error):
                raise
            if not scope.run(InvalidationIntentReadToken(intent_id)).rows:
                raise RuntimeError(
                    "意図の一意制約違反後に先着行を観測できない"
                ) from error
    return tuple(intent_ids)


def _intent_primary_key_violation(error: IntegrityError) -> bool:
    """意図 ID の主キー衝突だけを再読の契機とする。"""
    original = error.orig
    diagnostic = getattr(original, "diag", None)
    return (
        getattr(original, "sqlstate", None) == "23505"
        and getattr(diagnostic, "constraint_name", None) == "pk_invalidation_intents"
    )


def record_p3_intents(
    scope: _TenantTransaction,
    game_id: UUID,
    target_generation: int,
    target_d1: int,
    confirmed_version: int,
) -> tuple[str, ...]:
    """P3 の V10 と対象確定版から範囲別意図を記録する。

    Args:
        scope: 対象変更と同一のテナントトランザクション。
        game_id: V10 の試合。
        target_generation: V10 の対象 D4。
        target_d1: V10 の対象 D1。
        confirmed_version: 対象の確定版。

    Returns:
        記録済みの五つの意図 ID。
    """
    if (
        type(game_id) is not UUID
        or type(target_generation) is not int
        or target_generation <= 0
        or type(target_d1) is not int
        or target_d1 <= 0
        or type(confirmed_version) is not int
        or confirmed_version <= 0
    ):
        raise ValueError("P3 の V10 と対象確定版が必要")
    identity = f"{game_id}:{target_generation}:{target_d1}:{confirmed_version}"
    return _record_intents(scope, identity, game_id)


def record_d1_intents(
    scope: _TenantTransaction,
    game_id: UUID,
    d5: UUID,
) -> tuple[str, ...]:
    """D3 を前進させた D1 付きイベントの D5 から意図を記録する。

    Args:
        scope: イベント適用と同一のテナントトランザクション。
        game_id: イベントの試合。
        d5: イベントの D5。

    Returns:
        記録済みの五つの意図 ID。
    """
    if type(game_id) is not UUID or type(d5) is not UUID:
        raise ValueError("D1 付き経路には試合 ID と D5 が必要")
    return _record_intents(scope, str(d5), game_id)


def deliver_pending_sync_intents(
    context: TenantContext,
    sink: InvalidationSinkPort,
    *,
    page_size: int = 100,
) -> DeliveryProgress:
    """B04 の未配信行をページングし、同期所有の意図だけを冪等配送する。

    配信先は意図 ID を冪等キーとして扱う。配信後の完了記録が失敗しても、
    次回は同じ ID を渡す。外部呼び出し中は DB トランザクションを保持しない。
    """
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError("配信ページの上限は 1〜100")
    port_guard.require_registered_port(sink)
    cursor = ""
    attempted = delivered = 0
    while True:
        with tenant_transaction_scope(context) as scope:
            rows = scope.run(InvalidationIntentPendingToken(page_size, cursor)).rows
        if not rows:
            break
        for row in rows:
            if len(row) != len(_INTENT_COLUMNS):
                raise RuntimeError("意図行の列数が正本と異なる")
            intent_id = row[_INTENT_COLUMNS.index("intent_id")]
            scope_kind = row[_INTENT_COLUMNS.index("scope_kind")]
            if type(intent_id) is not str or type(scope_kind) is not str:
                raise RuntimeError("意図 ID または範囲の型が不正")
            cursor = intent_id
            if not is_sync_intent_id(intent_id):
                continue
            if not intent_id.endswith(f":{scope_kind}"):
                raise RuntimeError("同期意図 ID と範囲が一致しない")
            attempted += 1
            if not sink.deliver(intent_id, scope_kind):
                continue
            with tenant_transaction_scope(context) as scope:
                scope.run(
                    InvalidationIntentDeliveredToken(intent_id, datetime.now(UTC))
                )
                persisted = scope.run(InvalidationIntentReadToken(intent_id)).rows
            if len(persisted) != 1 or len(persisted[0]) != len(_INTENT_COLUMNS):
                raise RuntimeError("配信完了を記録した意図行を再読できない")
            if persisted[0][_INTENT_COLUMNS.index("delivery_status")] == "delivered":
                delivered += 1
            else:
                raise RuntimeError("配信完了の状態が永続化されていない")
        if len(rows) < page_size:
            break
    return DeliveryProgress(attempted, delivered)
