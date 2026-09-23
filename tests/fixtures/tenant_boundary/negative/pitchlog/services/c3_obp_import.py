"""条件 3 の出塁率契約 import を表す負例。"""

from pitchlog.domain.calculations import obp  # ty: ignore


def use_contract() -> object:
    return obp
