"""同writer保存用4関数の実registry境界。実DB成功とは区別する。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import transaction
from pitchlog.repositories.first_ball import (
    _BindFirstBallDeviceToken,
    _CheckFirstBallRightToken,
)
from pitchlog.repositories.function_operations import FunctionOperationError
from pitchlog.repositories.operation_registry import (
    FUNCTION_OPERATION_REGISTRY,
    PRODUCT_FUNCTION_OPERATIONS,
)
from pitchlog.repositories.writer_binding import (
    _AssertWriterBindingToken,
    _ReadWriterIdentityToken,
)

_IDS = tuple(UUID(int=k) for k in range(1, 7))
_NOW = datetime(2026, 10, 27, tzinfo=UTC)
_CASES = (
    (
        _BindFirstBallDeviceToken(
            _IDS[1], _IDS[2], b"n" * 32, _IDS[3], _IDS[4], b"c" * 32
        ),
        ((True,),),
    ),
    (
        _CheckFirstBallRightToken(
            _IDS[1], _IDS[2], b"n" * 32, _IDS[3], _IDS[4], 2**31, 2**31 + 1, b"p" * 32
        ),
        ((True, True),),
    ),
    (
        _ReadWriterIdentityToken(),
        (("123", "42", _NOW, 123, _NOW, "18446744073709551615"),),
    ),
    (
        _AssertWriterBindingToken(_IDS[1], _IDS[2], b"n" * 32, _IDS[3], _IDS[4]),
        ((None,),),
    ),
)


def _handle(monkeypatch: pytest.MonkeyPatch, rows: tuple[Any, ...]):
    """実handleへSession doubleだけを渡し、実SQL成功を偽装しない。"""
    seen: list[tuple[Any, dict[str, Any]]] = []

    class SessionDouble:
        """実行入口のSQL/bindとcanonical結果を観測する。"""

        def execute(self, statement: Any, parameters: dict[str, Any]):
            seen.append((statement, parameters))
            return rows

    context = make_tenant_context(_IDS[0])
    key = object()
    monkeypatch.setitem(
        transaction._TRANSACTION_RUNTIMES, key, (SessionDouble(), object())
    )
    handle = transaction._TenantTransaction(
        context,
        key,
        context.tenant_id,
        context._integrity_proof,
        transaction._HANDLE_CREATION_TOKEN,
    )
    return handle, context, seen


@pytest.mark.parametrize("token,rows", _CASES)
def test_four_exact_tokens_dispatch_with_same_tenant_and_canonical_rows(
    token: Any, rows: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """実registry型4だけを同scopeへ束縛し、失効後の再実行を拒否する。"""
    handle, context, seen = _handle(monkeypatch, rows)
    spec = FUNCTION_OPERATION_REGISTRY[type(token)]
    assert (
        sum(row.token_type is type(token) for row in PRODUCT_FUNCTION_OPERATIONS) == 1
    )
    assert handle.run_function(token).rows == rows
    assert len(seen) == 1
    statement, parameters = seen[0]
    assert statement is spec.statement
    assert parameters == {
        "tenant_id": context.tenant_id,
        **{name: getattr(token, name) for name, _ in spec.input_fields},
    }
    handle._expire()
    with pytest.raises(RuntimeError, match="失効"):
        handle.run_function(token)
    assert len(seen) == 1


@pytest.mark.parametrize("token,rows", _CASES)
def test_same_capability_unregistered_subclass_never_reaches_sql(
    token: Any, rows: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """capability文字列を継承してもexact型でなければ拒否する。"""
    subtype = type("UnregisteredFunction", (type(token),), {})
    spec = FUNCTION_OPERATION_REGISTRY[type(token)]
    forged = subtype(**{name: getattr(token, name) for name, _ in spec.input_fields})
    handle, _, seen = _handle(monkeypatch, rows)
    with pytest.raises(FunctionOperationError, match="未登録または偽造"):
        handle.run_function(forged)
    assert seen == []
    handle._expire()


@pytest.mark.parametrize("token,rows", _CASES)
def test_mutated_tenant_is_rejected_before_sql(
    token: Any, rows: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """元contextのtenant改変も発行証跡の照合で拒否する。"""
    handle, context, seen = _handle(monkeypatch, rows)
    object.__setattr__(context, "tenant_id", _IDS[-1])
    with pytest.raises(RuntimeError, match="発行証跡"):
        handle.run_function(token)
    assert seen == []
    handle._expire()


@pytest.mark.parametrize("token,rows", _CASES)
def test_missing_result_never_becomes_success(
    token: Any, rows: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """実行したという事実だけで欠損応答を成功へ補わない。"""
    del rows
    handle, _, seen = _handle(monkeypatch, ())
    with pytest.raises(FunctionOperationError, match="戻り行数"):
        handle.run_function(token)
    assert len(seen) == 1
    handle._expire()
