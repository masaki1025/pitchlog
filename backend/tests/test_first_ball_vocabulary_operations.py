"""未登録tenant球種readのpure境界。実DB・global結果・保存成功ではない。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import Integer, Select, Table, bindparam, func, select
from sqlalchemy.dialects import postgresql
from test_authz_tenant_context import make_tenant_context

from pitchlog.db.tenant_isolation.models import AdminVocabulary, TenantVocabulary
from pitchlog.repositories import base, transaction
from pitchlog.repositories.first_ball_vocabulary_operations import (
    _UNREGISTERED_TENANT_PITCH_TYPES,
    FirstBallVocabularyError,
    TenantPitchTypeReadToken,
    is_enabled_tenant_pitch_type,
)
from pitchlog.repositories.operation_registry import PRODUCT_OPERATIONS
from pitchlog.repositories.tokens import TenantOperationResult

_SPEC = _UNREGISTERED_TENANT_PITCH_TYPES[0]
_TABLE = cast(Table, TenantVocabulary.__table__)
_KEY = "tenant-fastball"


class StringSubtype(str):
    """同値でもexact文字列でない入力を作る。"""


def test_fixed_three_columns_tenant_key_and_limit_sql() -> None:
    """SQLと全宣言を比較し、登録やglobal読取を供給しない。"""
    token = TenantPitchTypeReadToken(_KEY)
    statement, params = _SPEC.prepare(token)
    assert isinstance(statement, Select)
    assert len(_UNREGISTERED_TENANT_PITCH_TYPES) == 1
    assert _SPEC.token_type is TenantPitchTypeReadToken
    assert _SPEC.capability_id == token.capability_id == "CAP:tenant_vocabularies:read"
    assert _SPEC.tenant_column is _TABLE.c.tenant_id
    assert statement is _SPEC.statement
    assert statement.get_final_froms() == [_TABLE]
    assert tuple(statement.selected_columns) == (
        _TABLE.c.key,
        _TABLE.c.category,
        _TABLE.c.disabled,
    )
    assert params == {"pitch_type_key": _KEY, "limit": 2}
    assert [field.name for field in fields(token)] == ["pitch_type_key"]
    assert _SPEC.required_limit_parameter == "limit" and _SPEC.required_limit_max == 2
    assert not _SPEC.required_bindings and not _SPEC.primary_key_bindings
    assert _SPEC.preflight is _SPEC.allowed_update_columns is None
    assert _SPEC.for_update is _SPEC.use_capability_lock_shape is False
    compiled = statement.compile(dialect=postgresql.dialect())
    assert str(compiled) == (
        "SELECT tenant_vocabularies.key, tenant_vocabularies.category, "
        "tenant_vocabularies.disabled \nFROM tenant_vocabularies \n"
        "WHERE tenant_vocabularies.tenant_id = %(tenant_id)s::UUID AND "
        "tenant_vocabularies.key = %(pitch_type_key)s \n LIMIT %(limit)s"
    )
    assert set(compiled.params) == {"tenant_id", "pitch_type_key", "limit"}
    base._TenantScopedOperation(_SPEC.capability_id, statement, _SPEC.tenant_column)
    base._validate_prepared_statement(_SPEC, statement, params | {"tenant_id": uuid4()})


@pytest.mark.parametrize("bad", [None, True, 1, uuid4(), "", StringSubtype(_KEY)])
def test_constructor_and_forced_field_change_rejected(bad: Any) -> None:
    """構築と使用時の両方で暗黙変換・変異を拒否する。"""
    with pytest.raises(FirstBallVocabularyError):
        TenantPitchTypeReadToken(bad)
    token = TenantPitchTypeReadToken(_KEY)
    object.__setattr__(token, "pitch_type_key", bad)
    with pytest.raises(FirstBallVocabularyError):
        _SPEC.prepare(token)
    with pytest.raises(FirstBallVocabularyError):
        is_enabled_tenant_pitch_type(TenantOperationResult(()), bad)


@pytest.mark.parametrize("name", ["tenant_id", "limit", "category", "disabled", "sql"])
def test_no_extra_parameters_or_mutation(name: str) -> None:
    """資格や任意SQL・上限をtokenへ注入しない。"""
    with pytest.raises(TypeError):
        TenantPitchTypeReadToken(_KEY, **{name: None})
    token = TenantPitchTypeReadToken(_KEY)
    with pytest.raises(FrozenInstanceError):
        setattr(token, "pitch_type_key", "changed")


def test_no_key_normalization() -> None:
    """空白・表示名・SQL文字列を補完や実行せず元bind値として保持する。"""
    for key in (" ", "直球", "' OR true --"):
        _, params = _SPEC.prepare(TenantPitchTypeReadToken(key))
        assert params == {"pitch_type_key": key, "limit": 2}


@pytest.mark.parametrize("kind", ["exact", "subtype", "sibling"])
def test_unregistered_real_handle_has_zero_sql(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """実handle/contextのpure fixtureで未登録型はSQL前拒否する。"""
    cls: Any = (
        TenantPitchTypeReadToken
        if kind == "exact"
        else type("Derived", (TenantPitchTypeReadToken,), {})
        if kind == "subtype"
        else type("SameCap", (), {"capability_id": _SPEC.capability_id})
    )
    token: Any = cls(_KEY) if kind != "sibling" else cls()
    assert cls not in base._OPERATION_REGISTRY
    assert all(spec.token_type is not cls for spec in PRODUCT_OPERATIONS)
    if kind != "exact":
        with pytest.raises(FirstBallVocabularyError):
            _SPEC.prepare(token)
    calls: list[Any] = []

    class NoExecute:
        """SQL発行を成功にせず、到達時点で失敗させる。"""

        def execute(self, *args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))
            raise AssertionError("未登録SQLへ到達")

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
    try:
        with pytest.raises(base._TenantOperationError, match="未登録"):
            handle.run(token)
    finally:
        handle._expire()
    with pytest.raises(RuntimeError, match="失効"):
        handle.run(token)
    assert calls == []


@pytest.mark.parametrize("bad_limit", [None, True, -1, 0, 3, "2"])
def test_real_validator_rejects_bad_limit(bad_limit: Any) -> None:
    """既validatorの上限/型拒否を維持する。"""
    statement, params = _SPEC.prepare(TenantPitchTypeReadToken(_KEY))
    assert isinstance(statement, Select)
    with pytest.raises(base._TenantOperationError):
        base._validate_prepared_statement(
            _SPEC, statement, params | {"tenant_id": uuid4(), "limit": bad_limit}
        )


@pytest.mark.parametrize(
    "mutation", ["missing-tenant", "global-table", "function", "lock"]
)
def test_real_validator_rejects_non_equivalent_sql(mutation: str) -> None:
    """同型登録でもtenant消失・global偽装・副作用/lockを拒否する。"""
    statement, params = _SPEC.prepare(TenantPitchTypeReadToken(_KEY))
    assert isinstance(statement, Select)
    spec = _SPEC
    if mutation == "missing-tenant":
        statement = (
            select(_TABLE.c.key, _TABLE.c.category, _TABLE.c.disabled)
            .where(_TABLE.c.key == bindparam("pitch_type_key"))
            .limit(bindparam("limit", type_=Integer))
        )
    elif mutation == "global-table":
        table = cast(Table, AdminVocabulary.__table__)
        statement = select(table.c.key).limit(bindparam("limit", type_=Integer))
        spec = replace(_SPEC, tenant_column=table.c.key)
    elif mutation == "function":
        statement = select(func.set_config("app.tenant_id", "bad", True))
    else:
        statement = statement.with_for_update()
    with pytest.raises(base._TenantOperationError):
        # 実prepareと同順にtenant必須検査→固定文検査を行う。
        base._TenantScopedOperation(spec.capability_id, statement, spec.tenant_column)
        base._validate_prepared_statement(
            spec, statement, params | {"tenant_id": uuid4()}
        )


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ((), False),
        (((_KEY, "pitch_type", False),), True),
        (((_KEY, "pitch_type", True),), False),
        (((_KEY, "strategy", False),), False),
    ],
)
def test_enabled_is_only_tenant_pitch_type_result(rows: Any, expected: bool) -> None:
    """有効球種だけがTrueで、global ballの成立へ昇格しない。"""
    assert is_enabled_tenant_pitch_type(TenantOperationResult(rows), _KEY) is expected


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [(_KEY, "pitch_type", False)],
        ([_KEY, "pitch_type", False],),
        ((_KEY, "pitch_type"),),
        ((_KEY, "pitch_type", False, 1),),
        (("different", "pitch_type", False),),
        ((StringSubtype(_KEY), "pitch_type", False),),
        ((_KEY, StringSubtype("pitch_type"), False),),
        ((_KEY, "pitch_type", 0),),
        ((_KEY, "pitch_type", None),),
        ((_KEY, "pitch_type", False), (_KEY, "pitch_type", False)),
    ],
)
def test_bad_result_is_exception_not_false(rows: Any) -> None:
    """実行器の契約違反を内容拒否へ畳まず、NULLやbool-intも区別する。"""
    with pytest.raises(FirstBallVocabularyError):
        is_enabled_tenant_pitch_type(TenantOperationResult(rows), _KEY)


def test_result_type_is_exact() -> None:
    """同型の手作り値で正規結果形を代替しない。"""
    for result in (None, object(), type("Result", (), {"rows": ()})()):
        with pytest.raises(FirstBallVocabularyError):
            is_enabled_tenant_pitch_type(cast(Any, result), _KEY)


def test_missing_forced_fields_are_fixed_boundary_errors() -> None:
    """同じexact型の未構築参照も固定例外で閉じる。"""
    token = object.__new__(TenantPitchTypeReadToken)
    with pytest.raises(FirstBallVocabularyError):
        _SPEC.prepare(token)
    result = object.__new__(TenantOperationResult)
    with pytest.raises(FirstBallVocabularyError):
        is_enabled_tenant_pitch_type(result, _KEY)


def test_unknown_result_property_is_not_executed() -> None:
    """型拒否の前に未知propertyを呼び、副作用や例外を実行しない。"""
    calls = []

    class UnknownResult:
        """未知結果に読取副作用と元例外を仕込む。"""

        @property
        def rows(self) -> tuple:
            """到達した時点で固定拒否の迂回を検出する。"""
            calls.append(True)
            raise RuntimeError("未知結果のpropertyへ到達")

    for result in (UnknownResult(),):
        with pytest.raises(FirstBallVocabularyError):
            is_enabled_tenant_pitch_type(cast(Any, result), _KEY)
    assert calls == []
