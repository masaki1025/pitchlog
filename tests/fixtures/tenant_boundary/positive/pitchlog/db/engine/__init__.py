"""アプリ用物理接続の真正性検査シンボル正例。"""

from typing import Any

import psycopg  # ty: ignore


def _verify_application_role_connection(
    connection: psycopg.Connection[Any],
) -> None:
    """許可された物理接続のカタログ検査を実行する。"""
    with connection.cursor() as cursor:
        cursor.execute("SELECT session_user, current_user")
    connection.rollback()
