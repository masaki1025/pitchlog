"""成績5関数の有限登録。値型だけに実行能力を与えない。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import BindParameter
from sqlalchemy.sql.selectable import Select

from pitchlog.repositories import stats_function_codec as codec
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    FunctionOperationRegistration,
)
from pitchlog.repositories.play_export_primitives import (
    OpenPrimitiveSnapshotToken,
    ReadPrimitivePageToken,
)
from pitchlog.repositories.stats import ReadPrimitiveTotalsToken
from pitchlog.repositories.tokens import TenantOperationToken


@dataclass(frozen=True, slots=True, init=False)
class _SavePrimitiveSourceCall(TenantOperationToken):
    """flush私有SQLsiteを記述するだけの型。自由な値の発行口を持たない。"""

    attempt_id: UUID
    phase_id: UUID
    source_event_id: UUID
    model_sha256: str
    expected_revision: int
    expected_source_set_sha256: str | None
    evaluation_json: str
    binding_nonce: bytes

    def __new__(cls, *args, **kwargs):
        """本型自体も保存資格として発行しない。"""
        raise FunctionOperationError("成績writerのmetadata型は生成できません")

    @property
    def capability_id(self):
        """同じ私有保存能力を宣言する。"""
        return "CAP:stats_primitives:save_source"


@dataclass(frozen=True, slots=True, init=False)
class _ReadPrimitiveWriterStateCall(TenantOperationToken):
    """同TX前値の固定siteを記述し、UUID/nonceから資格を発行しない。"""

    attempt_id: UUID
    phase_id: UUID
    source_event_id: UUID
    model_sha256: str
    binding_nonce: bytes

    def __new__(cls, *args, **kwargs):
        """通常構築を拒否する。"""
        raise FunctionOperationError("成績writerのmetadata型は生成できません")

    @property
    def capability_id(self):
        """新しい公開能力は増やさない。"""
        return "CAP:stats_primitives:save_source"


_FAMILIES = {
    "save_primitive_source": (
        _SavePrimitiveSourceCall,
        "save_source",
        "save_source",
        1,
        1,
        (),
    ),
    "read_primitive_writer_state": (
        _ReadPrimitiveWriterStateCall,
        "read_writer_state",
        "save_source",
        1,
        1,
        ("source_set_sha256",),
    ),
    "open_primitive_snapshot": (
        OpenPrimitiveSnapshotToken,
        "open_snapshot",
        "read",
        1,
        1,
        (),
    ),
    "read_play_export_primitives": (
        ReadPrimitivePageToken,
        "read_page",
        "read",
        0,
        500,
        ("value",),
    ),
    "read_primitive_totals": (
        ReadPrimitiveTotalsToken,
        "read_totals",
        "read",
        26,
        26,
        ("value",),
    ),
}


def _private_decoder(result):
    """公開generic decodeから私有資格を復元しない。実callerは固定codecを使う。"""
    raise FunctionOperationError("成績のdecoderは私有資格dispatcherだけで利用できます")


def _shape(name):
    """同codecの型付きSelect/引数順/行型をmetadataへ写し、数学は持たない。"""
    if set(codec._SPECS) != set(_FAMILIES) or name not in _FAMILIES:
        raise FunctionOperationError("成績の固定5identityが不一致")
    token, operation, capability, minimum, maximum, nullable = _FAMILIES[name]
    inputs, outputs = codec._SPECS[name]
    call = codec._call(name, (None,) * len(inputs))
    return {
        "operation_id": "STATS_PRIMITIVES:" + operation,
        "token_type": token,
        "capability_id": "CAP:stats_primitives:" + capability,
        "function_id": "stats_api." + name,
        "statement": call.statement,
        "input_fields": tuple(
            (key, str if key == "evaluation_json" else sql_type.python_type)
            for key, sql_type in inputs
        ),
        "result_fields": tuple(
            (key, sql_type.python_type) for key, sql_type in outputs
        ),
        "min_rows": minimum,
        "max_rows": maximum,
        "decoder": _private_decoder,
        "nonempty_inputs": (),
        "nullable_results": nullable,
        "aware_datetime_results": (),
    }


def _same_metadata(left, right):
    """bool/intや派生文字列の同値性を固定宣言へ持ち込まない。"""
    if type(left) is not type(right):
        return False
    if type(left) is tuple:
        return len(left) == len(right) and all(
            _same_metadata(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _same_statement(actual, expected):
    """元codecとの全構造とSQL型/compileを比べ、未知SQLや型を受けない。"""
    if type(actual) is not Select or not actual.compare(expected):
        return False
    dialect = postgresql.dialect()
    if str(actual.compile(dialect=dialect)) != str(expected.compile(dialect=dialect)):
        return False
    left = [
        node for node in visitors.iterate(actual) if isinstance(node, BindParameter)
    ]
    right = [
        node for node in visitors.iterate(expected) if isinstance(node, BindParameter)
    ]
    return len(left) == len(right) and all(
        type(a) is BindParameter
        and a.key == b.key
        and a.value is None
        and a.literal_execute is False
        and a.expanding is False
        and type(a.type) is type(b.type)
        and a.type._static_cache_key == b.type._static_cache_key
        and a.type._variant_mapping == b.type._variant_mapping
        for a, b in zip(left, right, strict=True)
    )


def validate_registration(registration) -> None:
    """新5の正確な型/能力/引数/SQLだけを閉じて登録する。"""
    if type(registration) is not FunctionOperationRegistration:
        raise FunctionOperationError("成績の登録実型が不一致")
    name = (
        registration.function_id.removeprefix("stats_api.")
        if type(registration.function_id) is str
        else ""
    )
    if name not in _FAMILIES:
        raise FunctionOperationError("成績の固定function-idが不一致")
    expected = _shape(name)
    for key, value in expected.items():
        if key == "statement":
            if not _same_statement(registration.statement, value):
                raise FunctionOperationError("成績の固定SQL/型が不一致")
        elif not _same_metadata(getattr(registration, key), value):
            raise FunctionOperationError("成績の登録全fieldが不一致")
    # 旧validatorと同様、呼出者のSelectを実行せず単一codecから安全に再構築する。
    object.__setattr__(registration, "statement", expected["statement"])


STATS_NATIVE_FUNCTION_OPERATIONS = tuple(
    FunctionOperationRegistration(**_shape(name)) for name in _FAMILIES
)


def _registered(token_type, registry):
    """同じcanonical registration object以外で登録値を置換しない。"""
    expected = next(
        (r for r in STATS_NATIVE_FUNCTION_OPERATIONS if r.token_type is token_type),
        None,
    )
    if expected is None or registry.get(token_type) is not expected:
        raise FunctionOperationError("成績の実registrationが未供給又は置換されました")
    validate_registration(expected)
    return expected


def require_read_registration(operation, registry):
    """metadata照合のみ。RRRO/一回receiptの確認は既dispatcherが別途必須。"""
    if type(operation) not in (
        OpenPrimitiveSnapshotToken,
        ReadPrimitivePageToken,
        ReadPrimitiveTotalsToken,
    ):
        raise FunctionOperationError("成績readの実token型が不一致")
    return _registered(type(operation), registry)


def require_registered_call(registration, call, registry) -> None:
    """実codec呼出しと登録SQLを結ぶだけで、新しい資格は発行しない。"""
    actual = _registered(registration.token_type, registry)
    if actual is not registration or type(call) is not codec.StatsFunctionCall:
        raise FunctionOperationError("成績callの登録実型が不一致")
    if call.function_id != registration.function_id or not _same_statement(
        call.statement, registration.statement
    ):
        raise FunctionOperationError("成績callと登録SQLが不一致")
    if tuple(call.parameters) != tuple(key for key, _ in registration.input_fields):
        raise FunctionOperationError("成績callの全引数が不一致")


def require_private_writer_call(operation_id, call, registry):
    """rootがflushの2siteで使う有限追跡口。source資格の代用にはしない。"""
    expected = next(
        (
            r
            for r in STATS_NATIVE_FUNCTION_OPERATIONS
            if r.operation_id == operation_id
            and r.token_type
            in (_SavePrimitiveSourceCall, _ReadPrimitiveWriterStateCall)
        ),
        None,
    )
    if expected is None:
        raise FunctionOperationError("成績writerの固定siteが不一致")
    require_registered_call(expected, call, registry)
    return expected


def contract_candidates() -> list[dict[str, Any]]:
    """rootの正式deriveへ同じ5operation/token/typed SQLの値を供給する。"""
    return [
        {
            "operation_id": r.operation_id,
            "capability_id": r.capability_id,
            "function_id": r.function_id,
            "token_type": r.token_type.__module__ + "." + r.token_type.__qualname__,
            "input_fields": [
                {"name": n, "python_type": t.__module__ + "." + t.__qualname__}
                for n, t in r.input_fields
            ],
            "result_fields": [
                {"name": n, "python_type": t.__module__ + "." + t.__qualname__}
                for n, t in r.result_fields
            ],
            "min_rows": r.min_rows,
            "max_rows": r.max_rows,
            "nullable_results": list(r.nullable_results),
            "private_only": True,
        }
        for r in STATS_NATIVE_FUNCTION_OPERATIONS
    ]
