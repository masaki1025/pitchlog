"""段階起動DB APIの限定許可正例。"""

import psycopg  # ty: ignore


class StageAStartupResult:
    """fixtureの戻り型。"""


class stage_a_startup:
    """製品モジュールの許可シンボルを表す。"""

    @staticmethod
    def advance_stage_a_from_s0(*, owner_dsn: str, applicator_dsn: str) -> StageAStartupResult:
        """登録済みのDB APIだけを使用する。"""
        psycopg.connect(owner_dsn)
        return StageAStartupResult()
