"""初球の未登録固定token宣言。実scopeや端末証明の発行器ではない。"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from pitchlog.repositories.function_operations import (
    _SYNC_FIRST_BALL_FUNCTION_TYPES,
    FunctionOperationRegistration,
    _build_fixed_function_statement,
)
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken


@dataclass(frozen=True, slots=True)
class _FirstBallToken(TenantOperationToken):
    """nonceを秘密として保持する未登録の固定入力。"""

    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes = field(repr=False)
    device_id: UUID
    game_id: UUID


@dataclass(frozen=True, slots=True)
class _BindFirstBallDeviceToken(_FirstBallToken):
    """同writerで端末資格を照合する入力宣言。"""

    credential_digest: bytes = field(repr=False)

    @property
    def capability_id(self) -> str:
        """固定能力だけを返す。"""
        return "CAP:sync_first_ball:bind_device"


@dataclass(frozen=True, slots=True)
class _CheckFirstBallRightToken(_FirstBallToken):
    """同writerで現権利を照合する入力宣言。"""

    internal_generation: int
    recovery_generation: int
    proof_digest: bytes = field(repr=False)

    @property
    def capability_id(self) -> str:
        """固定能力だけを返す。"""
        return "CAP:sync_first_ball:check_current_right"


def _identity(result: TenantOperationResult) -> TenantOperationResult:
    """前後のexact型検査を迂回せず結果を返す。"""
    return result


def _declarations() -> tuple[FunctionOperationRegistration, ...]:
    """runtimeへ登録せず、exact2の不変宣言だけを作る。"""
    registrations = []
    for name, token in (
        ("bind_device", _BindFirstBallDeviceToken),
        ("check_current_right", _CheckFirstBallRightToken),
    ):
        inputs, outputs, nullable, aware = _SYNC_FIRST_BALL_FUNCTION_TYPES[
            f"sync_right_api.{name}"
        ]
        registrations.append(
            FunctionOperationRegistration(
                operation_id=f"SYNC_FIRST_BALL:{name}",
                capability_id=f"CAP:sync_first_ball:{name}",
                token_type=token,
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
        )
    return tuple(registrations)


# 宣言をimportしても実runtime registry/PORT_IMPLEMENTATIONSは更新しない。
_UNREGISTERED_DECLARATIONS = _declarations()


@dataclass(frozen=True, slots=True)
class _ReadFirstBallDeviceStateToken(TenantOperationToken):
    """binding前の状態読取専用。nonce/attempt/phaseを持たない。"""

    device_id: UUID

    @property
    def capability_id(self) -> str:
        """未登録の固定能力だけを返す。"""
        return "CAP:sync_first_ball:read_device_state"


def _device_state_read_declaration() -> FunctionOperationRegistration:
    """既exact2へ混入させず、未登録の単独宣言を作る。"""
    inputs, outputs, nullable, aware = _SYNC_FIRST_BALL_FUNCTION_TYPES[
        "sync_right_api.read_device_state"
    ]
    return FunctionOperationRegistration(
        operation_id="SYNC_FIRST_BALL:read_device_state",
        capability_id="CAP:sync_first_ball:read_device_state",
        token_type=_ReadFirstBallDeviceStateToken,
        function_id="sync_right_api.read_device_state",
        statement=_build_fixed_function_statement(
            "sync_right_api",
            "read_device_state",
            inputs,
            tuple(name for name, _ in outputs),
            True,
        ),
        input_fields=inputs,
        result_fields=outputs,
        decoder=_identity,
        min_rows=1,
        max_rows=1,
        nullable_results=nullable,
        aware_datetime_results=aware,
    )


# 既_UNREGISTERED_DECLARATIONSも実runtimeも変更しない。
_UNREGISTERED_DEVICE_STATE_READ = _device_state_read_declaration()
