"""独立ordinary device/right資格の有限関数token。"""

from dataclasses import dataclass, field

from pitchlog.repositories.first_ball import _FirstBallToken, _identity
from pitchlog.repositories.function_operations import (
    _SYNC_ORDINARY_PITCH_FUNCTION_TYPES,
    FunctionOperationRegistration,
    _build_fixed_function_statement,
)


@dataclass(frozen=True, slots=True)
class BindOrdinaryDeviceToken(_FirstBallToken):
    """実credentialだけを同writer資格関数へ渡す。"""

    credential_digest: bytes = field(repr=False)

    @property
    def capability_id(self) -> str:
        """新しい有限関数能力の識別だけを返す。"""
        return "CAP:sync_ordinary_pitch:bind_ordinary_device"


@dataclass(frozen=True, slots=True)
class CheckOrdinaryRightToken(_FirstBallToken):
    """実同世代/復旧/開始proofの閉参照。"""

    internal_generation: int
    recovery_generation: int
    proof_digest: bytes = field(repr=False)

    @property
    def capability_id(self) -> str:
        """新しい有限関数能力の識別だけを返す。"""
        return "CAP:sync_ordinary_pitch:check_ordinary_right"


@dataclass(frozen=True, slots=True)
class PrepareOrdinaryProjectionToken(_FirstBallToken):
    """核の実frameからのみ組み立てる閉準備値。boolを受け取らない。"""

    preparation_json: str = field(repr=False)

    @property
    def capability_id(self) -> str:
        """限定prepare関数の能力だけを返す。"""
        return "CAP:sync_ordinary_pitch:prepare_ordinary_projection"


def _declarations():
    """既関数と同じexact型を独立関数名で固定する。"""
    declarations = []
    for name, token_type in (
        ("bind_ordinary_device", BindOrdinaryDeviceToken),
        ("check_ordinary_right", CheckOrdinaryRightToken),
        ("prepare_ordinary_projection", PrepareOrdinaryProjectionToken),
    ):
        inputs, outputs, nullable, aware = _SYNC_ORDINARY_PITCH_FUNCTION_TYPES[
            f"sync_right_api.{name}"
        ]
        declarations.append(
            FunctionOperationRegistration(
                operation_id=f"SYNC_ORDINARY_PITCH:{name}",
                capability_id=f"CAP:sync_ordinary_pitch:{name}",
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
        )
    return tuple(declarations)


ORDINARY_QUALIFICATION_OPERATIONS = _declarations()
