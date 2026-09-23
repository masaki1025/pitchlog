"""条件 2 の連番 import を表す負例。"""

from pitchlog.sync.contracts import sequence_no  # ty: ignore


def use_contract() -> object:
    return sequence_no
