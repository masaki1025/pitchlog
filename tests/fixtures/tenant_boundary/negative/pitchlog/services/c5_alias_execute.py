"""条件 5 の DB API alias を表す負例。"""

from typing import Any


def load(session: Any) -> object:
    runner = session.execute
    return runner("SELECT 1")
