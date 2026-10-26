"""RG1の固定照合・実識別登録と、常閉拒否を確認する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    decode_function_result,
    prepare_function_operation,
)
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.repositories.rg1 import (
    RG1CommitCheckToken,
    RG1PrecheckToken,
    RG1ScopeBindingToken,
    RG1Unavailable,
    _build_rg1_read_statement,
    assert_rg1_open_before_commit,
    read_rg1_open,
)
from pitchlog.repositories.rule_resolution import StageAResolveRuleToken
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.repositories.transaction import _TenantTransaction

_TENANT_ID = UUID("00000000-0000-0000-0000-000000000392")


@dataclass(frozen=True, slots=True)
class _UnknownToken(TenantOperationToken):
    """登録外の偽装token。"""

    @property
    def capability_id(self) -> str:
        """既存capabilityを装う。"""
        return "CAP:rg1:precheck"


def test_rg1_keeps_two_fixed_functions_with_one_registered_rule_resolver() -> None:
    """resolver1件追加後も、RG1のtenant固定2関数と未知token拒否を保つ。"""
    assert set(FUNCTION_OPERATION_REGISTRY) == {
        RG1PrecheckToken,
        RG1ScopeBindingToken,
        RG1CommitCheckToken,
        StageAResolveRuleToken,
    }
    for token, function_name in (
        (RG1PrecheckToken(), "rg1_read_open"),
        (RG1CommitCheckToken(), "rg1_assert_open_before_commit"),
    ):
        spec, parameters = prepare_function_operation(
            token, _TENANT_ID, FUNCTION_OPERATION_REGISTRY
        )
        assert parameters == {"tenant_id": _TENANT_ID}
        assert spec.input_fields == ()
        assert spec.result_fields == (("is_open", bool),)
        assert (spec.min_rows, spec.max_rows) == (1, 1)
        compiled = str(spec.statement.compile(dialect=postgresql.dialect()))
        assert compiled == (
            f"SELECT rg1_api.{function_name}(%(tenant_id)s::UUID) AS is_open"
        )
        assert decode_function_result(
            spec, TenantOperationResult(rows=((False,),))
        ).rows == ((False,),)
        with pytest.raises(FunctionOperationError, match="戻り列"):
            decode_function_result(spec, TenantOperationResult(rows=((1,),)))
    with pytest.raises(FunctionOperationError, match="未登録または偽造"):
        prepare_function_operation(
            _UnknownToken(), _TENANT_ID, FUNCTION_OPERATION_REGISTRY
        )
    with pytest.raises(ValueError, match="未登録"):
        _build_rg1_read_statement(cast("object", "unknown"))  # ty: ignore[invalid-argument-type]


def test_rg1_service_uses_same_scope_and_rejects_closed_result() -> None:
    """事前・直前の両口が同じハンドルを使いfalseを成功にしない。"""
    seen: list[type[TenantOperationToken]] = []

    class _Scope:
        """選択されたtokenだけを記録する隔離スコープ。"""

        def run_function(self, token: TenantOperationToken) -> TenantOperationResult:
            """製品DB関数の常閉戻り値を返す。"""
            seen.append(type(token))
            return TenantOperationResult(rows=((False,),))

    scope = cast("_TenantTransaction", _Scope())
    with pytest.raises(RG1Unavailable, match="閉じている"):
        read_rg1_open(scope)
    with pytest.raises(RG1Unavailable, match="閉じている"):
        assert_rg1_open_before_commit(scope)
    assert seen == [RG1PrecheckToken, RG1CommitCheckToken]


def test_scope_binding_has_only_server_bound_tenant_and_text_result() -> None:
    """識別値をcaller入力で補完せず、制御operationを登録しない。"""
    spec, parameters = prepare_function_operation(
        RG1ScopeBindingToken(), _TENANT_ID, FUNCTION_OPERATION_REGISTRY
    )
    assert parameters == {"tenant_id": _TENANT_ID}
    assert spec.input_fields == ()
    assert spec.result_fields == (("binding", str),)
    assert (spec.min_rows, spec.max_rows) == (1, 1)
    assert str(spec.statement.compile(dialect=postgresql.dialect())) == (
        "SELECT rg1_control.scope_binding(%(tenant_id)s::UUID) AS binding"
    )
    assert decode_function_result(
        spec, TenantOperationResult(rows=(("{}",),))
    ).rows == (("{}",),)
    for bad in (None, True, 1, (), 1.5):
        with pytest.raises(FunctionOperationError):
            decode_function_result(spec, TenantOperationResult(rows=((bad,),)))
