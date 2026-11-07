"""閲覧point関数と現行RR readerの有限境界を検査する。"""

from uuid import UUID

from pitchlog.authz.started_snapshot_read_product import candidate_declarations
from pitchlog.authz.viewer_effective_sql import candidate_viewer_effective_body
from pitchlog.repositories.started_snapshot_read_operations import (
    STARTED_SNAPSHOT_READ_OPERATIONS,
)
from pitchlog.repositories.viewer_read import (
    VIEWER_READ_OPERATIONS,
    ViewerEffectiveVersionReadToken,
)


def test_current_started_readers_already_supply_all_viewer_pages() -> None:
    """閲覧用page SQLを重ねず、現行RR専用3関数を使う。"""
    names = {entry.function_id for entry in STARTED_SNAPSHOT_READ_OPERATIONS}
    assert names == {
        "sync_right_api.read_started_ordinary_history_page",
        "sync_right_api.read_started_play_prefix_history_page",
        "sync_right_api.read_started_nonplay_active_history",
    }
    assert callable(candidate_declarations)


def test_one_viewer_point_is_closed_and_sql_requires_rr_ro() -> None:
    """pointだけを追加し、writer scope/公開実行をSQLでも拒否する。"""
    (point,) = VIEWER_READ_OPERATIONS
    assert point.token_type is ViewerEffectiveVersionReadToken
    assert point.function_id == "sync_right_api.read_viewer_effective_version"
    assert point.input_fields == (("game_id", UUID), ("generation", int))
    assert point.result_fields == (("record_json", str),)
    assert (point.min_rows, point.max_rows) == (1, 1)
    body = candidate_viewer_effective_body()
    assert (
        body.count("CREATE FUNCTION sync_right_api.read_viewer_effective_version(")
        == 1
    )
    assert "transaction_isolation" in body
    assert "transaction_read_only" in body
    assert "FOR UPDATE" not in body and "FOR SHARE" not in body
    assert body.count("LEFT JOIN") == 3
    assert body.count("REVOKE ALL ON FUNCTION") == 1
    assert body.count("GRANT EXECUTE ON FUNCTION") == 1
    assert "TO pitchlog_app" in body
