"""同期writerの自己identityと固定assertの閉tokenを定義する。"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from pitchlog.repositories.function_operations import (
    _SYNC_WRITER_BINDING_FUNCTION_TYPES,
    FunctionOperationError,
    FunctionOperationRegistration,
    _build_fixed_function_statement,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken


@dataclass(frozen=True, slots=True)
class _ReadWriterIdentityToken(TenantOperationToken):
    """現在scopeの実PG identityだけを照会する。"""

    @property
    def capability_id(self) -> str:
        """固定能力を返す。"""
        return "CAP:sync_writer_binding:read_writer_identity"


@dataclass(frozen=True, slots=True)
class _AssertWriterBindingToken(TenantOperationToken):
    """既nonceを同writerの実PG関数で検証する。"""

    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes = field(repr=False)
    device_id: UUID
    game_id: UUID

    @property
    def capability_id(self) -> str:
        """固定能力を返す。"""
        return "CAP:sync_writer_binding:assert_writer_binding"


def _identity(result: TenantOperationResult) -> TenantOperationResult:
    """共通exact型検査でのみdecodeする。"""
    return result


def _decode_assert(result: TenantOperationResult) -> TenantOperationResult:
    """PostgreSQL voidの単一NULL以外をassert成功としない。"""
    if result.rows != ((None,),):
        raise FunctionOperationError("writer assertのvoid応答が不一致")
    return result


def _declarations() -> tuple[FunctionOperationRegistration, ...]:
    """新2署名だけの登録候補を作り、他のregistryを変更しない。"""
    result = []
    for name, token in (
        ("read_writer_identity", _ReadWriterIdentityToken),
        ("assert_writer_binding", _AssertWriterBindingToken),
    ):
        inputs, outputs, nullable, aware = _SYNC_WRITER_BINDING_FUNCTION_TYPES[
            f"sync_fence_api.{name}"
        ]
        result.append(
            FunctionOperationRegistration(
                operation_id=f"SYNC_WRITER_BINDING:{name}",
                capability_id=f"CAP:sync_writer_binding:{name}",
                token_type=token,
                function_id=f"sync_fence_api.{name}",
                statement=_build_fixed_function_statement(
                    "sync_fence_api",
                    name,
                    inputs,
                    tuple(n for n, _ in outputs),
                    name == "read_writer_identity",
                ),
                input_fields=inputs,
                result_fields=outputs,
                min_rows=1,
                max_rows=1,
                decoder=_identity if name == "read_writer_identity" else _decode_assert,
                nullable_results=nullable,
                aware_datetime_results=aware,
            )
        )
    return tuple(result)


_UNREGISTERED_DECLARATIONS = _declarations()
