"""条件 3 のイニング状態契約 import を表す負例。"""

from pitchlog.domain.calculations import inning_state  # ty: ignore


def use_contract() -> object:
    return inning_state
