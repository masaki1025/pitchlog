"""engine factory の戻り値を別名化する負例。"""

from pitchlog.db.engine import create_database_engine  # ty: ignore


def bypass() -> object:
    """変数名に依存せず Connection の SQL 実行へ到達する。"""
    database = create_database_engine()
    handle = database.connect()
    return handle.exec_driver_sql("SELECT 1")
