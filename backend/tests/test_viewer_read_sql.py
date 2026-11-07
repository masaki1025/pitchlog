"""閲覧point関数と現行RR readerの有限境界を検査する。"""

from copy import deepcopy
from uuid import UUID, uuid4

import pytest

from pitchlog.authz.first_ball_product import ADDITIONS
from pitchlog.authz.started_snapshot_read_product import candidate_declarations
from pitchlog.authz.viewer_effective_sql import candidate_viewer_effective_body
from pitchlog.authz.viewer_page_sql import candidate_viewer_page_body
from pitchlog.authz.viewer_product import candidate_declarations as viewer_declarations
from pitchlog.repositories.started_snapshot_read_operations import (
    STARTED_SNAPSHOT_READ_OPERATIONS,
)
from pitchlog.repositories.viewer_read import (
    VIEWER_READ_OPERATIONS,
    ViewerEffectiveVersionReadToken,
    ViewerPlayPrefixHistoryPageToken,
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
    page, point = VIEWER_READ_OPERATIONS
    assert page.token_type is ViewerPlayPrefixHistoryPageToken
    assert (page.min_rows, page.max_rows) == (0, 26)
    for size in (25, 26):
        args = (uuid4(), 1, 1, uuid4(), 1, 1, 1, 0, 0, uuid4(), size)
        if size == 25:
            assert ViewerPlayPrefixHistoryPageToken(*args).page_size == 25
        else:
            with pytest.raises(ValueError):
                ViewerPlayPrefixHistoryPageToken(*args)
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


def test_viewer_page_is_bounded_descending_current_reader() -> None:
    """元started全値条件を保持し、必要なv3降順関数だけを派生する。"""
    body = candidate_viewer_page_body()
    assert "p_page_size>25" in body
    assert body.count("read_viewer_play_prefix_history_page(") == 4
    assert (
        "ORDER BY x.d1 DESC,x.d2 DESC,x.source_event_id DESC LIMIT p_page_size+1"
        in body
    )
    assert "ORDER BY h.d1 DESC,h.d2 DESC,h.source_event_id DESC" in body
    assert "next_d1-(item.history->>'d1')::bigint<>1" in body
    assert "next_d1<>1 THEN" in body
    assert "FOR SHARE" not in body and "FOR UPDATE" not in body
    assert "transaction_read_only" in body


def test_two_viewer_declarations_preserve_owner_acl_and_reject_collision() -> None:
    """元registered関数のowner/ACL全値を固定し未知既宣言を受け入れない。"""
    original = [
        row
        for row in ADDITIONS["functions"]
        if row["function_name"]
        not in {
            "read_viewer_play_prefix_history_page",
            "read_viewer_effective_version",
        }
    ]
    rows, bodies = viewer_declarations(original)
    assert [row["function_name"] for row in rows] == [
        "read_viewer_play_prefix_history_page",
        "read_viewer_effective_version",
    ]
    assert set(bodies) == {"function|" + row["function_id"] for row in rows}
    integrated = [
        row
        for row in ADDITIONS["functions"]
        if row["function_name"]
        in {
            "read_viewer_play_prefix_history_page",
            "read_viewer_effective_version",
        }
    ]
    if integrated:
        assert integrated == rows
    for row in rows:
        assert row["owner_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["acl_expectations"] == [
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False}
        ]
        assert row["revoked_acl_expectations"] == [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
        ]
    with pytest.raises(ValueError):
        viewer_declarations([*original, deepcopy(rows[0])])
