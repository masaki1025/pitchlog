"""閲覧pageが既readerの照合面を共有し、行ロックだけを除く。"""

from pathlib import Path
from uuid import UUID

import pytest

from pitchlog.authz import product_catalog
from pitchlog.authz.nonplay_prefix_read_sql import (
    candidate_read_function_bodies as nonplay_bodies,
)
from pitchlog.authz.terminal_pitch_write_stamp import (
    candidate_function_bodies as play_bodies,
)
from pitchlog.authz.viewer_read_sql import candidate_viewer_function_bodies
from pitchlog.repositories.ordinary_prefix_read import (
    OrdinaryPrefixError,
    _assert_viewer_page_edges,
)
from pitchlog.repositories.viewer_read import VIEWER_READ_OPERATIONS


def test_viewer_page_derivation_keeps_every_other_sql_clause() -> None:
    """既writerのFOR SHAREを保ったまま閲覧2関数だけを派生する。"""
    viewer = candidate_viewer_function_bodies()
    assert set(viewer) == {
        "read_viewer_play_prefix_history_page",
        "read_viewer_nonplay_active_history",
    }
    for old, source, locks, descending in (
        ("read_play_prefix_history_page", play_bodies(), 1, True),
        ("read_nonplay_active_history", nonplay_bodies(), 2, False),
    ):
        original = source[old]
        assert original.count("FOR SHARE") == locks
        new = "read_viewer_" + old.removeprefix("read_")
        expected = (
            original.replace(
                "sync_right_api." + old + "(",
                "sync_right_api." + new + "(",
                1,
            )
            .replace("FOR SHARE OF c", "")
            .replace("FOR SHARE", "")
        )
        if descending:
            expected = expected.replace(
                "AND (x.d1,x.d2,x.source_event_id)>(p_after_d1,p_after_d2,p_after_id)",
                "AND (p_after_d1=0 OR (x.d1,x.d2,x.source_event_id)<="
                "(p_after_d1,p_after_d2,p_after_id))",
                1,
            ).replace(
                "ORDER BY x.d1,x.d2,x.source_event_id LIMIT p_page_size+1",
                "ORDER BY x.d1 DESC,x.d2 DESC,x.source_event_id DESC "
                "LIMIT p_page_size+1",
                1,
            )
            expected = (
                expected.replace("next_d1:=p_after_d1;", "next_d1:=0;", 1)
                .replace(
                    " IF (item.history->>'d1')::bigint-next_d1<>1",
                    " IF next_d1=0 THEN "
                    "next_d1:=(item.history->>'d1')::bigint-1; END IF;\n"
                    " IF (item.history->>'d1')::bigint-next_d1<>1",
                    1,
                )
                .replace(
                    " IF seen_count<=p_page_size AND "
                    "next_d1<>p_upper_watermark THEN\n"
                    " RAISE EXCEPTION 'ordinary prefix history tail rejected' "
                    "USING ERRCODE='42501';\n"
                    " END IF;",
                    "",
                    1,
                )
            )
        assert viewer[new] == expected
        assert "FOR SHARE" not in viewer[new]
        assert "FOR UPDATE" not in viewer[new]


def test_shared_authz_catalog_patch_declares_viewer_functions() -> None:
    """共有認可catalogは直接編集せず、接合patchの宣言と実登録が一致する。"""
    patch = (
        Path(__file__).parents[2]
        / "docs/features/mvp-viewer-live-connection/patches/shared-integration.patch"
    )
    assert patch.is_file(), "共有認可catalogへの接合patchがありません"
    text = patch.read_text(encoding="utf-8")
    names = set(candidate_viewer_function_bodies())
    assert {entry.function_id for entry in VIEWER_READ_OPERATIONS} == {
        f"sync_right_api.{name}" for name in names
    }
    for name in names:
        assert f"FUNCTION:sync_right_api:{name}(" in text
        assert f"function-bodies/functions/FUNCTION:sync_right_api:{name}(" in text
    for required in (
        "game_viewer_head",
        "game_viewer_saved",
        "backend/tests/test_api_app.py",
        "backend/tests/test_api_conventions.py",
        "CAP:sync_play_prefix:read_viewer_play_prefix_history_page",
        "CAP:sync_ordinary_pitch:read_viewer_nonplay_active_history",
        "SYNC_PLAY_PREFIX:read_viewer_play_prefix_history_page",
        "SYNC_ORDINARY_PITCH:read_viewer_nonplay_active_history",
        "frontend/src/router.ts",
        "GameScreenEntryNavigation.ts",
    ):
        assert required in text, required
    assert "'sync_right_api'" in product_catalog._LIFECYCLE_FUNCTION_DETAILS_QUERY


def test_viewer_page_edges_fail_closed_on_missing_history() -> None:
    """最新端・先頭端・空pageの欠落を成功にしない。"""
    zero = (0, 0, UUID(int=0))
    positions = [(value, 0, UUID(int=0)) for value in range(1, 27)]
    _assert_viewer_page_edges(zero, positions, 26, has_next=True)
    _assert_viewer_page_edges((1, 0, UUID(int=0)), positions[:1], 26, has_next=False)
    for point, page, has_next in (
        (zero, [], True),
        (zero, positions[:-1], False),
        ((1, 0, UUID(int=0)), [(2, 0, UUID(int=0))], False),
    ):
        with pytest.raises(OrdinaryPrefixError):
            _assert_viewer_page_edges(point, page, 26, has_next=has_next)
