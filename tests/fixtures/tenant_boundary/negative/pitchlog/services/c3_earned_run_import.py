"""条件 3 の自責点契約 import を表す負例。"""

from pitchlog.domain.calculations import earned_run  # ty: ignore


def use_contract() -> object:
    return earned_run
