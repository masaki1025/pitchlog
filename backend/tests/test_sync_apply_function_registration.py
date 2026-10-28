"""同writer保存用4関数と端末状態readの実registry境界。実DBとは区別する。"""

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
    _ReadFirstBallDeviceStateToken,
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


@pytest.mark.parametrize("active", [True, False])
def test_device_state_read_exact_registration_and_fixed_sql(active, monkeypatch):
    """Pure Session上で実登録と固定SQLを照合し、falseを成功へ直さない。"""
    from sqlalchemy.dialects.postgresql import psycopg

    token = _ReadFirstBallDeviceStateToken(_IDS[3])
    handle, context, seen = _handle(monkeypatch, ((active,),))
    spec = FUNCTION_OPERATION_REGISTRY[type(token)]
    assert PRODUCT_FUNCTION_OPERATIONS[-1] is spec
    assert spec.operation_id == "SYNC_FIRST_BALL:read_device_state"
    assert spec.function_id == "sync_right_api.read_device_state"
    assert spec.input_fields == (("device_id", UUID),)
    assert spec.result_fields == (("device_active", bool),)
    assert (spec.min_rows, spec.max_rows, spec.nullable_results) == (1, 1, ())
    assert handle.run_function(token).rows == ((active,),)
    assert len(seen) == 1
    statement, params = seen[0]
    assert statement is spec.statement
    assert params == {"tenant_id": context.tenant_id, "device_id": _IDS[3]}
    assert str(statement.compile(dialect=psycopg.dialect())) == (
        "SELECT anon_1.device_active \n"
        "FROM sync_right_api.read_device_state(%(tenant_id)s::UUID, "
        "%(device_id)s::UUID) AS anon_1"
    )
    handle._expire()
    with pytest.raises(RuntimeError, match="失効"):
        handle.run_function(token)
    assert len(seen) == 1


@pytest.mark.parametrize("kind", ["same-name", "same-cap", "derived"])
def test_device_state_unknown_exact_types_are_sql_zero(kind, monkeypatch):
    """正規exact型を許可し、名前/CAP/継承だけの類似型は拒否する。"""
    from dataclasses import dataclass

    from pitchlog.repositories.tokens import TenantOperationToken

    if kind == "derived":
        unknown = type("Derived", (_ReadFirstBallDeviceStateToken,), {})(_IDS[3])
    else:

        @dataclass(frozen=True)
        class Unknown(TenantOperationToken):
            """CAP文字列だけを装う未知型。"""

            device_id: UUID

            @property
            def capability_id(self):
                """正規文字列で型拒否を迂回できない。"""
                return "CAP:sync_first_ball:read_device_state"

        if kind == "same-name":
            Unknown.__name__ = "_ReadFirstBallDeviceStateToken"
        unknown = Unknown(_IDS[3])
    handle, _, seen = _handle(monkeypatch, ((True,),))
    with pytest.raises(FunctionOperationError, match="未登録または偽造"):
        handle.run_function(unknown)
    assert seen == []
    handle._expire()


@pytest.mark.parametrize("bad", [None, True, 1, "00000000-0000-0000-0000-000000000004"])
def test_device_state_mutated_input_is_sql_zero(bad, monkeypatch):
    """frozenを強制変更しても使用時exact UUID照合を省略しない。"""
    token = _ReadFirstBallDeviceStateToken(_IDS[3])
    object.__setattr__(token, "device_id", bad)
    handle, _, seen = _handle(monkeypatch, ((True,),))
    with pytest.raises(FunctionOperationError, match="入力device_idの型"):
        handle.run_function(token)
    assert seen == []
    handle._expire()


def test_device_state_uuid_subtype_is_sql_zero(monkeypatch):
    """UUID派生をexact UUIDへ補完しない。"""

    class DerivedUUID(UUID):
        """UUIDを装う派生型。"""

    token = _ReadFirstBallDeviceStateToken(DerivedUUID(int=4))
    handle, _, seen = _handle(monkeypatch, ((True,),))
    with pytest.raises(FunctionOperationError, match="入力device_idの型"):
        handle.run_function(token)
    assert seen == []
    handle._expire()


@pytest.mark.parametrize(
    "rows", [(), ((None,),), ((1,),), ((True, False),), ((True,), (False,))]
)
def test_device_state_bad_results_never_become_active(rows, monkeypatch):
    """実run_functionで欠損/NULL/数値bool/過剰列行を固定例外へする。"""
    handle, _, seen = _handle(monkeypatch, rows)
    with pytest.raises(FunctionOperationError, match="戻り"):
        handle.run_function(_ReadFirstBallDeviceStateToken(_IDS[3]))
    assert len(seen) == 1
    handle._expire()


@pytest.mark.parametrize(
    "kind", ["rg1-precheck", "rg1-commit", "device", "rights", "content"]
)
def test_device_state_port_phase_is_sql_zero(kind, monkeypatch):
    """Pure phase fixtureで実有限関数guardを通しreadを貸与しない。"""
    from types import SimpleNamespace

    handle, _, seen = _handle(monkeypatch, ((True,),))
    phase = SimpleNamespace(kind=kind)
    monkeypatch.setattr(transaction, "_port_phase", lambda actual: phase)
    with pytest.raises(RuntimeError, match="固定関数が未許可"):
        handle.run_function(_ReadFirstBallDeviceStateToken(_IDS[3]))
    assert seen == []
    handle._expire()


@pytest.mark.parametrize("phase", ["intent", "business", "enroll"])
def test_device_state_initial_actor_is_sql_zero(phase, monkeypatch):
    """actor実体検証だけをpure化しても、実actor許可集合はreadを拒否する。"""
    from pitchlog.recording_rights import initial_grant_broker as broker

    handle, context, seen = _handle(monkeypatch, ((True,),))
    actor = object()
    monkeypatch.setitem(
        transaction._INITIAL_ACTOR_STATES, handle._state_key, (actor, phase)
    )
    monkeypatch.setattr(broker, "_initial_actor_engine", lambda actual: None)
    if phase == "enroll":
        monkeypatch.setitem(
            transaction._ENROLL_BINDINGS,
            handle._state_key,
            transaction._EnrollmentBinding(context, actor, _IDS[3], b"c" * 32),
        )
    with pytest.raises(RuntimeError, match="初期権actorのphaseに未登録"):
        handle.run_function(_ReadFirstBallDeviceStateToken(_IDS[3]))
    assert seen == []
    handle._expire()


@pytest.mark.parametrize("change", ["tenant", "proof"])
def test_device_state_context_mutation_is_sql_zero(change, monkeypatch):
    """型が正しくても同scope発行証跡を変えた入力ではSQLを始めない。"""
    handle, context, seen = _handle(monkeypatch, ((True,),))
    if change == "tenant":
        object.__setattr__(context, "tenant_id", _IDS[-1])
    else:
        object.__setattr__(context, "_integrity_proof", b"wrong")
    with pytest.raises(RuntimeError, match="発行証跡"):
        handle.run_function(_ReadFirstBallDeviceStateToken(_IDS[3]))
    assert seen == []
    handle._expire()
