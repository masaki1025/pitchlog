"""段階起動DB APIの限定許可正例。"""

import psycopg  # ty: ignore


class StageAStartupResult:
    """fixtureの戻り型。"""


class stage_a_startup:
    """製品モジュールの許可シンボルを表す。"""

    @staticmethod
    def resume_stage_a_after_placement(
        *, owner_dsn: str, applicator_dsn: str
    ) -> StageAStartupResult:
        """登録済みのDB APIだけを使用する。"""
        with psycopg.connect(owner_dsn) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return StageAStartupResult()
