"""アプリケーション用 SQLAlchemy engine を生成する。"""

import os
from collections.abc import Mapping

from sqlalchemy import Engine, create_engine

from pitchlog.db.config import (
    DatabaseConfigurationError,
    require_database_configuration,
)
from pitchlog.db.url import normalize_postgresql_url

_DATABASE_URL_VARIABLE = "PITCHLOG_DATABASE_URL"
_DATABASE_POOLED_VARIABLE = "PITCHLOG_DATABASE_POOLED"


def engine_connect_args(pooled: bool) -> dict[str, object]:
    """Pooler 利用有無から psycopg の接続引数を導出する。

    Args:
        pooled: Transaction pooler を経由するか。

    Returns:
        SQLAlchemy engine に渡す psycopg 接続引数。
    """
    if pooled:
        return {"prepare_threshold": None}
    return {}


def engine_connect_args_violations(
    pooled: bool, connect_args: Mapping[str, object]
) -> list[str]:
    """Pooler 設定と psycopg 接続引数の違反を返す。

    Args:
        pooled: Transaction pooler を経由するか。
        connect_args: 検査対象の psycopg 接続引数。

    Returns:
        検出した違反の一覧。
    """
    if pooled and (
        "prepare_threshold" not in connect_args
        or connect_args["prepare_threshold"] is not None
    ):
        return ["pooler 利用時は prepare_threshold=None が必要"]
    if not pooled and "prepare_threshold" in connect_args:
        return ["pooler 非利用時は prepare_threshold を指定しない"]
    return []


def _database_is_pooled(value: str) -> bool:
    """明示された pooler フラグを bool へ変換する。

    Args:
        value: 環境から取得済みの pooler フラグ。

    Returns:
        ``true`` なら True、``false`` なら False。

    Raises:
        DatabaseConfigurationError: ``true`` / ``false`` 以外の場合。
    """
    if value == "true":
        return True
    if value == "false":
        return False
    raise DatabaseConfigurationError(
        f"{_DATABASE_POOLED_VARIABLE} は true または false で指定する"
    )


def create_database_engine() -> Engine:
    """アプリケーション用 URL から SQLAlchemy engine を生成する。

    Returns:
        psycopg 3 を使用する同期 engine。
    """
    database_url = require_database_configuration(
        _DATABASE_URL_VARIABLE,
        os.environ.get(_DATABASE_URL_VARIABLE),
    )
    pooled_value = require_database_configuration(
        _DATABASE_POOLED_VARIABLE,
        os.environ.get(_DATABASE_POOLED_VARIABLE),
    )
    connect_args = engine_connect_args(_database_is_pooled(pooled_value))
    normalized_url = normalize_postgresql_url(database_url)
    return create_engine(normalized_url, connect_args=connect_args)
