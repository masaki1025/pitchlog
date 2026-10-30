"""段階起動の既実装に対応する有限DB API正例。"""


import psycopg  # ty: ignore


class stage_a_startup:
    """製品モジュールの許可シンボルを表す。"""

    @staticmethod
    def _require_initial_state(applicator_dsn: str) -> None:
        """宣言したAPIのみを固定した名前で呼ぶ。"""
        with psycopg.connect(applicator_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
