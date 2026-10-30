"""固定関数だけを同一テナントスコープで実行するための登録型。"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.sql.elements import BindParameter, Label
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.selectable import Select, TableValuedAlias
from sqlalchemy.sql.sqltypes import (
    UUID as SqlUUID,
)
from sqlalchemy.sql.sqltypes import (
    BigInteger,
    Boolean,
    Integer,
    LargeBinary,
    NullType,
    String,
    Uuid,
)
from sqlalchemy.sql.type_api import TypeDecorator

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*\Z")
_PG_DIALECT = postgresql.dialect()
_MAX_IDENTIFIER_BYTES = _PG_DIALECT.max_identifier_length
_IDENTIFIER_PREPARER = _PG_DIALECT.identifier_preparer
_SAFE_BIND_TYPES = frozenset((Boolean, Integer, String, SqlUUID, Uuid))

# 新9関数だけのbytea/nullable/aware結果契約。旧登録の許容型は変更しない。
_INITIAL_RECORD_FIELDS = (
    ("tenant_id", UUID),
    ("game_id", UUID),
    ("start_request_id", UUID),
    ("device_id", UUID),
    ("generation", int),
    ("recovery_generation", int),
    ("proof_digest", bytes),
    ("key_id", str),
    ("nonce", bytes),
    ("ciphertext", bytes),
)
_INITIAL_FUNCTION_TYPES = MappingProxyType(
    {
        "initial_right_api.lock_device": (
            (("device_id", UUID),),
            (("credential_digest", bytes), ("revoked_at", datetime)),
            ("revoked_at",),
            ("revoked_at",),
        ),
        "initial_right_api.read_existing_start": (
            (("game_id", UUID), ("start_request_id", UUID)),
            _INITIAL_RECORD_FIELDS,
            (),
            (),
        ),
        "initial_right_api.read_start_game": (
            (("game_id", UUID),),
            (("status", str),),
            (),
            (),
        ),
        "initial_right_api.lock_preparing_game": (
            (("game_id", UUID),),
            (("locked", bool),),
            (),
            (),
        ),
        "initial_right_api.lock_current_start": (
            (("game_id", UUID), ("start_request_id", UUID)),
            _INITIAL_RECORD_FIELDS,
            (),
            (),
        ),
        "initial_right_api.check_business_epoch": (
            (("recovery_generation", int),),
            (("matches", bool),),
            (),
            (),
        ),
        "initial_right_api.insert_initial_grant": (
            (
                ("game_id", UUID),
                ("start_request_id", UUID),
                ("device_id", UUID),
                ("attempt_id", UUID),
                ("generation", int),
                ("recovery_generation", int),
                ("proof_digest", bytes),
                ("key_id", str),
                ("nonce", bytes),
                ("ciphertext", bytes),
            ),
            (("inserted", bool),),
            (),
            (),
        ),
        "initial_right_api.begin_start_attempt": (
            (
                ("game_id", UUID),
                ("start_request_id", UUID),
                ("device_id", UUID),
                ("request_digest", bytes),
                ("attempt_id", UUID),
            ),
            (("attempt_id", UUID), ("outcome", str)),
            (),
            (),
        ),
        "initial_right_api.resolve_start_attempt": (
            (("game_id", UUID), ("start_request_id", UUID), ("attempt_id", UUID)),
            (("outcome", str), ("generation", int)),
            ("generation",),
            (),
        ),
    }
)

# 旧9署名の反復を変えず、新開始2署名だけを別閉集合へ置く。
_INITIAL_START_FUNCTION_TYPES = MappingProxyType(
    {
        "initial_right_api.read_initial_start_context": (
            (
                ("game_id", UUID),
                ("start_request_id", UUID),
                ("attempt_id", UUID),
                ("request_digest", bytes),
                ("typed_payload_json", str),
            ),
            (("context_json", str),),
            (),
            (),
        ),
        "initial_right_api.persist_initial_start": (
            (
                ("game_id", UUID),
                ("start_request_id", UUID),
                ("attempt_id", UUID),
                ("request_digest", bytes),
                ("typed_payload_json", str),
            ),
            (
                ("started_at", datetime),
                ("away_lineup_id", UUID),
                ("home_lineup_id", UUID),
            ),
            (),
            ("started_at",),
        ),
    }
)


# 旧9/開始2とは別の登録境界。tenantはscopeだけが渡す。
_INITIAL_ENROLL_FUNCTION_TYPES = MappingProxyType(
    {
        "initial_right_api.enroll_device": (
            (("device_id", UUID), ("credential_digest", bytes)),
            (("device_id", UUID),),
            (),
            (),
        ),
    }
)


_INITIAL_RESOLVE_FUNCTION_TYPES = MappingProxyType(
    {
        "initial_right_api.lookup_existing_start_attempt": (
            (
                ("game_id", UUID),
                ("start_request_id", UUID),
                ("device_id", UUID),
                ("request_digest", bytes),
            ),
            (("attempt_id", UUID), ("outcome", str)),
            (),
            (),
        ),
    }
)


def _valid_db_identifier(name: object) -> bool:
    """再構築したSQLでも同じDB識別子になる名前だけを許す。"""
    return (
        type(name) is str
        and _IDENTIFIER.fullmatch(name) is not None
        and len(name.encode("ascii")) <= _MAX_IDENTIFIER_BYTES
        and _IDENTIFIER_PREPARER.quote(name) == name
    )


_SYNC_FIRST_BALL_COMMON = (
    ("attempt_id", UUID),
    ("phase_id", UUID),
    ("binding_nonce", bytes),
    ("device_id", UUID),
    ("game_id", UUID),
)
_SYNC_FIRST_BALL_FUNCTION_TYPES = MappingProxyType(
    {
        "sync_right_api.read_device_state": (
            (("device_id", UUID),),
            (("device_active", bool),),
            (),
            (),
        ),
        "sync_right_api.bind_device": (
            (*_SYNC_FIRST_BALL_COMMON, ("credential_digest", bytes)),
            (("device_matches", bool),),
            (),
            (),
        ),
        "sync_right_api.check_current_right": (
            (
                *_SYNC_FIRST_BALL_COMMON,
                ("internal_generation", int),
                ("recovery_generation", int),
                ("proof_digest", bytes),
            ),
            (("recovery_matches", bool), ("right_matches", bool)),
            (),
            (),
        ),
    }
)


_SYNC_WRITER_BINDING_FUNCTION_TYPES = MappingProxyType(
    {
        "sync_fence_api.read_writer_identity": (
            (),
            (
                ("system_identifier", str),
                ("database_oid", str),
                ("postmaster_started_at", datetime),
                ("backend_pid", int),
                ("backend_start", datetime),
                ("transaction_id", str),
            ),
            (),
            ("postmaster_started_at", "backend_start"),
        ),
        "sync_fence_api.assert_writer_binding": (
            _SYNC_FIRST_BALL_COMMON,
            (("asserted", bool),),
            ("asserted",),
            (),
        ),
    }
)


def _valid_function_schema(name: object) -> bool:
    """接続ごとに指す先が変わる一時schemaとシステムschemaを拒否する。"""
    return (
        _valid_db_identifier(name)
        and isinstance(name, str)
        and not name.startswith("pg_")
        and name != "information_schema"
    )


class FunctionOperationError(RuntimeError):
    """固定関数の登録、入力、結果の契約違反。"""


class _WriterAssertVoidResult(TypeDecorator[None]):
    """固定writer assertの実driver空文字だけを内部NULLへ正規化する。"""

    impl = NullType
    cache_ok = True

    def process_result_value(self, value: object, dialect: Dialect) -> None:
        """PostgreSQL voidのTEXT表現以外は値を漏らさず拒否する。"""
        if type(value) is not str or value != "":
            raise FunctionOperationError("writer assertのdriver応答が不一致")
        return None


@dataclass(frozen=True, slots=True)
class FunctionOperationRegistration:
    """単一のschema修飾関数、exact bind、戻りdecoderを固定する。"""

    operation_id: str
    token_type: type[TenantOperationToken]
    capability_id: str
    function_id: str
    statement: Select[Any]
    input_fields: tuple[tuple[str, type], ...]
    result_fields: tuple[tuple[str, type], ...]
    min_rows: int
    max_rows: int
    decoder: Callable[[TenantOperationResult], TenantOperationResult]
    nonempty_inputs: tuple[str, ...] = ()
    nullable_results: tuple[str, ...] = ()
    aware_datetime_results: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """登録時に任意SQLや曖昧な入出力を拒否する。"""
        if not self.operation_id or not self.capability_id:
            raise FunctionOperationError("固定関数の識別子とcapability IDが必要")
        if (
            not isinstance(self.token_type, type)
            or not issubclass(self.token_type, TenantOperationToken)
            or not is_dataclass(self.token_type)
            or not getattr(
                getattr(self.token_type, "__dataclass_params__", None), "frozen", False
            )
        ):
            raise FunctionOperationError("固定関数tokenはfrozen dataclassが必要")
        if type(self.statement) is not Select or not callable(self.decoder):
            raise FunctionOperationError("固定関数には固定Selectとdecoderが必要")
        input_names = tuple(name for name, _ in self.input_fields)
        result_names = tuple(name for name, _ in self.result_fields)
        if (
            not self.result_fields
            or len(set(input_names)) != len(input_names)
            or len(set(result_names)) != len(result_names)
            or "tenant_id" in input_names
            or any(
                not _valid_db_identifier(name) for name in (*input_names, *result_names)
            )
            or any(
                type(field_type) is not type
                for _, field_type in (*self.input_fields, *self.result_fields)
            )
            or type(self.min_rows) is not int
            or type(self.max_rows) is not int
            or not 0 <= self.min_rows <= self.max_rows
        ):
            raise FunctionOperationError("固定関数の入出力宣言が不正")
        initial = _INITIAL_FUNCTION_TYPES.get(self.function_id)
        if initial is None:
            initial = _INITIAL_START_FUNCTION_TYPES.get(self.function_id)
        if initial is None:
            initial = _INITIAL_ENROLL_FUNCTION_TYPES.get(self.function_id)
        if initial is None:
            initial = _INITIAL_RESOLVE_FUNCTION_TYPES.get(self.function_id)
        first_ball = _SYNC_FIRST_BALL_FUNCTION_TYPES.get(self.function_id)
        writer_binding = _SYNC_WRITER_BINDING_FUNCTION_TYPES.get(self.function_id)
        extended = (
            self.input_fields,
            self.result_fields,
            self.nullable_results,
            self.aware_datetime_results,
        )
        if initial is not None:
            name = self.function_id.rsplit(".", 1)[1]
            if (
                extended != initial
                or self.operation_id != f"INITIAL_RIGHT:{name}"
                or self.capability_id != f"CAP:initial_right:{name}"
            ):
                raise FunctionOperationError("初期権関数の有限型宣言が不一致")
        elif first_ball is not None:
            name = self.function_id.rsplit(".", 1)[1]
            if (
                extended != first_ball
                or self.operation_id != f"SYNC_FIRST_BALL:{name}"
                or self.capability_id != f"CAP:sync_first_ball:{name}"
                or self.min_rows != 1
                or self.max_rows != 1
                or self.nonempty_inputs
            ):
                raise FunctionOperationError("初球関数の有限型宣言が不一致")
        elif writer_binding is not None:
            name = self.function_id.rsplit(".", 1)[1]
            if (
                extended != writer_binding
                or self.operation_id != f"SYNC_WRITER_BINDING:{name}"
                or self.capability_id != f"CAP:sync_writer_binding:{name}"
                or self.min_rows != 1
                or self.max_rows != 1
                or self.nonempty_inputs
            ):
                raise FunctionOperationError("writer binding関数の有限型宣言が不一致")
        elif (
            self.nullable_results
            or self.aware_datetime_results
            or any(field_type is bytes for _, field_type in self.input_fields)
        ):
            raise FunctionOperationError("拡張型宣言は初期権の固定9関数だけに限る")
        token_fields = {field.name for field in fields(self.token_type)}
        if (
            type(self.nonempty_inputs) is not tuple
            or any(type(name) is not str for name in self.nonempty_inputs)
            or len(set(self.nonempty_inputs)) != len(self.nonempty_inputs)
            or any(
                dict(self.input_fields).get(name) is not str
                for name in self.nonempty_inputs
            )
        ):
            raise FunctionOperationError("固定関数の非空入力宣言が不正")
        if not set(input_names) <= token_fields:
            raise FunctionOperationError("固定関数入力がtokenに存在しない")
        parts = self.function_id.split(".")
        if (
            len(parts) != 2
            or not _valid_function_schema(parts[0])
            or not _valid_db_identifier(parts[1])
        ):
            raise FunctionOperationError("DB関数identityにはschema修飾が必要")
        compiler = postgresql.dialect().statement_compiler
        if getattr(compiler, f"visit_{parts[1]}_func", None) is not None:
            raise FunctionOperationError(
                "DB関数identityにSQLAlchemy特殊関数名を許可しない"
            )

        selected = tuple(self.statement.selected_columns)
        froms = self.statement.get_final_froms()
        function: Function[Any]
        if len(froms) == 0 and len(selected) == 1 and type(selected[0]) is Label:
            label = selected[0]
            if (
                len(result_names) != 1
                or label.name != result_names[0]
                or type(label.element) is not Function
            ):
                raise FunctionOperationError("関数戻り列が宣言と不一致")
            function = label.element
        elif len(froms) == 1 and type(froms[0]) is TableValuedAlias:
            table = froms[0]
            if (
                tuple(column.name for column in selected) != result_names
                or any(column.table is not table for column in selected)
                or type(table.element) is not Function
            ):
                raise FunctionOperationError("関数戻り列が宣言と不一致")
            function = table.element
        else:
            raise FunctionOperationError("単一の固定関数呼出しだけを許可する")
        if (
            self.statement.whereclause is not None
            or self.statement._limit_clause is not None
            or self.statement._offset_clause is not None
            or self.statement._order_by_clauses
            or self.statement._group_by_clauses
            or self.statement._having_criteria
            or self.statement._distinct
            or self.statement._prefixes
            or self.statement._suffixes
            or self.statement._hints
            or self.statement._statement_hints
            or self.statement._independent_ctes
            or self.statement._for_update_arg is not None
            or self.statement._fetch_clause is not None
            or (function.packagenames, function.name) != ((parts[0],), parts[1])
        ):
            raise FunctionOperationError("固定関数文に追加SQLまたはidentity不一致")
        arguments = tuple(function.clauses)
        if (
            len(arguments) != len(input_names) + 1
            or any(type(arg) is not BindParameter for arg in arguments)
            or tuple(arg.key for arg in arguments) != ("tenant_id", *input_names)
            or any(arg.literal_execute or arg.expanding for arg in arguments)
        ):
            raise FunctionOperationError("固定関数のbind集合・順序が不一致")
        for argument, expected_type in zip(
            arguments,
            (UUID, *(field_type for _, field_type in self.input_fields)),
            strict=True,
        ):
            if argument.type._variant_mapping:
                raise FunctionOperationError(
                    "固定関数bindにdialect別のSQL型を許可しない"
                )
            if type(argument.type) is NullType:
                continue
            if (
                type(argument.type) not in _SAFE_BIND_TYPES
                and not (
                    (
                        initial is not None
                        or first_ball is not None
                        or writer_binding is not None
                    )
                    and expected_type is bytes
                    and type(argument.type) is LargeBinary
                )
                and not (
                    first_ball is not None
                    and self.function_id == "sync_right_api.check_current_right"
                    and argument.key in ("internal_generation", "recovery_generation")
                    and expected_type is int
                    and type(argument.type) is BigInteger
                )
            ):
                raise FunctionOperationError("固定関数bindに未許可のSQL型")
            try:
                bound_type = argument.type.python_type
            except NotImplementedError as error:
                raise FunctionOperationError(
                    "固定関数bindの型を判定できない"
                ) from error
            if bound_type is not expected_type:
                raise FunctionOperationError("固定関数bindの型が入力宣言と不一致")

        object.__setattr__(
            self,
            "statement",
            _build_fixed_function_statement(
                parts[0], parts[1], self.input_fields, result_names, bool(froms)
            ),
        )


def _build_fixed_function_statement(
    schema: str,
    function_name: str,
    input_fields: tuple[tuple[str, type], ...],
    result_names: tuple[str, ...],
    table_valued: bool,
) -> Select[Any]:
    """検証済み宣言から固定関数のSelectだけを組み立てる。"""
    safe_arguments = (
        _canonical_bind("tenant_id", UUID),
        *(
            bindparam(name, type_=BigInteger())
            if (
                schema == "sync_right_api"
                and function_name == "check_current_right"
                and name in ("internal_generation", "recovery_generation")
                and field_type is int
            )
            else _canonical_bind(name, field_type)
            for name, field_type in input_fields
        ),
    )
    safe_function = Function(function_name, *safe_arguments, packagenames=(schema,))
    if (
        schema == "sync_fence_api"
        and function_name == "assert_writer_binding"
        and not table_valued
        and result_names == ("asserted",)
    ):
        safe_function.type = _WriterAssertVoidResult()
    if not table_valued:
        return select(safe_function.label(result_names[0]))
    safe_table = safe_function.table_valued(*result_names)
    return select(*(safe_table.c[name] for name in result_names))


def _canonical_bind(name: str, expected_type: type) -> BindParameter[Any]:
    """検証済み入力から組み込み型の新規bindだけを作る。"""
    if expected_type is UUID:
        return bindparam(name, type_=Uuid())
    if expected_type is str:
        return bindparam(name, type_=String())
    if expected_type is int:
        return bindparam(name, type_=Integer())
    if expected_type is bool:
        return bindparam(name, type_=Boolean())
    if expected_type is bytes:
        return bindparam(name, type_=LargeBinary())
    raise FunctionOperationError("固定関数入力に未対応の型")


def build_function_registry(
    registrations: tuple[FunctionOperationRegistration, ...],
    dml_token_types: frozenset[type[TenantOperationToken]],
    dml_capability_ids: frozenset[str] = frozenset(),
) -> Mapping[type[TenantOperationToken], FunctionOperationRegistration]:
    """DMLと重複しない不変の固定関数registryを作る。"""
    registry: dict[type[TenantOperationToken], FunctionOperationRegistration] = {}
    operation_ids: set[str] = set()
    for registration in registrations:
        if (
            registration.token_type in dml_token_types
            or registration.token_type in registry
            or registration.operation_id in operation_ids
            or registration.operation_id in dml_capability_ids
            or registration.capability_id in dml_capability_ids
        ):
            raise FunctionOperationError("固定関数と既存DMLのIDまたはtoken型が重複")
        registry[registration.token_type] = registration
        operation_ids.add(registration.operation_id)
    return MappingProxyType(registry)


def prepare_function_operation(
    operation: TenantOperationToken,
    tenant_id: object,
    registry: Mapping[type[TenantOperationToken], FunctionOperationRegistration],
) -> tuple[FunctionOperationRegistration, dict[str, object]]:
    """Exact token型・capability・入力型を実行直前に検証する。"""
    spec = registry.get(type(operation))
    if spec is None:
        raise FunctionOperationError("未登録または偽造された固定関数token")
    if operation.capability_id != spec.capability_id:
        raise FunctionOperationError("固定関数tokenのcapability IDが不一致")
    parameters: dict[str, object] = {"tenant_id": tenant_id}
    for name, expected_type in spec.input_fields:
        value = getattr(operation, name)
        if type(value) is not expected_type:
            raise FunctionOperationError(f"固定関数入力{name}の型が不一致")
        if (
            spec.function_id in _INITIAL_FUNCTION_TYPES
            or spec.function_id in _INITIAL_START_FUNCTION_TYPES
            or spec.function_id in _INITIAL_ENROLL_FUNCTION_TYPES
            or spec.function_id in _INITIAL_RESOLVE_FUNCTION_TYPES
        ):
            byte_lengths = {
                "request_digest": 32,
                "credential_digest": 32,
                "proof_digest": 32,
                "nonce": 12,
                "ciphertext": 48,
            }
            if expected_type is bytes and len(value) != byte_lengths[name]:
                raise FunctionOperationError("初期権の固定byte長が不一致")
            if expected_type is int and not 0 < value < 2**63:
                raise FunctionOperationError("初期権の整数は正bigintが必要")
            if expected_type is str and not value:
                raise FunctionOperationError("初期権の文字列を空にできない")
        if (
            spec.function_id in _SYNC_FIRST_BALL_FUNCTION_TYPES
            or spec.function_id in _SYNC_WRITER_BINDING_FUNCTION_TYPES
        ):
            if expected_type is bytes and len(value) != 32:
                raise FunctionOperationError("初球の固定byte長が不一致")
            if expected_type is int and not 0 < value < 2**63:
                raise FunctionOperationError("初球の整数は正bigintが必要")
        if name in spec.nonempty_inputs and value == "":
            raise FunctionOperationError(f"固定関数入力{name}は空文字を許可しない")
        parameters[name] = value
    return spec, parameters


def decode_function_result(
    spec: FunctionOperationRegistration,
    result: TenantOperationResult,
) -> TenantOperationResult:
    """固定decoderの前後で行数・列数・exact型を検査する。"""
    _validate_result_shape(spec, result)
    decoded = spec.decoder(result)
    if type(decoded) is not TenantOperationResult:
        raise FunctionOperationError("固定関数decoderの戻り型が不一致")
    _validate_result_shape(spec, decoded)
    return decoded


def _validate_result_shape(
    spec: FunctionOperationRegistration,
    result: TenantOperationResult,
) -> None:
    """登録済みの行数・列・exact型から外れた結果を拒否する。"""
    if not spec.min_rows <= len(result.rows) <= spec.max_rows:
        raise FunctionOperationError("固定関数の戻り行数が不一致")
    for row in result.rows:
        if len(row) != len(spec.result_fields):
            raise FunctionOperationError("固定関数の戻り列または型が不一致")
        for value, (name, expected_type) in zip(row, spec.result_fields, strict=True):
            if value is None and name in spec.nullable_results:
                continue
            if type(value) is not expected_type:
                raise FunctionOperationError("固定関数の戻り列または型が不一致")
            if name in spec.aware_datetime_results and (
                not isinstance(value, datetime) or value.utcoffset() is None
            ):
                raise FunctionOperationError("固定関数の日時にはtimezoneが必要")
