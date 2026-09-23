"""条件 3 の責任投手契約 import を表す負例。"""

from pitchlog.domain.calculations import responsible_pitcher  # ty: ignore


def use_contract() -> object:
    return responsible_pitcher
