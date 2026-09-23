"""条件 3 の打席結果契約 import を表す負例。"""

from pitchlog.domain.calculations import at_bat_result  # ty: ignore


def use_contract() -> object:
    return at_bat_result
