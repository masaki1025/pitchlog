"""条件 5 の SQLAlchemy ORM query を表す負例。"""

from typing import Any


def load(db_session: Any) -> object:
    return db_session.query(object).all()
