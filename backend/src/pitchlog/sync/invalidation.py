"""同期イベントと同じトランザクションに範囲別の意図を記録する。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError

from pitchlog.repositories.cache_invalidation import CacheScope
from pitchlog.repositories.invalidation_intents import SCOPE_KIND_BY_SCOPE
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.intent_ids import derive_sync_intent_id
from pitchlog.sync.tokens import (
    InvalidationIntentReadToken,
    SyncInvalidationIntentInsertToken,
    SyncSharedInvalidationIntentInsertToken,
)


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
