"""通常appendの実末尾/O4集約を固定definer bridgeへ束縛する。"""

from dataclasses import dataclass
from uuid import UUID

from pitchlog.repositories.first_ball import _identity
from pitchlog.repositories.function_operations import (
    FunctionOperationRegistration,
    _build_fixed_function_statement,
)
from pitchlog.repositories.tokens import TenantOperationToken


@dataclass(frozen=True, slots=True)
class OrdinaryOrderSummaryToken(TenantOperationToken):
    """同tenant/gameの実D2末尾と重複有無だけを一点で読む。"""

    game_id: UUID

    @property
    def capability_id(self):
        """自由SQL/表権限に置換できない有限能力。"""
        return "CAP:sync_ordinary_pitch:read_ordinary_order_summary"


ORDINARY_ORDER_OPERATIONS = (
    FunctionOperationRegistration(
        operation_id="SYNC_ORDINARY_PITCH:read_ordinary_order_summary",
        token_type=OrdinaryOrderSummaryToken,
        capability_id="CAP:sync_ordinary_pitch:read_ordinary_order_summary",
        function_id="sync_right_api.read_ordinary_order_summary",
        statement=_build_fixed_function_statement(
            "sync_right_api",
            "read_ordinary_order_summary",
            (("game_id", UUID),),
            ("record_json",),
            True,
        ),
        input_fields=(("game_id", UUID),),
        result_fields=(("record_json", str),),
        decoder=_identity,
        min_rows=1,
        max_rows=1,
    ),
)
