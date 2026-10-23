"""外部台帳のexact私有DB境界の正例。"""
from __future__ import annotations

from typing import Any

import psycopg  # ty: ignore


class adapter:
    """製品の限定モジュールを表す。"""

    @staticmethod
    def _connect(dsn: str, timeout: float) -> psycopg.Connection[Any]:
        """登録したAPIだけを使用する。"""
        return psycopg.connect(dsn)
