"""禁止された DB 接続 import を持つ合成ポート。"""

from pitchlog.db.engine import create_database_engine


class EngineProjection:
    """独立接続を開ける形の不正な投影ポート。"""

    def apply(self) -> None:
        """検査に拒否されるため、実行されない。"""
        create_database_engine()
