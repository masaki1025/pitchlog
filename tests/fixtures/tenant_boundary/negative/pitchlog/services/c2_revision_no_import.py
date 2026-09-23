"""条件 2 の改訂番号 import を表す負例。"""

from pitchlog.sync.contracts import revision_no  # ty: ignore


def use_contract() -> object:
    return revision_no
