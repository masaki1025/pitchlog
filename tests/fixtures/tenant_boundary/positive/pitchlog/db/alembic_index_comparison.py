"""migration ownerの固定catalog読取だけに限定した正例。"""

from sqlalchemy import Connection, text


def _require_catalog(connection: Connection) -> None:
    """型を明示した接続でtextとexecuteだけを使用する。"""
    connection.execute(text("SELECT 1"))
