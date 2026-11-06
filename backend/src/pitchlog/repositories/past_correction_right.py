"""P3の無印記録権読取だけを同writerへ登録する。"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from pitchlog.repositories.function_operations import (
    _SYNC_P3_FUNCTION_TYPES,
    FunctionOperationRegistration,
    _build_fixed_function_statement,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken


@dataclass(frozen=True, slots=True)
class _BindP3DeviceToken(TenantOperationToken):
    """同writerの端末提示だけを無印DB関数へ渡す。"""

    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes = field(repr=False)
    device_id: UUID
    game_id: UUID
    credential_digest: bytes = field(repr=False)

    @property
    def capability_id(self) -> str:
        """P3端末再照合だけの固定能力。"""
        return "CAP:sync_p3:bind_p3_device"


@dataclass(frozen=True, slots=True)
class _CheckP3RightToken(TenantOperationToken):
    """実bound writerのP3提示証明をDBだけに照合させる。"""

    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes = field(repr=False)
    device_id: UUID
    game_id: UUID
    internal_generation: int
    recovery_generation: int
    proof_digest: bytes = field(repr=False)

    @property
    def capability_id(self) -> str:
        """P3専用の固定読取capability。"""
        return "CAP:sync_p3:check_p3_right"


def _identity(result: TenantOperationResult) -> TenantOperationResult:
    """共通decoderのexact結果を変形しない。"""
    return result


def _registration(name: str, token_type: type[TenantOperationToken]):
    """P3の二つの有限関数宣言を同じ型核から作る。"""
    inputs, outputs, nullable, aware = _SYNC_P3_FUNCTION_TYPES[
        f"sync_right_api.{name}"
    ]
    return FunctionOperationRegistration(
        operation_id=f"SYNC_P3:{name}",
        capability_id=f"CAP:sync_p3:{name}",
        token_type=token_type,
        function_id=f"sync_right_api.{name}",
        statement=_build_fixed_function_statement(
            "sync_right_api", name, inputs, tuple(n for n, _ in outputs), True
        ),
        input_fields=inputs,
        result_fields=outputs,
        decoder=_identity,
        min_rows=1,
        max_rows=1,
        nullable_results=nullable,
        aware_datetime_results=aware,
    )


P3_DEVICE_BIND_OPERATION = _registration("bind_p3_device", _BindP3DeviceToken)
P3_RIGHT_CHECK_OPERATION = _registration("check_p3_right", _CheckP3RightToken)
