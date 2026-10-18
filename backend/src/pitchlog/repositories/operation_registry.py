"""製品 operation の登録を一箇所に集める。"""

from __future__ import annotations

from pitchlog.repositories.function_operations import (
    FunctionOperationRegistration,
    build_function_registry,
)
from pitchlog.repositories.invalidation_intents import INVALIDATION_INTENT_OPERATIONS
from pitchlog.repositories.lineup_memory import LINEUP_MEMORY_OPERATIONS
from pitchlog.repositories.operation_registration import OperationRegistration
from pitchlog.repositories.rg1 import (
    RG1CommitCheckToken,
    RG1PrecheckToken,
    _build_rg1_read_statement,
    _decode_rg1_result,
)
from pitchlog.repositories.roster import ROSTER_OPERATIONS
from pitchlog.repositories.sync_apply import SYNC_APPLY_OPERATIONS
from pitchlog.repositories.tenant_profile import TENANT_PROFILE_OPERATIONS

PRODUCT_OPERATIONS: tuple[OperationRegistration, ...] = (
    *ROSTER_OPERATIONS,
    *INVALIDATION_INTENT_OPERATIONS,
    *LINEUP_MEMORY_OPERATIONS,
    *SYNC_APPLY_OPERATIONS,
    *TENANT_PROFILE_OPERATIONS,
)

# RG1の固定読取2件だけを登録する。共有実行器の他の入口は変更しない。
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
)
FUNCTION_OPERATION_REGISTRY = build_function_registry(
    PRODUCT_FUNCTION_OPERATIONS,
    frozenset(registration.token_type for registration in PRODUCT_OPERATIONS),
    frozenset(registration.capability_id for registration in PRODUCT_OPERATIONS),
)
