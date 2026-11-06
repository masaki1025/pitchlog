"""閲覧pageが既readerの照合面を共有し、行ロックだけを除く。"""

from pitchlog.authz import product_catalog
from pitchlog.authz.nonplay_prefix_read_sql import (
    candidate_read_function_bodies as nonplay_bodies,
)
from pitchlog.authz.terminal_pitch_write_stamp import (
    candidate_function_bodies as play_bodies,
)
from pitchlog.authz.viewer_read_sql import candidate_viewer_function_bodies
from pitchlog.repositories.viewer_read import VIEWER_READ_OPERATIONS


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


def test_viewer_functions_are_in_publisher_and_catalog_detail_scope() -> None:
    """正式宣言2本と実catalog本文照合schemaが同じ境界を指す。"""
    from pitchlog.authz.first_ball_product import ADDITIONS

    names = {
        row["function_name"]
        for row in ADDITIONS["functions"]
        if row["function_name"].startswith("read_viewer_")
    }
    assert names == set(candidate_viewer_function_bodies())
    assert "'sync_right_api'" in product_catalog._LIFECYCLE_FUNCTION_DETAILS_QUERY
    assert {entry.function_id for entry in VIEWER_READ_OPERATIONS} == {
        f"sync_right_api.{name}" for name in names
    }
