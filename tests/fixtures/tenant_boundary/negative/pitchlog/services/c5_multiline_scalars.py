"""条件 5 の複数行 DB API 呼び出しを表す負例。"""

from typing import Any


def load(session: Any) -> object:
    return (
        session
        .scalars("SELECT 1")
    )
