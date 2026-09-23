"""アプリ用 engine 生成の許可シンボル正例。"""

from sqlalchemy import Engine, create_engine  # ty: ignore


def create_database_engine() -> Engine:
    """真正性検査を配線する engine の生成だけを許可する。"""
    return create_engine("postgresql+psycopg://")
