"""アプリケーション用 SQLAlchemy engine を生成する。"""

import os

from sqlalchemy import Engine, create_engine

from pitchlog.db.url import normalize_postgresql_url

_DATABASE_URL_VARIABLE = "PITCHLOG_DATABASE_URL"


def create_database_engine() -> Engine:
    """アプリケーション用 URL から SQLAlchemy engine を生成する。

    Returns:
        psycopg 3 を使用する同期 engine。
    """
    database_url = os.environ[_DATABASE_URL_VARIABLE]
    return create_engine(normalize_postgresql_url(database_url))
