"""root配置のcontroller接続と固定読取APIだけの正例。"""

from pathlib import Path

import psycopg  # ty: ignore[unresolved-import]


class rg1_lifecycle:
    """製品モジュールの登録symbolを表す。"""

    @staticmethod
    def serve_fresh_controller(config_path: Path) -> None:
        """固定設定を使う制御接続だけを表す。"""
        with psycopg.connect(
            host="/run/pitchlog-test",
            dbname="pitchlog_test",
            user="pitchlog_rg1_control_actor",
            passfile="/dev/null",
        ) as connection:
            connection.execute("SELECT session_user, current_user").fetchone()
