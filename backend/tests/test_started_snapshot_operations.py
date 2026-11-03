"""started read登録のSQL境界。実DB/HTTP接続の成功ではない。"""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import transaction
from pitchlog.repositories.base import _operation_spec, _validate_prepared_statement
from pitchlog.repositories.operation_registry import PRODUCT_OPERATIONS
from pitchlog.repositories.started_snapshot_operations import (
    STARTED_SNAPSHOT_OPERATIONS,
    StartedLineupsReadToken,
)


@pytest.mark.parametrize("spec", STARTED_SNAPSHOT_OPERATIONS)
def test_candidates_have_tenant_game_bounds_and_no_other_filters(spec: Any) -> None:
    """全世代/NULL D2/退役行を除外せず有限件数だけを問い合わせる。"""
    game = uuid4()
    token = spec.token_type(game)
    statement, parameters = spec.prepare(token)
    _validate_prepared_statement(spec, statement)
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    table = spec.tenant_column.table.name
    assert f"{table}.tenant_id = %(tenant_id)s::UUID" in sql
    assert f"{table}.game_id = %(game_id)s::UUID" in sql
    assert "LIMIT %(limit)s" in sql
    assert parameters == {
        "game_id": game,
        "limit": 3 if type(token) is StartedLineupsReadToken else 1,
    }
    assert spec.required_limit_parameter == "limit"
    assert spec.required_limit_max == parameters["limit"]
    assert "generation =" not in sql
    assert "d2" not in sql and "retired_at" not in sql and "replaced_at" not in sql
    assert not statement._for_update_arg
    assert len(statement.selected_columns) == (
        5 if type(token) is StartedLineupsReadToken else 1
    )


@pytest.mark.parametrize("spec", STARTED_SNAPSHOT_OPERATIONS)
@pytest.mark.parametrize(
    "value", [None, True, 1, "00000000-0000-4000-8000-000000000001"]
)
def test_token_rejects_non_uuid_and_prepare_rechecks_it(spec: Any, value: Any) -> None:
    """構築時と強制改変後の両方でUUID実型を確認する。"""
    with pytest.raises(ValueError):
        spec.token_type(value)
    token = spec.token_type(uuid4())
    object.__setattr__(token, "game_id", value)
    with pytest.raises(ValueError):
        spec.prepare(token)


@pytest.mark.parametrize("spec", STARTED_SNAPSHOT_OPERATIONS)
def test_unregistered_subtype_never_enters_real_registry_or_session(
    spec: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """実executorが未登録tokenをSQL到達前に拒否する。"""
    unregistered_type = type("UnregisteredStartedRead", (spec.token_type,), {})
    token = unregistered_type(uuid4())
    assert type(token) not in {r.token_type for r in PRODUCT_OPERATIONS}
    with pytest.raises(RuntimeError, match="未登録"):
        _operation_spec(token)

    class NoExecute:
        """未登録tokenがSQLへ来たら試験を失敗させる。"""

        def execute(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("unregistered SQL")

    context = make_tenant_context(uuid4())
    key = object()
    monkeypatch.setitem(transaction._TRANSACTION_RUNTIMES, key, (NoExecute(), object()))
    handle = transaction._TenantTransaction(
        context,
        key,
        context.tenant_id,
        context._integrity_proof,
        transaction._HANDLE_CREATION_TOKEN,
    )
    with pytest.raises(RuntimeError, match="未登録"):
        handle.run(token)
    handle._expire()
    with pytest.raises(RuntimeError, match="失効"):
        handle.run(token)


def test_prepare_never_accepts_a_different_candidate_type() -> None:
    """同じUUIDや能力名でも候補の型を取り替えない。"""
    for spec, other in zip(
        STARTED_SNAPSHOT_OPERATIONS, reversed(STARTED_SNAPSHOT_OPERATIONS), strict=True
    ):
        with pytest.raises(ValueError):
            spec.prepare(cast(Any, other.token_type)(uuid4()))


def test_four_candidates_reuse_exact_existing_read_capabilities() -> None:
    """新grant/function権限を作らず既read四件だけを参照する。"""
    assert {s.capability_id for s in STARTED_SNAPSHOT_OPERATIONS} == {
        "CAP:game_lineups:read",
        "CAP:event_slots:read",
        "CAP:operation_events:read",
        "CAP:play_rows:read",
    }


@pytest.mark.parametrize("spec", STARTED_SNAPSHOT_OPERATIONS)
def test_registered_read_uses_actual_handle_tenant_and_fixed_bounds(
    spec: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """実handleがexact型を解決し、呼出側にtenant変更を委ねない。"""
    token = spec.token_type(uuid4())
    assert _operation_spec(token) is spec
    assert sum(r.token_type is type(token) for r in PRODUCT_OPERATIONS) == 1
    seen: list[tuple[Any, dict[str, Any]]] = []

    class RecordingSession:
        """SQLの実行入口と束縛値だけを観測する。DB成功は主張しない。"""

        def execute(self, statement: Any, parameters: dict[str, Any]) -> tuple[()]:
            seen.append((statement, parameters))
            return ()

    context = make_tenant_context(uuid4())
    key = object()
    monkeypatch.setitem(
        transaction._TRANSACTION_RUNTIMES, key, (RecordingSession(), object())
    )
    handle = transaction._TenantTransaction(
        context,
        key,
        context.tenant_id,
        context._integrity_proof,
        transaction._HANDLE_CREATION_TOKEN,
    )
    result = handle.run(token)
    assert result.rows == ()
    assert len(seen) == 1
    statement, parameters = seen[0]
    assert statement.compare(spec.statement)
    assert dict(statement.get_execution_options()) == {"preserve_rowcount": True}
    assert parameters == {
        "tenant_id": context.tenant_id,
        "game_id": token.game_id,
        "limit": 3 if type(token) is StartedLineupsReadToken else 1,
    }
    handle._expire()
    with pytest.raises(RuntimeError, match="失効"):
        handle.run(token)
    assert len(seen) == 1
