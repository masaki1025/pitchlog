"""段階起動の既実装に対応する有限DB API正例。"""

from typing import Any


class stage_a_startup:
    """製品モジュールの許可シンボルを表す。"""

    @staticmethod
    def _check_writer_storage(connection: Any, revision: str) -> None:
        """宣言したAPIのみを固定した名前で呼ぶ。"""
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
