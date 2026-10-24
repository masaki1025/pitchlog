"""外部台帳のexact私有DB境界の正例。"""
from __future__ import annotations

from typing import Any

import psycopg  # ty: ignore


class adapter:
    """製品の限定モジュールを表す。"""

    @staticmethod
    def _commit(connection: psycopg.Connection[Any], timeout: float) -> None:
        """登録したAPIだけを使用する。"""
        connection.commit()
