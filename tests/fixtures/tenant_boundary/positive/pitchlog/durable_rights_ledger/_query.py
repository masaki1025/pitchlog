"""外部台帳のexact私有DB境界の正例。"""
from __future__ import annotations

from typing import Any, Literal

import psycopg  # ty: ignore

Operation = Literal["identity", "business_identity", "fence", "reserve", "claim", "read", "advance"]


class adapter:
    """製品の限定モジュールを表す。"""

    @staticmethod
    def _query(
        connection: psycopg.Connection[Any],
        operation: Operation,
        params: tuple[object, ...] = (),
    ) -> tuple[Any, ...]:
        """登録したAPIだけを使用する。"""
        return connection.execute('SELECT 1').fetchone()
