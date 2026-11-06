"""非play履歴の有限readonly能力1。書込資格は発行しない。"""

from dataclasses import dataclass
from uuid import UUID

from pitchlog.repositories.first_ball import _identity
from pitchlog.repositories.function_operations import (
    _SYNC_ORDINARY_PREFIX_FUNCTION_TYPES,
    FunctionOperationRegistration,
    _build_fixed_function_statement,
)
from pitchlog.repositories.tokens import TenantOperationToken


@dataclass(frozen=True, slots=True)
class NonplayActiveHistoryReadToken(TenantOperationToken):
    """実CP/版を固定した最大100件のkeyset。tenantはhandleだけから供給する。"""

    game_id: UUID
    generation: int
    checkpoint_id: UUID
    revision: int
    epoch: int
    d3: int
    logical_version: int
    after_order: int
    after_d1: int
    after_id: UUID
    page_size: int

    def __post_init__(self):
        """bool/異型/負値/上限超過を暗黙変換しない。"""
        if (
            any(
                type(v) is not UUID
                for v in (self.game_id, self.checkpoint_id, self.after_id)
            )
            or any(
                type(v) is not int or not 0 < v < 2**63
                for v in (
                    self.generation,
                    self.revision,
                    self.epoch,
                    self.d3,
                    self.logical_version,
                )
            )
            or any(
                type(v) is not int or not 0 <= v < 2**63
                for v in (self.after_order, self.after_d1)
            )
            or type(self.page_size) is not int
            or not 1 <= self.page_size <= 100
        ):
            raise ValueError("非play page anchorが不正")

    @property
    def capability_id(self):
        """固定readonly関数1の能力だけを返す。"""
        return "CAP:sync_ordinary_pitch:read_nonplay_active_history"


def _registration():
    """実型全値から決定的に構成する。"""
    name = "read_nonplay_active_history"
    inputs, outputs, nullable, aware, minimum, maximum = (
        _SYNC_ORDINARY_PREFIX_FUNCTION_TYPES["sync_right_api." + name]
    )
    return FunctionOperationRegistration(
        operation_id="SYNC_ORDINARY_PITCH:" + name,
        capability_id="CAP:sync_ordinary_pitch:" + name,
        token_type=NonplayActiveHistoryReadToken,
        function_id="sync_right_api." + name,
        statement=_build_fixed_function_statement(
            "sync_right_api", name, inputs, tuple(k for k, _ in outputs), True
        ),
        input_fields=inputs,
        result_fields=outputs,
        decoder=_identity,
        min_rows=minimum,
        max_rows=maximum,
        nullable_results=nullable,
        aware_datetime_results=aware,
    )


NONPLAY_READ_OPERATIONS = (_registration(),)
