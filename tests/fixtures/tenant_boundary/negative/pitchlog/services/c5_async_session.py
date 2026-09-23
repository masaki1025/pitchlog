"""条件 5 の async DB API を表す負例。"""

from typing import Any


async def load(async_session: Any) -> object:
    return await async_session.execute("SELECT 1")
