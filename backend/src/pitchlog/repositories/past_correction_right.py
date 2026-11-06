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


_INPUTS, _OUTPUTS, _NULLABLE, _AWARE = _SYNC_P3_FUNCTION_TYPES[
    "sync_right_api.check_p3_right"
]
P3_RIGHT_CHECK_OPERATION = FunctionOperationRegistration(
    operation_id="SYNC_P3:check_p3_right",
    capability_id="CAP:sync_p3:check_p3_right",
    token_type=_CheckP3RightToken,
    function_id="sync_right_api.check_p3_right",
    statement=_build_fixed_function_statement(
        "sync_right_api",
        "check_p3_right",
        _INPUTS,
        tuple(name for name, _ in _OUTPUTS),
        True,
    ),
    input_fields=_INPUTS,
    result_fields=_OUTPUTS,
    decoder=_identity,
    min_rows=1,
    max_rows=1,
    nullable_results=_NULLABLE,
    aware_datetime_results=_AWARE,
)
