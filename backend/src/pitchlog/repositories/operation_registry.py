"""製品 operation の登録を一箇所に集める。"""

from __future__ import annotations

from types import MappingProxyType

from pitchlog.repositories.first_ball import (
    _UNREGISTERED_DECLARATIONS as _FIRST_BALL_FUNCTION_OPERATIONS,
)
from pitchlog.repositories.first_ball import DEVICE_STATE_READ_OPERATION
from pitchlog.repositories.first_ball_operations import FIRST_BALL_PLAY_OPERATIONS
from pitchlog.repositories.function_operations import (
    FunctionOperationRegistration,
    build_function_registry,
)
from pitchlog.repositories.games import PREPARING_GAME_READ_OPERATIONS
from pitchlog.repositories.invalidation_intents import INVALIDATION_INTENT_OPERATIONS
from pitchlog.repositories.lineup_memory import LINEUP_MEMORY_OPERATIONS
from pitchlog.repositories.operation_registration import OperationRegistration
from pitchlog.repositories.ordinary_order import ORDINARY_ORDER_OPERATIONS
from pitchlog.repositories.ordinary_pitch_operations import (
    ORDINARY_PLAY_OPERATIONS,
    PLAY_PREFIX_PLAY_OPERATIONS,
)
from pitchlog.repositories.ordinary_pitch_qualification import (
    ORDINARY_QUALIFICATION_OPERATIONS,
)
from pitchlog.repositories.ordinary_prefix_operations import (
    ORDINARY_PREFIX_OPERATIONS,
    PLAY_PREFIX_OPERATIONS,
)
from pitchlog.repositories.pitch_type_options import PITCH_TYPE_OPTIONS_OPERATIONS
from pitchlog.repositories.preparing_game_creation import (
    PREPARING_GAME_CREATE_OPERATIONS,
)
from pitchlog.repositories.recorded_snapshot_operations import (
    RECORDED_SNAPSHOT_OPERATIONS,
)
from pitchlog.repositories.rg1 import (
    RG1CommitCheckToken,
    RG1PrecheckToken,
    RG1ScopeBindingToken,
    _build_rg1_read_statement,
    _build_rg1_scope_binding_statement,
    _decode_rg1_result,
)
from pitchlog.repositories.roster import ROSTER_OPERATIONS
from pitchlog.repositories.rule_resolution import (
    StageAResolveRuleToken,
    _build_stage_a_rule_statement,
    _decode_stage_a_rule_result,
)
from pitchlog.repositories.started_snapshot_operations import (
    STARTED_SNAPSHOT_OPERATIONS,
)
from pitchlog.repositories.sync_apply import SYNC_APPLY_OPERATIONS
from pitchlog.repositories.tenant_profile import TENANT_PROFILE_OPERATIONS
from pitchlog.repositories.writer_binding import (
    _UNREGISTERED_DECLARATIONS as _WRITER_BINDING_FUNCTION_OPERATIONS,
)

PRODUCT_OPERATIONS: tuple[OperationRegistration, ...] = (
    *PREPARING_GAME_READ_OPERATIONS,
    *ROSTER_OPERATIONS,
    *INVALIDATION_INTENT_OPERATIONS,
    *LINEUP_MEMORY_OPERATIONS,
    *SYNC_APPLY_OPERATIONS,
    *TENANT_PROFILE_OPERATIONS,
    *STARTED_SNAPSHOT_OPERATIONS,
    *FIRST_BALL_PLAY_OPERATIONS,
    *RECORDED_SNAPSHOT_OPERATIONS,
    *PREPARING_GAME_CREATE_OPERATIONS,
    *PITCH_TYPE_OPTIONS_OPERATIONS,
    *ORDINARY_PLAY_OPERATIONS,
    *PLAY_PREFIX_PLAY_OPERATIONS,
)


_STATIC_PRODUCT_FUNCTION_BINDING_IDS = frozenset(
    (
        "SYNC_FIRST_BALL:bind_device",
        "SYNC_FIRST_BALL:check_current_right",
        "SYNC_WRITER_BINDING:read_writer_identity",
        "SYNC_WRITER_BINDING:assert_writer_binding",
        "SYNC_FIRST_BALL:read_device_state",
        "SYNC_ORDINARY_PITCH:bind_ordinary_device",
        "SYNC_ORDINARY_PITCH:check_ordinary_right",
        "SYNC_ORDINARY_PITCH:prepare_ordinary_projection",
        "SYNC_ORDINARY_PITCH:read_ordinary_checkpoint",
        "SYNC_ORDINARY_PITCH:lock_ordinary_checkpoint",
        "SYNC_ORDINARY_PITCH:read_ordinary_history_page",
        "SYNC_ORDINARY_PITCH:read_ordinary_order_summary",
        "SYNC_PLAY_PREFIX:read_play_prefix_checkpoint",
        "SYNC_PLAY_PREFIX:lock_play_prefix_checkpoint",
        "SYNC_PLAY_PREFIX:read_play_prefix_history_page",
        "SYNC_PLAY_PREFIX:prepare_play_prefix_projection",
    )
)


def _registered_product_function(
    registration: FunctionOperationRegistration, *, operation_id: str
) -> FunctionOperationRegistration:
    """単一源の実registrationと静的IDを完全照合し、同じobjectだけを登録する。"""
    if (
        type(registration) is not FunctionOperationRegistration
        or type(operation_id) is not str
        or operation_id not in _STATIC_PRODUCT_FUNCTION_BINDING_IDS
        or registration.operation_id != operation_id
    ):
        raise ValueError("製品固定関数の実参照と静的IDが不一致")
    return registration


