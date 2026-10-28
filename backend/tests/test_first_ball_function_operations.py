"""初球exact2の型例外と旧一般bytes拒否の境界を確認する。"""

from dataclasses import replace
from uuid import UUID

import pytest

from pitchlog.repositories.first_ball import (
    _UNREGISTERED_DECLARATIONS,
    _BindFirstBallDeviceToken,
    _CheckFirstBallRightToken,
)
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    build_function_registry,
    decode_function_result,
    prepare_function_operation,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

_IDS = [UUID(int=i) for i in range(1, 7)]
_REGISTRY = build_function_registry(_UNREGISTERED_DECLARATIONS, frozenset())


def _device() -> _BindFirstBallDeviceToken:
    """宣言試験の入力。実nonce証明ではない。"""
    return _BindFirstBallDeviceToken(
        _IDS[1], _IDS[2], b"n" * 32, _IDS[3], _IDS[4], b"c" * 32
    )


def _right() -> _CheckFirstBallRightToken:
    """宣言試験の入力。実権利証明ではない。"""
    return _CheckFirstBallRightToken(
        _IDS[1], _IDS[2], b"n" * 32, _IDS[3], _IDS[4], 1, 1, b"p" * 32
    )


@pytest.mark.parametrize("token", [_device(), _right()])
def test_exact_declaration_parameters(token: TenantOperationToken) -> None:
    """宣言内のtenant注入・秘密repr・byte位置を確認する。"""
    spec, args = prepare_function_operation(token, _IDS[0], _REGISTRY)
    assert tuple(args) == ("tenant_id", *(n for n, _ in spec.input_fields))
    assert args["binding_nonce"] == b"n" * 32
    assert "nnnn" not in repr(token)
    assert "cccc" not in repr(token)
    assert "pppp" not in repr(token)


@pytest.mark.parametrize(
    "name,value",
    [
        ("binding_nonce", b"n" * 31),
        ("binding_nonce", b"n" * 33),
        ("credential_digest", b"c" * 31),
        ("credential_digest", bytearray(32)),
    ],
)
def test_device_bytes_closed(name: str, value: object) -> None:
    """bytes以外や32byte以外を補正しない。"""
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(
            replace(_device(), **{name: value}), _IDS[0], _REGISTRY
        )


@pytest.mark.parametrize(
    "name,value",
    [
        ("proof_digest", b"p" * 33),
        ("internal_generation", True),
        ("internal_generation", 0),
        ("recovery_generation", 2**63),
    ],
)
def test_right_bounds(name: str, value: object) -> None:
    """正bigint/証拠digest境界を維持する。"""
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(
            replace(_right(), **{name: value}), _IDS[0], _REGISTRY
        )


@pytest.mark.parametrize(
    "change",
    [
        dict(function_id="other.bind_device"),
        dict(operation_id="SYNC_FIRST_BALL:other"),
        dict(capability_id="CAP:other"),
        dict(min_rows=0),
        dict(nullable_results=("device_matches",)),
    ],
)
def test_exact_signature_only(change: dict[str, object]) -> None:
    """別schema/宣言/一般bytes解禁を拒否する。"""
    with pytest.raises(FunctionOperationError):
        replace(_UNREGISTERED_DECLARATIONS[0], **change)


@pytest.mark.parametrize(
    "rows", [(), ((None,),), ((1,),), ((True, False),), ((True,), (False,))]
)
def test_device_return_shape(rows: tuple) -> None:
    """曖昧な戻り値で成功しない。"""
    with pytest.raises(FunctionOperationError):
        decode_function_result(
            _UNREGISTERED_DECLARATIONS[0], TenantOperationResult(rows)
        )


def test_declared_results() -> None:
    """exact結果形だけを受ける。"""
    for spec, row in zip(
        _UNREGISTERED_DECLARATIONS, [(False,), (False, False)], strict=True
    ):
        result = TenantOperationResult((row,))
        assert decode_function_result(spec, result) == result


def test_unregistered_or_derived_token_rejected() -> None:
    """宣言を作ってもruntime登録や派生token許可にならない。"""
    from dataclasses import dataclass

    @dataclass(frozen=True, slots=True)
    class Derived(_BindFirstBallDeviceToken):
        """親tokenを装う入力。"""

    derived = Derived(_IDS[1], _IDS[2], b"n" * 32, _IDS[3], _IDS[4], b"c" * 32)
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(derived, _IDS[0], _REGISTRY)
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(_device(), _IDS[0], {})


@pytest.mark.parametrize(
    "name,value",
    [
        ("binding_nonce", None),
        ("device_id", str(_IDS[3])),
        ("attempt_id", None),
        ("proof_digest", None),
    ],
)
def test_null_or_wrong_type_rejected(name: str, value: object) -> None:
    """NULLや文字列IDをexact型へ補正しない。"""
    token = _right() if name == "proof_digest" else _device()
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(replace(token, **{name: value}), _IDS[0], _REGISTRY)


