"""製品 operation の登録を一箇所に集める。"""

from __future__ import annotations

from types import MappingProxyType

from pitchlog.repositories.first_ball import (
    _UNREGISTERED_DECLARATIONS as _FIRST_BALL_FUNCTION_OPERATIONS,
)
from pitchlog.repositories.first_ball_operations import FIRST_BALL_PLAY_OPERATIONS
from pitchlog.repositories.function_operations import (
    FunctionOperationRegistration,
    build_function_registry,
)
from pitchlog.repositories.games import PREPARING_GAME_READ_OPERATIONS
from pitchlog.repositories.invalidation_intents import INVALIDATION_INTENT_OPERATIONS
from pitchlog.repositories.lineup_memory import LINEUP_MEMORY_OPERATIONS
from pitchlog.repositories.operation_registration import OperationRegistration
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
)

# 既RG1/段階A4件と同writerの閉じた保存用4件だけを登録する。
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
    *_FIRST_BALL_FUNCTION_OPERATIONS,
    *_WRITER_BINDING_FUNCTION_OPERATIONS,
)
FUNCTION_OPERATION_REGISTRY = build_function_registry(
    PRODUCT_FUNCTION_OPERATIONS,
    frozenset(registration.token_type for registration in PRODUCT_OPERATIONS),
    frozenset(registration.capability_id for registration in PRODUCT_OPERATIONS),
)
