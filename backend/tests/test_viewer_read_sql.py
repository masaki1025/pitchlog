"""閲覧pageが既readerの照合面を共有し、行ロックだけを除く。"""

from pitchlog.authz.nonplay_prefix_read_sql import (
    candidate_read_function_bodies as nonplay_bodies,
)
from pitchlog.authz.terminal_pitch_write_stamp import (
    candidate_function_bodies as play_bodies,
)
from pitchlog.authz.viewer_read_sql import candidate_viewer_function_bodies


def test_viewer_page_derivation_keeps_every_other_sql_clause() -> None:
    """既writerのFOR SHAREを保ったまま閲覧2関数だけを派生する。"""
    viewer = candidate_viewer_function_bodies()
    assert set(viewer) == {
        "read_viewer_play_prefix_history_page",
        "read_viewer_nonplay_active_history",
    }
    for old, source, locks in (
        ("read_play_prefix_history_page", play_bodies(), 1),
        ("read_nonplay_active_history", nonplay_bodies(), 2),
    ):
        original = source[old]
        assert original.count("FOR SHARE") == locks
        new = "read_viewer_" + old.removeprefix("read_")
        assert viewer[new] == original.replace(
            "sync_right_api." + old + "(",
            "sync_right_api." + new + "(",
            1,
        ).replace("FOR SHARE OF c", "").replace("FOR SHARE", "")
        assert "FOR SHARE" not in viewer[new]
        assert "FOR UPDATE" not in viewer[new]
