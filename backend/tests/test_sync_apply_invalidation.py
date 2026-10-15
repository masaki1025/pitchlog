"""同期経路の範囲別意図 ID と再記録の純粋な境界を検査する。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from pitchlog.repositories.invalidation_intents import SCOPE_KIND_BY_SCOPE
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.intent_ids import derive_sync_intent_id
from pitchlog.sync.invalidation import record_d1_intents, record_p3_intents
from pitchlog.sync.tokens import (
    InvalidationIntentReadToken,
    SyncInvalidationIntentInsertToken,
    SyncSharedInvalidationIntentInsertToken,
)


def test_p3_and_d1_record_each_scope_once_for_same_input() -> None:
    """再記録では範囲別 ID が変わらず追加 token を発行しない。"""
    saved: set[str] = set()
    inserted: list[str] = []

    def run(operation: object) -> TenantOperationResult:
        if isinstance(operation, InvalidationIntentReadToken):
            rows = ((operation.intent_id,),) if operation.intent_id in saved else ()
            return TenantOperationResult(rows)
        if isinstance(
            operation,
            SyncInvalidationIntentInsertToken | SyncSharedInvalidationIntentInsertToken,
        ):
            saved.add(operation.intent_id)
            inserted.append(operation.intent_id)
            return TenantOperationResult(((-1,),))
        raise AssertionError("未知の token")

    scope = cast(_TenantTransaction, SimpleNamespace(run=run, run_in_savepoint=run))
    game_id, d5 = uuid4(), uuid4()
    p3 = record_p3_intents(scope, game_id, 2, 3, 4)
    assert p3 == tuple(
        derive_sync_intent_id(f"{game_id}:2:3:4", kind)
        for kind in SCOPE_KIND_BY_SCOPE.values()
    )
    assert record_p3_intents(scope, game_id, 2, 3, 4) == p3
    d1 = record_d1_intents(scope, game_id, d5)
    assert d1 == tuple(
        derive_sync_intent_id(str(d5), kind) for kind in SCOPE_KIND_BY_SCOPE.values()
    )
    assert record_d1_intents(scope, game_id, d5) == d1
    assert inserted == [*p3, *d1]
    assert len(saved) == 10


def test_invalid_event_identity_does_not_issue_token() -> None:
    """P3 の V10・確定版と D1 の D5 の型違反を実行前に拒否する。"""

    def unexpected_run(_operation: object) -> TenantOperationResult:
        raise AssertionError("不正な入力から token を実行してはならない")

    scope = cast(_TenantTransaction, SimpleNamespace(run=unexpected_run))
    game_id = uuid4()
    with pytest.raises(ValueError, match="V10"):
        record_p3_intents(scope, game_id, 1, 1, 0)
    with pytest.raises(ValueError, match="D5"):
        record_d1_intents(scope, game_id, cast(UUID, "not-a-uuid"))


class _ConstraintError(Exception):
    """psycopg の制約診断情報を持つ試験用例外。"""

    sqlstate = "23505"

    def __init__(self, constraint_name: str) -> None:
        """違反した制約名を設定する。"""
        self.diag = SimpleNamespace(constraint_name=constraint_name)


@pytest.mark.parametrize(
    ("constraint_name", "recheck"),
    [("pk_invalidation_intents", True), ("other_unique", False)],
)
def test_only_intent_primary_key_collision_is_rechecked(
    constraint_name: str, recheck: bool
) -> None:
    """主キー衝突だけを再読し、別の制約違反は伝播する。"""
    reads = 0
    inserts = 0

    def run(operation: object) -> TenantOperationResult:
        nonlocal reads
        assert isinstance(operation, InvalidationIntentReadToken)
        reads += 1
        return TenantOperationResult(((operation.intent_id,),) if reads == 2 else ())

    def fail_insert(_operation: object) -> TenantOperationResult:
        nonlocal inserts
        inserts += 1
        if inserts == 1:
            raise IntegrityError("INSERT", {}, _ConstraintError(constraint_name))
        return TenantOperationResult(((-1,),))

    scope = cast(
        _TenantTransaction,
        SimpleNamespace(run=run, run_in_savepoint=fail_insert),
    )
    if recheck:
        assert len(record_d1_intents(scope, uuid4(), uuid4())) == 5
        assert reads == 6
    else:
        with pytest.raises(IntegrityError):
            record_d1_intents(scope, uuid4(), uuid4())
        assert reads == 1
