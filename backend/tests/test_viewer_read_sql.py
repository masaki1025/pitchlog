"""閲覧pageが既readerの照合面を共有し、行ロックだけを除く。"""

from pathlib import Path

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
        "ライブ閲覧へ",
    ):
        assert required in text, required
    assert "'sync_right_api'" in product_catalog._LIFECYCLE_FUNCTION_DETAILS_QUERY
