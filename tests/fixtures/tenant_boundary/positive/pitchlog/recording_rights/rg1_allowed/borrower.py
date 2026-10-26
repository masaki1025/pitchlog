"""同DB/PIDの借用主体照合だけの正例。"""

import psycopg  # ty: ignore[unresolved-import]
from pitchlog.recording_rights.rg1_lifecycle import (  # ty: ignore[unresolved-import]
    BusinessBinding,
)


def serve_fresh_controller(connection: psycopg.Connection) -> None:
    """正規外側scopeの接続を表す静的試験用の階層。"""

    def assert_borrower_backend(uid: int, local: BusinessBinding) -> None:
        """固定照合SQLの実行だけを表す。"""
        connection.execute("SELECT 1", (uid, local.backend_pid))
