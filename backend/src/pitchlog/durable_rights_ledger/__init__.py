"""業務復元範囲外の記録権耐久台帳候補を提供する。"""

from .adapter import (
    DurableLedger,
    LedgerEndpoints,
    LedgerOutcomeUnconfirmed,
    LedgerUnavailable,
)

__all__ = (
    "DurableLedger",
    "LedgerEndpoints",
    "LedgerOutcomeUnconfirmed",
    "LedgerUnavailable",
)
