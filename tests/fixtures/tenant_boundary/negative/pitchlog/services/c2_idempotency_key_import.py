"""条件 2 のべき等キー import を表す負例。"""

from pitchlog.sync.contracts import idempotency_key  # ty: ignore


def use_contract() -> object:
    return idempotency_key
