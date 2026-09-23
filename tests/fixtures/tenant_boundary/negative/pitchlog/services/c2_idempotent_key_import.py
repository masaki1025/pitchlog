"""条件 2 の別綴りのべき等キー import を表す負例。"""

from pitchlog.sync.contracts import idempotent_key  # ty: ignore


def use_contract() -> object:
    return idempotent_key
