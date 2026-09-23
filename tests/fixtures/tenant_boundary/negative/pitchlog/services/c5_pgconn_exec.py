"""psycopg 低水準 PGconn API の負例。"""

from psycopg.pq import PGconn  # ty: ignore


def bypass(connection: PGconn) -> object:
    """PGconn.exec_ を直接呼び出す。"""
    return connection.exec_(b"SELECT 1")