@pytest.mark.parametrize("value", [2**31 - 1, 2**31, 2**62, 2**63 - 1])
def test_bigint_generation_abi(value: int) -> None:
    """受理する正bigintを実psycopg SQLでもint4へ狭めない。"""
    from sqlalchemy import BigInteger
    from sqlalchemy.dialects.postgresql import psycopg

    token = replace(_right(), internal_generation=value, recovery_generation=value)
    spec, params = prepare_function_operation(token, _IDS[0], _REGISTRY)
    compiled = spec.statement.compile(dialect=psycopg.dialect())
    sql = str(compiled)
    for name in ("internal_generation", "recovery_generation"):
        assert params[name] == value
        assert f"%({name})s::BIGINT" in sql
        assert f"%({name})s::INTEGER" not in sql
        assert type(compiled.binds[name].type) is BigInteger


@pytest.mark.parametrize("name", ["internal_generation", "recovery_generation"])
@pytest.mark.parametrize("value", [2**63, True, False, -1, 0])
def test_bigint_rejects_before_compilation(name: str, value: object) -> None:
    """型付きSQL実行前に範囲外・boolを拒否する。"""
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(
            replace(_right(), **{name: value}), _IDS[0], _REGISTRY
        )


def test_bigint_exception_not_generalized() -> None:
    """一般int/INITIALのcanonical bindと他位置の型拒否を維持する。"""
    from sqlalchemy import BigInteger, bindparam, select
    from sqlalchemy.dialects.postgresql import psycopg
    from sqlalchemy.sql.functions import Function

    from pitchlog.repositories.function_operations import _canonical_bind

    general = select(_canonical_bind("generation", int)).compile(
        dialect=psycopg.dialect()
    )
    assert "%(generation)s::INTEGER" in str(general)
    spec = _UNREGISTERED_DECLARATIONS[1]
    for wrong_name in ("attempt_id", "binding_nonce", "device_id", "proof_digest"):
        args = [bindparam("tenant_id")]
        args.extend(
            bindparam(name, type_=BigInteger())
            if name == wrong_name
            else _canonical_bind(name, kind)
            for name, kind in spec.input_fields
        )
        table = Function(
            "check_current_right", *args, packagenames=("sync_right_api",)
        ).table_valued("recovery_matches", "right_matches")
        with pytest.raises(FunctionOperationError):
            replace(
                spec, statement=select(table.c.recovery_matches, table.c.right_matches)
            )


@pytest.mark.parametrize(
    "schema,name", [("other", "check_current_right"), ("sync_right_api", "other")]
)
def test_unknown_function_bigint_rejected(schema: str, name: str) -> None:
    """新位置を名乗る未知関数にもBigIntegerを許さない。"""
    from sqlalchemy import BigInteger, bindparam, select
    from sqlalchemy.sql.functions import Function

    table = Function(
        name,
        bindparam("tenant_id"),
        bindparam("internal_generation", type_=BigInteger()),
        packagenames=(schema,),
    ).table_valued("recovery_matches", "right_matches")
    with pytest.raises(FunctionOperationError):
        replace(
            _UNREGISTERED_DECLARATIONS[1],
            function_id=f"{schema}.{name}",
            input_fields=(("internal_generation", int),),
            statement=select(table.c.recovery_matches, table.c.right_matches),
        )


def test_device_state_read_is_standalone_and_product_registered() -> None:
    """新readは旧exact2から独立した正式登録でtenantを必須注入する。"""
    from dataclasses import fields

    from pitchlog.repositories.first_ball import (
        DEVICE_STATE_READ_OPERATION,
        _ReadFirstBallDeviceStateToken,
    )

    assert len(_UNREGISTERED_DECLARATIONS) == 2
    assert DEVICE_STATE_READ_OPERATION not in _UNREGISTERED_DECLARATIONS
    from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY

    assert (
        FUNCTION_OPERATION_REGISTRY[_ReadFirstBallDeviceStateToken]
        is DEVICE_STATE_READ_OPERATION
    )
    registry = build_function_registry((DEVICE_STATE_READ_OPERATION,), frozenset())
    token = _ReadFirstBallDeviceStateToken(_IDS[1])
    assert [item.name for item in fields(token)] == ["device_id"]
    spec, values = prepare_function_operation(token, _IDS[0], registry)
    assert values == {"tenant_id": _IDS[0], "device_id": _IDS[1]}
    for result in (True, False):
        row = TenantOperationResult(((result,),))
        assert decode_function_result(spec, row) == row
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(token, _IDS[0], _REGISTRY)


@pytest.mark.parametrize(
    "rows", ((), ((None,),), ((1,),), ((True,), (True,)), ((True, False),))
)
def test_device_state_read_does_not_coerce_missing_or_numeric_result(rows) -> None:
    """確認不能・異型をdevice falseやsuccessへ補完しない。"""
    from pitchlog.repositories.first_ball import DEVICE_STATE_READ_OPERATION

    with pytest.raises(FunctionOperationError):
        decode_function_result(DEVICE_STATE_READ_OPERATION, TenantOperationResult(rows))
