"""RG1の固定照合・実識別登録と、常閉拒否を確認する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from pitchlog.repositories.first_ball import (
    _BindFirstBallDeviceToken,
    _CheckFirstBallRightToken,
    _ReadFirstBallDeviceStateToken,
)
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    decode_function_result,
    prepare_function_operation,
)
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.repositories.ordinary_order import OrdinaryOrderSummaryToken
from pitchlog.repositories.ordinary_pitch_qualification import (
    BindOrdinaryDeviceToken,
    CheckOrdinaryRightToken,
    PrepareOrdinaryProjectionToken,
)
from pitchlog.repositories.ordinary_prefix_operations import (
    OrdinaryCheckpointLockToken,
    OrdinaryCheckpointReadToken,
    OrdinaryHistoryPageToken,
)
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
from pitchlog.repositories.writer_binding import (
    _AssertWriterBindingToken,
    _ReadWriterIdentityToken,
)
from pitchlog.sync.terminal_pitch_tokens import (
    PlayPrefixCheckpointLockToken,
    PlayPrefixCheckpointReadToken,
    PlayPrefixHistoryPageToken,
    PreparePlayPrefixProjectionToken,
)

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
    from pitchlog.repositories.batted_ball_options import BattedBallOptionsToken
    from pitchlog.sync.terminal_pitch_tokens import LineupStartedOriginReadToken

    assert set(FUNCTION_OPERATION_REGISTRY) == {
        RG1PrecheckToken,
        RG1ScopeBindingToken,
        RG1CommitCheckToken,
        StageAResolveRuleToken,
        _BindFirstBallDeviceToken,
        _CheckFirstBallRightToken,
        _ReadWriterIdentityToken,
        _AssertWriterBindingToken,
        _ReadFirstBallDeviceStateToken,
        BindOrdinaryDeviceToken,
        CheckOrdinaryRightToken,
        PrepareOrdinaryProjectionToken,
        OrdinaryCheckpointReadToken,
        OrdinaryCheckpointLockToken,
        OrdinaryHistoryPageToken,
        OrdinaryOrderSummaryToken,
        # 正式repository契約のSYNC_PLAY_PREFIX固定4操作。
        PlayPrefixCheckpointReadToken,
        PlayPrefixCheckpointLockToken,
        PlayPrefixHistoryPageToken,
        PreparePlayPrefixProjectionToken,
        # 固定9b76の同tenant・実started原本read1だけを閉追加する。
        LineupStartedOriginReadToken,
        BattedBallOptionsToken,
    }
    assert len(FUNCTION_OPERATION_REGISTRY) == 22
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


def test_recording_vocab_function_registration_keeps_table_registry() -> None:
    """table66を増やさず、新function1の全公開属性を固定する。"""
    from pitchlog.repositories.base import _OPERATION_REGISTRY
    from pitchlog.repositories.batted_ball_options import (
        BATTED_BALL_OPTIONS_OPERATIONS,
        BattedBallOptionsToken,
    )

    spec = FUNCTION_OPERATION_REGISTRY[BattedBallOptionsToken]
    assert spec is BATTED_BALL_OPTIONS_OPERATIONS[0]
    assert len(BATTED_BALL_OPTIONS_OPERATIONS) == 1
    assert spec.operation_id == "RECORDING_VOCABULARIES:read_batted_ball_options"
    assert spec.function_id == "recording_vocab_api.read_batted_ball_options"
    assert spec.capability_id == "CAP:recording_vocabularies:read"
    assert spec.token_type is BattedBallOptionsToken
    assert spec.input_fields == (("page_size", int), ("cursor_key", str))
    assert spec.result_fields == (("key", str), ("display_name", str))
    assert (spec.min_rows, spec.max_rows) == (0, 101)
    assert (
        spec.nonempty_inputs
        == spec.nullable_results
        == spec.aware_datetime_results
        == ()
    )
    assert BattedBallOptionsToken not in _OPERATION_REGISTRY
    assert len(_OPERATION_REGISTRY) == 66
    actual, parameters = prepare_function_operation(
        BattedBallOptionsToken(page_size=31, cursor_key="previous"),
        _TENANT_ID,
        FUNCTION_OPERATION_REGISTRY,
    )
    assert actual is spec
    assert parameters == {
        "tenant_id": _TENANT_ID,
        "page_size": 31,
        "cursor_key": "previous",
    }
    result = TenantOperationResult((("observed-key", "表示"),))
    assert spec.decoder(result) is result


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation_id", "UNKNOWN:read"),
        ("capability_id", "CAP:games:read"),
        ("input_fields", (("page_size", bool), ("cursor_key", str))),
        ("result_fields", (("key", str), ("display_name", int))),
        ("min_rows", 1),
        ("max_rows", 100),
        ("nonempty_inputs", ("cursor_key",)),
        ("nullable_results", ("key",)),
        ("aware_datetime_results", ("key",)),
    ],
)
def test_recording_vocab_function_registration_rejects_field_substitution(
    field: str, value: object
) -> None:
    """新1登録の操作/型/上限等を独立な別宣言へ差し替えできない。"""
    from dataclasses import replace

    from pitchlog.repositories.batted_ball_options import BattedBallOptionsToken

    spec = FUNCTION_OPERATION_REGISTRY[BattedBallOptionsToken]
    with pytest.raises(FunctionOperationError):
        replace(spec, **cast(Any, {field: value}))
