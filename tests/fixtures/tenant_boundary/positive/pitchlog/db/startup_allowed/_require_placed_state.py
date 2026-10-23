"""段階起動DB APIの限定許可正例。"""

import psycopg  # ty: ignore


class stage_a_startup:
    """製品モジュールの許可シンボルを表す。"""

    @staticmethod
    def _require_placed_state(applicator_dsn: str) -> None:
        """登録済みのDB APIだけを使用する。"""
        with psycopg.connect(applicator_dsn) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
