"""取消固定6関数の閉metadataと真正私有dispatcher。認可資格は別に要求する。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import islice
from types import MappingProxyType
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, LargeBinary, Text, Uuid, bindparam, column
from sqlalchemy import select as sql_select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import BindParameter
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.selectable import Select

from pitchlog.authz.nonplay_prefix_sql import candidate_function_bodies
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    FunctionOperationRegistration,
)
from pitchlog.repositories.nonplay_qualification import (
    BindNonplayDeviceToken,
    CheckNonplayRightToken,
    _assert_nonplay_right_live,
    _qualified_nonplay_right_call,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken


@dataclass(frozen=True, slots=True, init=False)
class _PrivateNonplayCall(TenantOperationToken):
    """固定SQLsiteのmetadata。実reader tokenや保存資格を発行しない。"""

    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes = field(repr=False)
    device_id: UUID
    game_id: UUID
    request_json: str = field(repr=False)

    def __new__(cls, *args, **kwargs):
        """自由なnonce/JSONからmetadata型を生成しない。"""
        raise FunctionOperationError("取消私有SQLsiteのmetadataは生成できません")


@dataclass(frozen=True, slots=True, init=False)
class _LockNonplayCheckpointCall(_PrivateNonplayCall):
    """固定point読取site。"""

    @property
    def capability_id(self):
        """実readerと同じ限定能力を表す。"""
        return "CAP:sync_nonplay:lock_checkpoint"


@dataclass(frozen=True, slots=True, init=False)
class _ReadNonplayHistoryPageCall(_PrivateNonplayCall):
    """有限page読取site。"""

    @property
    def capability_id(self):
        """実readerと同じ限定能力を表す。"""
        return "CAP:sync_nonplay:read_history_page"


@dataclass(frozen=True, slots=True, init=False)
class _PrepareNonplayUndoCall(_PrivateNonplayCall):
    """一回prepare site。"""

    @property
    def capability_id(self):
        """実bridgeと同じ限定能力を表す。"""
        return "CAP:sync_nonplay:prepare_undo"


@dataclass(frozen=True, slots=True, init=False)
class _ConsumeNonplayUndoCall(_PrivateNonplayCall):
    """一回consume site。"""

    @property
    def capability_id(self):
        """実bridgeと同じ限定能力を表す。"""
        return "CAP:sync_nonplay:consume_undo"


_COMMON = (
    ("attempt_id", UUID),
    ("phase_id", UUID),
    ("binding_nonce", bytes),
    ("device_id", UUID),
    ("game_id", UUID),
)
_FAMILIES = MappingProxyType(
    {
        "bind_nonplay_device": (
            BindNonplayDeviceToken,
            "bind_device",
            (*_COMMON, ("credential_digest", bytes)),
            (("device_matches", bool),),
            1,
            1,
        ),
        "check_nonplay_right": (
            CheckNonplayRightToken,
            "check_right",
            (
                *_COMMON,
                ("internal_generation", int),
                ("recovery_generation", int),
                ("proof_digest", bytes),
            ),
            (("recovery_matches", bool), ("right_matches", bool)),
            1,
            1,
        ),
        "lock_nonplay_checkpoint": (
            _LockNonplayCheckpointCall,
            "lock_checkpoint",
            (*_COMMON, ("request_json", str)),
            (("record_json", str),),
            1,
            1,
        ),
        "read_nonplay_history_page": (
            _ReadNonplayHistoryPageCall,
            "read_history_page",
            (*_COMMON, ("request_json", str)),
            (("record_json", str),),
            0,
            100,
        ),
        "prepare_nonplay_undo": (
            _PrepareNonplayUndoCall,
            "prepare_undo",
            (*_COMMON, ("request_json", str)),
            (("prepared", bool),),
            1,
            1,
        ),
        "consume_nonplay_undo": (
            _ConsumeNonplayUndoCall,
            "consume_undo",
            (*_COMMON, ("request_json", str)),
            (("consumed", bool),),
            1,
            1,
        ),
    }
)
_TYPES = {UUID: Uuid, bytes: LargeBinary, int: BigInteger, str: Text, bool: Boolean}
_SQL_NAMES = {UUID: "uuid", bytes: "bytea", int: "bigint", str: "text", bool: "boolean"}


def _statement(name, inputs, outputs):
    """閉型の単一schema修飾関数だけを構築する。"""
    args = tuple(
        bindparam(k, type_=_TYPES[t]()) for k, t in (("tenant_id", UUID), *inputs)
    )
    fn = Function(name, *args, packagenames=("sync_right_api",))
    table = fn.table_valued(*(column(k, _TYPES[t]()) for k, t in outputs))
    return sql_select(*(table.c[k] for k, _ in outputs))


def _verify_renderer():
    """実body rendererの全6 ABIと引数順/型/戻り列を照合する。"""
    bodies = candidate_function_bodies()
    if set(bodies) != set(_FAMILIES):
        raise FunctionOperationError("取消固定6関数のrenderer集合が不一致です")
    for name, (_token, _cap, inputs, outputs, _min, _max) in _FAMILIES.items():
        match = re.search(
            r"CREATE(?: OR REPLACE)? FUNCTION sync_right_api\.([a-z_]+)"
            r"\((.*?)\)\s*RETURNS TABLE\s*\((.*?)\)",
            bodies[name],
            re.S,
        )
        expected = ",".join(
            "p_" + k + " " + _SQL_NAMES[t] for k, t in (("tenant_id", UUID), *inputs)
        )
        result = ",".join(k + " " + _SQL_NAMES[t] for k, t in outputs)

        def compact(text):
            """SQL引数の字句間空白だけを除いてABIを比べる。"""
            return re.sub(r"\s+", "", text)

        if (
            match is None
            or match[1] != name
            or compact(match[2]) != compact(expected)
            or compact(match[3]) != compact(result)
        ):
            raise FunctionOperationError("取消固定関数のrenderer ABIが不一致です")


def _private_decoder(_result):
    """Generic decodeを資格付き私有経路へ昇格させない。"""
    raise FunctionOperationError("取消decoderは私有dispatcherだけで使用できます")


def _shape(name):
    """閉6identityだけを同じ一か所から宣言する。"""
    token, cap, inputs, outputs, minimum, maximum = _FAMILIES[name]
    return dict(
        operation_id="SYNC_NONPLAY:" + name,
        token_type=token,
        capability_id="CAP:sync_nonplay:" + cap,
        function_id="sync_right_api." + name,
        statement=_statement(name, inputs, outputs),
        input_fields=inputs,
        result_fields=outputs,
        min_rows=minimum,
        max_rows=maximum,
        decoder=_private_decoder,
        nonempty_inputs=("request_json",) if ("request_json", str) in inputs else (),
        nullable_results=(),
        aware_datetime_results=(),
    )


def _same_statement(left, right):
    """追加SQL/未知bind/型variantを受けず正準文を比較する。"""
    if type(left) is not Select or not left.compare(right):
        return False
    dialect = postgresql.dialect()
    if str(left.compile(dialect=dialect)) != str(right.compile(dialect=dialect)):
        return False
    if len(left.selected_columns) != len(right.selected_columns) or any(
        type(a.type) is not type(b.type)
        or a.type._static_cache_key != b.type._static_cache_key
        or a.type._variant_mapping
        for a, b in zip(left.selected_columns, right.selected_columns, strict=True)
    ):
        return False
    a = [n for n in visitors.iterate(left) if isinstance(n, BindParameter)]
    b = [n for n in visitors.iterate(right) if isinstance(n, BindParameter)]
    return len(a) == len(b) and all(
        type(x) is BindParameter
        and x.key == y.key
        and x.value is None
        and x.literal_execute is False
        and x.expanding is False
        and type(x.type) is type(y.type)
        and x.type._static_cache_key == y.type._static_cache_key
        and not x.type._variant_mapping
        for x, y in zip(a, b, strict=True)
    )


def _same_metadata(left, right):
    """入れ子の型も完全一致させbool/intや派生文字列を混同しない。"""
    if type(left) is not type(right):
        return False
    if type(left) is tuple:
        return len(left) == len(right) and all(
            _same_metadata(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def validate_registration(registration):
    """予約namespaceを正確な全fieldと単一renderer ABIへ閉じる。"""
    if type(registration) is not FunctionOperationRegistration:
        raise FunctionOperationError("取消登録の実型が不一致です")
    name = (
        registration.function_id.removeprefix("sync_right_api.")
        if type(registration.function_id) is str
        else ""
    )
    if name not in _FAMILIES:
        raise FunctionOperationError("取消の固定function IDが不一致です")
    _verify_renderer()
    expected = _shape(name)
    for key, value in expected.items():
        actual = getattr(registration, key)
        if key == "statement":
            if not _same_statement(actual, value):
                raise FunctionOperationError("取消登録の固定SQL/型が不一致です")
        elif not _same_metadata(actual, value):
            raise FunctionOperationError("取消登録の全fieldが不一致です")
    object.__setattr__(registration, "statement", expected["statement"])


NONPLAY_FUNCTION_OPERATIONS = tuple(
    FunctionOperationRegistration(**_shape(name)) for name in _FAMILIES
)
NONPLAY_TOKEN_TYPES = frozenset(x.token_type for x in NONPLAY_FUNCTION_OPERATIONS)


def _actual_families():
    """循環importを避け、実呼出時にSource17 exact4型だけを解決する。"""
    from pitchlog.repositories.nonplay_prefix import (
        _ConsumeNonplayUndo,
        _LockNonplayCheckpoint,
        _PrepareNonplayUndo,
        _ReadNonplayHistoryPage,
    )

    return {
        BindNonplayDeviceToken: "bind_nonplay_device",
        CheckNonplayRightToken: "check_nonplay_right",
        _LockNonplayCheckpoint: "lock_nonplay_checkpoint",
        _ReadNonplayHistoryPage: "read_nonplay_history_page",
        _PrepareNonplayUndo: "prepare_nonplay_undo",
        _ConsumeNonplayUndo: "consume_nonplay_undo",
    }


def is_nonplay_operation(operation):
    """未知型/metadata型/派生型を実Source17命令へ昇格させない。"""
    return type(operation) in _actual_families()


def _registered(operation, registry) -> FunctionOperationRegistration:
    """実Source17型をcanonical metadataへ閉写像し同objectだけを使う。"""
    name = _actual_families().get(type(operation))
    actual = next(
        (
            x
            for x in NONPLAY_FUNCTION_OPERATIONS
            if x.function_id == "sync_right_api." + str(name)
        ),
        None,
    )
    if (
        actual is None
        or registry.get(actual.token_type) is not actual
        or type(operation.capability_id) is not str
        or operation.capability_id != actual.capability_id
    ):
        raise FunctionOperationError("取消実registrationが未登録又は置換されました")
    validate_registration(actual)
    return actual


def _decode(spec, rows):
    """全列exact型/有限行数を検査し、prepare/consumeはTrue1行だけを許す。"""
    if type(rows) is not tuple or not spec.min_rows <= len(rows) <= spec.max_rows:
        raise FunctionOperationError("取消固定関数の行数が不一致です")
    for row in rows:
        if (
            type(row) is not tuple
            or len(row) != len(spec.result_fields)
            or any(type(v) is not t for v, (_k, t) in zip(row, spec.result_fields))
        ):
            raise FunctionOperationError("取消固定関数の戻り全型が不一致です")
    if spec.token_type in {
        _PrepareNonplayUndoCall,
        _ConsumeNonplayUndoCall,
    } and rows != ((True,),):
        raise FunctionOperationError("取消writeの実True応答がありません")
    return TenantOperationResult(rows)


def execute_nonplay_function(handle, operation, registry):
    """実同Sessionで一回資格を消費し、固定Select/decoderだけを実行する。"""
    from pitchlog.repositories import transaction
    from pitchlog.repositories.nonplay_prefix import (
        QualifiedNonplayCall,
        _qualified_nonplay_call,
    )

    spec = _registered(operation, registry)
    runtime = transaction._TRANSACTION_RUNTIMES.get(handle._state_key)
    if runtime is None:
        raise FunctionOperationError("取消関数の実runtimeが失効しています")
    rights = type(operation) in {BindNonplayDeviceToken, CheckNonplayRightToken}
    if rights:
        params = _qualified_nonplay_right_call(handle, operation)
    else:
        qualified = _qualified_nonplay_call(handle, operation)
        if (
            type(qualified) is not QualifiedNonplayCall
            or qualified.operation is not operation
            or type(qualified.function_name) is not str
            or qualified.function_name
            != spec.function_id.removeprefix("sync_right_api.")
        ):
            raise FunctionOperationError("取消私有callの実参照が不一致です")
        params = qualified.parameters
    lifetime = handle._writer_lifetime()
    expected = (("tenant_id", UUID), *spec.input_fields)
    if type(params) is not MappingProxyType or tuple(params) != tuple(
        k for k, _ in expected
    ):
        raise FunctionOperationError("取消固定関数の全bind集合が不一致です")
    parameters: dict[str, object] = {}
    for key, typ in expected:
        value = params[key]
        if type(value) is not typ:
            raise FunctionOperationError("取消固定関数のbind実型が不一致です")
        if typ is bytes and len(value) != 32:
            raise FunctionOperationError("取消固定関数の固定byte長が不一致です")
        if typ is int and not 0 < value < 2**63:
            raise FunctionOperationError("取消固定関数の正bigintが不一致です")
        if typ is str and not value:
            raise FunctionOperationError("取消固定関数の空JSONを許可しません")
        parameters[key] = value
    session, _ = runtime
    maximum_rows = spec.max_rows
    rows = tuple(
        tuple(row)
        for row in islice(session.execute(spec.statement, parameters), maximum_rows + 1)
    )
    if transaction._TRANSACTION_RUNTIMES.get(handle._state_key) is not runtime:
        raise FunctionOperationError("取消関数の実runtimeが変更されました")
    observed = handle._writer_lifetime()
    if observed[0] is not lifetime[0] or observed[1] is not lifetime[1]:
        raise FunctionOperationError("取消関数の実topTXが変更されました")
    if rights:
        _assert_nonplay_right_live(handle, operation)
    _registered(operation, registry)
    return _decode(spec, rows)


def contract_candidates():
    """rootの正式登録へ同じ閉6 ABIだけを供給する。"""
    return [
        {
            "operation_id": x.operation_id,
            "capability_id": x.capability_id,
            "function_id": x.function_id,
            "token_type": x.token_type.__module__ + "." + x.token_type.__qualname__,
            "input_fields": [
                (n, t.__module__ + "." + t.__qualname__) for n, t in x.input_fields
            ],
            "result_fields": [
                (n, t.__module__ + "." + t.__qualname__) for n, t in x.result_fields
            ],
            "min_rows": x.min_rows,
            "max_rows": x.max_rows,
            "private_only": True,
            "metadata_only_token": x.token_type
            not in {BindNonplayDeviceToken, CheckNonplayRightToken},
            "actual_operation_token": next(
                t.__module__ + "." + t.__qualname__
                for t, n in _actual_families().items()
                if "sync_right_api." + n == x.function_id
            ),
        }
        for x in NONPLAY_FUNCTION_OPERATIONS
    ]
