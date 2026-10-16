"""固定関数入口を迂回してSessionを直接実行する負例。"""

from sqlalchemy.orm import Session  # ty: ignore[unresolved-import]


def bypass_function_scope(session: Session, statement: object) -> object:
    """任意の文を閉じたoperationの外から実行する。"""
    return session.execute(statement)
