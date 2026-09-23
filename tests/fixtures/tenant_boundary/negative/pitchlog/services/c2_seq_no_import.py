"""条件 2 の短縮連番 import を表す負例。"""

from pitchlog.sync.contracts import seq_no  # ty: ignore


def use_contract() -> object:
    return seq_no
