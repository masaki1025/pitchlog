"""固定関数登録と同一scope実行の閉鎖境界を確認する。"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Integer, bindparam, delete, func, select, table, text
from sqlalchemy.sql.selectable import Select
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import operation_registry, transaction
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    FunctionOperationRegistration,
    build_function_registry,
    decode_function_result,
    prepare_function_operation,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

_TENANT_ID = UUID("00000000-0000-0000-0000-000000000550")


@dataclass(frozen=True, slots=True)
class _FixedToken(TenantOperationToken):
    """試験専用の閉じた関数token。"""

    marker: str = "one"
    claimed_capability: str = "CAP:test:fixed"

    @property
    def capability_id(self) -> str:
        """登録済みcapabilityを返す。"""
        return self.claimed_capability


@dataclass(frozen=True, slots=True)
class _UnregisteredToken(TenantOperationToken):
    """未登録関数token。"""

    @property
    def capability_id(self) -> str:
        """偽のcapabilityを返す。"""
        return "CAP:test:fixed"


@dataclass(frozen=True, slots=True)
class _DerivedToken(_FixedToken):
    """登録型から派生した偽造token。"""


def _registration() -> FunctionOperationRegistration:
    """単一のschema修飾関数を試験内だけに登録する。"""
    statement = select(
        func.public.fixed_probe(bindparam("tenant_id"), bindparam("marker")).label(
            "value"
        )
    )
    return FunctionOperationRegistration(
        operation_id="test.fixed_probe",
        token_type=_FixedToken,
        capability_id="CAP:test:fixed",
        function_id="public.fixed_probe",
        statement=statement,
        input_fields=(("marker", str),),
        result_fields=(("value", str),),
        min_rows=1,
        max_rows=1,
        decoder=lambda result: result,
    )


def test_product_function_registry_is_empty_and_dml_is_unchanged() -> None:
    """Aの製品関数登録は0件で既存DML登録は維持する。"""
    assert operation_registry.PRODUCT_FUNCTION_OPERATIONS == ()
    assert operation_registry.FUNCTION_OPERATION_REGISTRY == {}
    assert operation_registry.PRODUCT_OPERATIONS


def test_fixed_registration_prepares_exact_tenant_and_token_input() -> None:
    """Tenant IDはscopeからだけ渡し、入力はexact型とする。"""
    spec = _registration()
    registry = build_function_registry((spec,), frozenset())
    assert type(registry) is MappingProxyType
    assert prepare_function_operation(_FixedToken(), _TENANT_ID, registry) == (
        spec,
        {"tenant_id": _TENANT_ID, "marker": "one"},
    )
    with pytest.raises(FunctionOperationError, match="未登録または偽造"):
        prepare_function_operation(_UnregisteredToken(), _TENANT_ID, registry)
    with pytest.raises(FunctionOperationError, match="未登録または偽造"):
        prepare_function_operation(_DerivedToken(), _TENANT_ID, registry)
    with pytest.raises(FunctionOperationError, match="capability ID"):
        prepare_function_operation(
            _FixedToken(claimed_capability="forged"), _TENANT_ID, registry
        )
    with pytest.raises(FunctionOperationError, match="型が不一致"):
        prepare_function_operation(_FixedToken(marker=1), _TENANT_ID, registry)  # ty: ignore[invalid-argument-type]


def test_fixed_table_valued_function_has_declared_columns() -> None:
    """複数戻り列でも単一のschema修飾関数と固定列だけを許す。"""
    table = func.public.fixed_probe(
        bindparam("tenant_id"), bindparam("marker")
    ).table_valued("value", "revision")
    spec = replace(
        _registration(),
        statement=select(table.c.value, table.c.revision),
        result_fields=(("value", str), ("revision", int)),
    )
    result = TenantOperationResult(rows=(("ok", 1),))
    assert decode_function_result(spec, result) is result


@pytest.mark.parametrize(
    "statement",
    (
        text("SELECT public.fixed_probe(:tenant_id, :marker)"),
        select(
            func.fixed_probe(bindparam("tenant_id"), bindparam("marker")).label("value")
        ),
        select(
            func.public.other(bindparam("tenant_id"), bindparam("marker")).label(
                "value"
            )
        ),
        select(
            func.public.fixed_probe(bindparam("tenant_id"), bindparam("other")).label(
                "value"
            )
        ),
        select(
            func.public.fixed_probe(
                bindparam("tenant_id"), bindparam("marker", type_=Integer)
            ).label("value")
        ),
        select(
            func.public.fixed_probe(
                bindparam("tenant_id", literal_execute=True), bindparam("marker")
            ).label("value")
        ),
        select(
            func.public.fixed_probe(
                bindparam("tenant_id"), bindparam("marker", literal_execute=True)
            ).label("value")
        ),
        select(
            func.public.fixed_probe(
                bindparam("tenant_id", expanding=True), bindparam("marker")
            ).label("value")
        ),
        select(
            func.public.fixed_probe(
                bindparam("tenant_id"), bindparam("marker", expanding=True)
            ).label("value")
        ),
        select(
            func.public.fixed_probe(bindparam("tenant_id"), bindparam("marker")).label(
                "value"
            )
        ).where(text("true")),
        select(
            func.public.fixed_probe(bindparam("tenant_id"), bindparam("marker")).label(
                "value"
            )
        ).add_cte(delete(table("other_tenant_data")).cte("wipe")),
    ),
)
def test_registration_rejects_arbitrary_sql_and_changed_function(
    statement: object,
) -> None:
    """任意SQL、別関数、bind変形、追加述語・DML CTEを拒否する。"""
    with pytest.raises(FunctionOperationError):
        replace(_registration(), statement=statement)  # type: ignore[arg-type]


def test_function_registry_rejects_dml_and_duplicate_registration() -> None:
    """DML token型または関数operation IDの重複を拒否する。"""
    spec = _registration()
    with pytest.raises(FunctionOperationError, match="重複"):
        build_function_registry((spec,), frozenset({_FixedToken}))
    with pytest.raises(FunctionOperationError, match="重複"):
        build_function_registry((spec, spec), frozenset())
    with pytest.raises(FunctionOperationError, match="重複"):
        build_function_registry((spec,), frozenset(), frozenset({"test.fixed_probe"}))
    with pytest.raises(FunctionOperationError, match="重複"):
        build_function_registry((spec,), frozenset(), frozenset({"CAP:test:fixed"}))


def test_function_entry_exposes_no_session_sql_or_tenant_argument() -> None:
    """callerへSession、任意SQL、tenant IDの引数を公開しない。"""
    assert tuple(
        inspect.signature(transaction._TenantTransaction.run_function).parameters
    ) == (
        "self",
        "operation",
    )
    assert "_session" not in transaction._TenantTransaction.__slots__


def test_decoder_rejects_wrong_columns_types_and_return_type() -> None:
    """戻り行を固定列・exact型・不変DTOへ閉じる。"""
    spec = _registration()
    result = TenantOperationResult(rows=(("ok",),))
    assert decode_function_result(spec, result) is result
    with pytest.raises(FunctionOperationError, match="戻り列"):
        decode_function_result(spec, TenantOperationResult(rows=((1,),)))
    with pytest.raises(FunctionOperationError, match="戻り列"):
        decode_function_result(spec, TenantOperationResult(rows=(("ok", "extra"),)))
    with pytest.raises(FunctionOperationError, match="戻り行数"):
        decode_function_result(spec, TenantOperationResult(rows=()))
    with pytest.raises(FunctionOperationError, match="decoder"):
        decode_function_result(replace(spec, decoder=lambda _: "bad"), result)  # type: ignore[arg-type]
    with pytest.raises(FunctionOperationError, match="戻り列"):
        decode_function_result(
            replace(
                spec, decoder=lambda _: TenantOperationResult(rows=((17, "extra"),))
            ),
            result,
        )
    with pytest.raises(FunctionOperationError, match="戻り行数"):
        decode_function_result(
            replace(spec, decoder=lambda _: TenantOperationResult(rows=())), result
        )


def test_run_function_rejects_unregistered_before_session_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """製品registry空集合ではSessionへ到達する前に拒否する。"""

    class _NoExecuteSession:
        """SQL実行を許可しない試験用Session。"""

        def execute(self, statement: Select[Any], params: object) -> None:
            """未登録tokenが来たら試験を失敗させる。"""
            raise AssertionError("Session.executeへ到達した")

    context = make_tenant_context(_TENANT_ID)
    state_key = object()
    monkeypatch.setitem(
        transaction._TRANSACTION_RUNTIMES, state_key, (_NoExecuteSession(), object())
    )
    handle = transaction._TenantTransaction(
        context,
        state_key,
        _TENANT_ID,
        context._integrity_proof,
        transaction._HANDLE_CREATION_TOKEN,
    )
    with pytest.raises(FunctionOperationError, match="未登録または偽造"):
        handle.run_function(_FixedToken())
    handle._expire()
    with pytest.raises(RuntimeError, match="失効"):
        handle.run_function(_FixedToken())


def test_registered_function_uses_same_scope_and_rolls_back_on_decoder_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """試験専用登録を同じ入口で実行し、decoder失敗を全取消へ渡す。"""
    events: list[str] = []

    class _FakeSession:
        """固定結果だけを返す閉じた試験用Session。"""

        def __init__(self, engine: object) -> None:
            """scopeが生成したことを記録する。"""
            events.append("session")

        def execute(self, statement: Select[Any], params: object) -> list[tuple[str]]:
            """関数文とscope由来tenant IDを照合する。"""
            assert statement is spec.statement
            assert params == {"tenant_id": _TENANT_ID, "marker": "one"}
            events.append("execute")
            return [("ok",)]

        def close(self) -> None:
            """scopeの終了で閉じる。"""
            events.append("close")

    @contextmanager
    def _binding(session: object, context: object) -> Iterator[None]:
        """既存のtransaction境界へ成功・失敗を委ねる。"""
        events.append("begin")
        try:
            yield
        except BaseException:
            events.append("rollback")
            raise
        else:
            events.append("commit")

    spec = _registration()
    monkeypatch.setattr(transaction, "Session", _FakeSession)
    monkeypatch.setattr(transaction, "create_database_engine", object)
    monkeypatch.setattr(transaction, "_tenant_transaction", _binding)
    monkeypatch.setattr(
        transaction,
        "FUNCTION_OPERATION_REGISTRY",
        build_function_registry((spec,), frozenset()),
    )
    with transaction.tenant_transaction_scope(make_tenant_context(_TENANT_ID)) as scope:
        assert scope.run_function(_FixedToken()).rows == (("ok",),)
    assert events == ["session", "begin", "execute", "commit", "close"]

    events.clear()

    def _raise_decoder(result: TenantOperationResult) -> TenantOperationResult:
        """decoder故障を注入する。"""
        raise ValueError("decoder failure")

    monkeypatch.setattr(
        transaction,
        "FUNCTION_OPERATION_REGISTRY",
        build_function_registry((replace(spec, decoder=_raise_decoder),), frozenset()),
    )
    with pytest.raises(ValueError, match="decoder failure"):
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            scope.run_function(_FixedToken())
    assert events == ["session", "begin", "execute", "rollback", "close"]

    events.clear()
    context = make_tenant_context(_TENANT_ID)
    with pytest.raises(TenantBindingError, match="発行証跡"):
        with transaction.tenant_transaction_scope(context) as scope:
            object.__setattr__(
                context, "tenant_id", UUID("00000000-0000-0000-0000-000000000551")
            )
            scope.run_function(_FixedToken())
    assert events == ["session", "begin", "rollback", "close"]


def test_run_function_stops_reading_after_declared_row_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """過剰行は上限の次の1行で検出し、全件読み込まず全取消する。"""
    observed: list[str] = []

    class _RowsSession:
        """過剰行を返す試験専用Session。"""

        def __init__(self, engine: object) -> None:
            """scopeから生成する。"""

        def execute(
            self, statement: Select[Any], params: object
        ) -> Iterator[tuple[str]]:
            """3行目を読んだ場合に試験を失敗させる。"""
            for index in range(3):
                if index == 2:
                    raise AssertionError("上限を超えて全件読み込んだ")
                observed.append("read")
                yield ("ok",)

        def close(self) -> None:
            """scope終了で閉じる。"""
            observed.append("close")

    @contextmanager
    def _binding(session: object, context: object) -> Iterator[None]:
        """失敗時の全取消を観測する。"""
        try:
            yield
        except BaseException:
            observed.append("rollback")
            raise

    monkeypatch.setattr(transaction, "Session", _RowsSession)
    monkeypatch.setattr(transaction, "create_database_engine", object)
    monkeypatch.setattr(transaction, "_tenant_transaction", _binding)
    monkeypatch.setattr(
        transaction,
        "FUNCTION_OPERATION_REGISTRY",
        build_function_registry((_registration(),), frozenset()),
    )
    with pytest.raises(FunctionOperationError, match="戻り行数"):
        with transaction.tenant_transaction_scope(
            make_tenant_context(_TENANT_ID)
        ) as scope:
            scope.run_function(_FixedToken())
    assert observed == ["read", "read", "rollback", "close"]
