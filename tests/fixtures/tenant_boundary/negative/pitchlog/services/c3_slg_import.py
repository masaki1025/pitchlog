"""条件 3 の長打率契約 import を表す負例。"""

from pitchlog.domain.calculations import slg  # ty: ignore


def use_contract() -> object:
    return slg
