"""条件 5 の psycopg 直呼びを表す負例。"""

import psycopg as pg  # ty: ignore


def open_connection() -> object:
    return pg.connect("")
