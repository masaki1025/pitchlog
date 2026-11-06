"""既有限履歴readerからRR READ ONLY専用の非ロック本文を派生する。"""

from pitchlog.authz.nonplay_prefix_read_sql import (
    candidate_read_function_bodies as nonplay_bodies,
)
from pitchlog.authz.terminal_pitch_write_stamp import (
    candidate_function_bodies as play_bodies,
)


def candidate_viewer_function_bodies() -> dict[str, str]:
    """既readerのanchor・保存証拠・上限を共有し、行ロックだけを除く。"""
    source = (
        ("read_play_prefix_history_page", play_bodies(), 1),
        ("read_nonplay_active_history", nonplay_bodies(), 2),
    )
    result = {}
    for old, bodies, expected_locks in source:
        sql = bodies[old]
        if sql.count("FOR SHARE") != expected_locks or "FOR UPDATE" in sql:
            raise ValueError("閲覧関数の元SQLが変更されました")
        new = "read_viewer_" + old.removeprefix("read_")
        if sql.count("sync_right_api." + old + "(") != 1:
            raise ValueError("閲覧関数の元宣言が変更されました")
        result[new] = sql.replace(
            "sync_right_api." + old + "(", "sync_right_api." + new + "(", 1
        ).replace("FOR SHARE OF c", "").replace("FOR SHARE", "")
    return result