# 既8関数を保持し、binding前の端末状態readだけを末尾へ加える。
PRODUCT_FUNCTION_OPERATIONS: tuple[FunctionOperationRegistration, ...] = (
    FunctionOperationRegistration(
        operation_id="RG1:precheck",
        token_type=RG1PrecheckToken,
        capability_id="CAP:rg1:precheck",
        function_id="rg1_api.rg1_read_open",
        statement=_build_rg1_read_statement("precheck"),
        input_fields=(),
        result_fields=(("is_open", bool),),
        min_rows=1,
        max_rows=1,
        decoder=_decode_rg1_result,
    ),
    FunctionOperationRegistration(
        operation_id="RG1:commit_check",
        token_type=RG1CommitCheckToken,
        capability_id="CAP:rg1:commit_check",
        function_id="rg1_api.rg1_assert_open_before_commit",
        statement=_build_rg1_read_statement("commit_check"),
        input_fields=(),
        result_fields=(("is_open", bool),),
        min_rows=1,
        max_rows=1,
        decoder=_decode_rg1_result,
    ),
    FunctionOperationRegistration(
        operation_id="RG1:scope_binding",
        token_type=RG1ScopeBindingToken,
        capability_id="CAP:rg1:scope_binding",
        function_id="rg1_control.scope_binding",
        statement=_build_rg1_scope_binding_statement(),
        input_fields=(),
        result_fields=(("binding", str),),
        min_rows=1,
        max_rows=1,
        decoder=_decode_rg1_result,
    ),
    FunctionOperationRegistration(
        operation_id="RULE:resolve_stage_a",
        token_type=StageAResolveRuleToken,
        capability_id="CAP:rules:resolve_stage_a",
        function_id="public.resolve_stage_a_rule",
        statement=_build_stage_a_rule_statement(),
        input_fields=(
            ("game_type_key", str),
            ("tournament_key", str),
            ("has_override", bool),
        ),
        result_fields=(("resolution", MappingProxyType),),
        min_rows=1,
        max_rows=1,
        decoder=_decode_stage_a_rule_result,
        nonempty_inputs=("game_type_key", "tournament_key"),
    ),
    _registered_product_function(
        _FIRST_BALL_FUNCTION_OPERATIONS[0], operation_id="SYNC_FIRST_BALL:bind_device"
    ),
    _registered_product_function(
        _FIRST_BALL_FUNCTION_OPERATIONS[1],
        operation_id="SYNC_FIRST_BALL:check_current_right",
    ),
    _registered_product_function(
        _WRITER_BINDING_FUNCTION_OPERATIONS[0],
        operation_id="SYNC_WRITER_BINDING:read_writer_identity",
    ),
    _registered_product_function(
        _WRITER_BINDING_FUNCTION_OPERATIONS[1],
        operation_id="SYNC_WRITER_BINDING:assert_writer_binding",
    ),
    _registered_product_function(
        DEVICE_STATE_READ_OPERATION, operation_id="SYNC_FIRST_BALL:read_device_state"
    ),
    _registered_product_function(
        ORDINARY_QUALIFICATION_OPERATIONS[0],
        operation_id="SYNC_ORDINARY_PITCH:bind_ordinary_device",
    ),
    _registered_product_function(
        ORDINARY_QUALIFICATION_OPERATIONS[1],
        operation_id="SYNC_ORDINARY_PITCH:check_ordinary_right",
    ),
    _registered_product_function(
        ORDINARY_QUALIFICATION_OPERATIONS[2],
        operation_id="SYNC_ORDINARY_PITCH:prepare_ordinary_projection",
    ),
    _registered_product_function(
        ORDINARY_PREFIX_OPERATIONS[0],
        operation_id="SYNC_ORDINARY_PITCH:read_ordinary_checkpoint",
    ),
    _registered_product_function(
        ORDINARY_PREFIX_OPERATIONS[1],
        operation_id="SYNC_ORDINARY_PITCH:lock_ordinary_checkpoint",
    ),
    _registered_product_function(
        ORDINARY_PREFIX_OPERATIONS[2],
        operation_id="SYNC_ORDINARY_PITCH:read_ordinary_history_page",
    ),
    _registered_product_function(
        ORDINARY_ORDER_OPERATIONS[0],
        operation_id="SYNC_ORDINARY_PITCH:read_ordinary_order_summary",
    ),
    _registered_product_function(
        PLAY_PREFIX_OPERATIONS[0],
        operation_id="SYNC_PLAY_PREFIX:read_play_prefix_checkpoint",
    ),
    _registered_product_function(
        PLAY_PREFIX_OPERATIONS[1],
        operation_id="SYNC_PLAY_PREFIX:lock_play_prefix_checkpoint",
    ),
    _registered_product_function(
        PLAY_PREFIX_OPERATIONS[2],
        operation_id="SYNC_PLAY_PREFIX:read_play_prefix_history_page",
    ),
    _registered_product_function(
        PLAY_PREFIX_OPERATIONS[3],
        operation_id="SYNC_PLAY_PREFIX:prepare_play_prefix_projection",
    ),
)
FUNCTION_OPERATION_REGISTRY = build_function_registry(
    PRODUCT_FUNCTION_OPERATIONS,
    frozenset(registration.token_type for registration in PRODUCT_OPERATIONS),
    frozenset(registration.capability_id for registration in PRODUCT_OPERATIONS),
)
