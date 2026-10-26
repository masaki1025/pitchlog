"""controller内部の固定制御SQLだけの正例。"""

import psycopg  # ty: ignore[unresolved-import]


def serve_fresh_controller(connection: psycopg.Connection) -> None:
    """正規外側scopeの接続を表す静的試験用の階層。"""

    def control(name: str) -> object:
        """固定制御文の実行だけを表す。"""
        return connection.execute(
            "SELECT rg1_control.controller_lease_alive()"
        ).fetchone()
