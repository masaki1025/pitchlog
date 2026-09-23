"""条件 5 の SET app.tenant_id を表す負例。"""

from typing import Any

from sqlalchemy import text  # ty: ignore


def bind(session: Any) -> None:
    session.execute(text("SET app.tenant_id = 'forbidden'"))
