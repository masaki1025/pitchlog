"""製品 operation の登録を一箇所に集める。"""

from __future__ import annotations

from pitchlog.repositories.operation_registration import OperationRegistration
from pitchlog.repositories.roster import ROSTER_OPERATIONS

PRODUCT_OPERATIONS: tuple[OperationRegistration, ...] = ROSTER_OPERATIONS
