"""条件 2 の墓標 import を表す負例。"""

from pitchlog.sync.contracts import tombstone  # ty: ignore


def use_contract() -> object:
    return tombstone
