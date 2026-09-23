"""条件 5 の raw_connection を表す負例。"""

from typing import Any


def open_connection(engine: Any) -> object:
    return engine.raw_connection()
