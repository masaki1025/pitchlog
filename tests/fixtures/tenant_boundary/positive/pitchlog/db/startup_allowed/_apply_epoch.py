"""段階起動DB APIの限定許可正例。"""

from sqlalchemy import create_engine  # ty: ignore


class stage_a_startup:
    """製品モジュールの許可シンボルを表す。"""

    @staticmethod
    def _apply_epoch(owner_dsn: str) -> None:
        """登録済みのDB APIだけを使用する。"""
        engine = create_engine("postgresql+psycopg://")
        with engine.begin():
            pass
