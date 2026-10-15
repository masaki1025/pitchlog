"""製品 operation の登録を一箇所に集める。"""

from __future__ import annotations

from pitchlog.repositories.function_operations import (
    FunctionOperationRegistration,
    build_function_registry,
)
from pitchlog.repositories.invalidation_intents import INVALIDATION_INTENT_OPERATIONS
from pitchlog.repositories.lineup_memory import LINEUP_MEMORY_OPERATIONS
from pitchlog.repositories.operation_registration import OperationRegistration
from pitchlog.repositories.roster import ROSTER_OPERATIONS

PRODUCT_OPERATIONS: tuple[OperationRegistration, ...] = (
    *ROSTER_OPERATIONS,
    *INVALIDATION_INTENT_OPERATIONS,
    *LINEUP_MEMORY_OPERATIONS,
)

# Aでは製品関数を登録しない。B/Cは各個別ゲートで追加する。
PRODUCT_FUNCTION_OPERATIONS: tuple[FunctionOperationRegistration, ...] = ()
FUNCTION_OPERATION_REGISTRY = build_function_registry(
    PRODUCT_FUNCTION_OPERATIONS,
    frozenset(registration.token_type for registration in PRODUCT_OPERATIONS),
    frozenset(registration.capability_id for registration in PRODUCT_OPERATIONS),
)
