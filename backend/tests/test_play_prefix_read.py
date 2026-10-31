"""v2 readのwire/storage分離と有界pageの閉入力を検査する。"""

from uuid import UUID

import pytest

from pitchlog.authz.terminal_pitch_write_stamp import candidate_function_bodies
from pitchlog.repositories.function_operations import (
    build_function_registry,
    prepare_function_operation,
)
from pitchlog.repositories.ordinary_prefix_operations import PLAY_PREFIX_OPERATIONS
from pitchlog.sync.terminal_pitch_tokens import PlayPrefixHistoryPageToken


def test_page_wire_head_and_storage_epoch_have_distinct_binds():
    """物理epochを論理historyVersionへ読み替えず、100+1件だけ取得する。"""
    token = PlayPrefixHistoryPageToken(
        UUID(int=1), 1, 2, UUID(int=3), 4, 5, 6, 0, 0, UUID(int=0), 100
    )
    registry = build_function_registry(PLAY_PREFIX_OPERATIONS, frozenset())
    _, params = prepare_function_operation(token, UUID(int=2), registry)
    assert params["storage_history_epoch"] == 2
    assert params["wire_history_version"] == 5
    sql = candidate_function_bodies()["read_play_prefix_history_page"]
    assert "LIMIT p_page_size+1" in sql
    assert "c.content->'prefix_ref'->>'historyVersion'" in sql
    assert "c.history_version=p_storage_history_epoch" in sql
    for value in (0, 101, True):
        with pytest.raises(ValueError):
            PlayPrefixHistoryPageToken(
                UUID(int=1), 1, 2, UUID(int=3), 4, 5, 6, 0, 0, UUID(int=0), value
            )


def test_readonly_bridge_metadata_has_no_write_qualification_and_closed_shape():
    """初期GETの提案metadataを閉codecへ通し、未成立source/余剰を拒否する。"""
    import copy
    import json

    from pydantic import ValidationError
    from test_ordinary_prefix_dto import POSITIVES

    from pitchlog.api.schemas.started_games import StartedPlayPrefixGameRead

    raw = copy.deepcopy(POSITIVES[0]["value"])
    raw.update(
        read_kind="play-prefix",
        prior_artifact_sha256="a" * 64,
        pa_start_source={"kind": "started-game", "id": raw["id"]},
        last_source=None,
        bridge_checkpoint={
            "id": "10000000-0000-0000-0000-000000000020",
            "revision": "1",
            "digest": "a" * 64,
        },
        storage_anchor=None,
        bridge_origin=None,
        runners=[],
        participants=None,
    )
    value = StartedPlayPrefixGameRead.model_validate_json(json.dumps(raw))
    assert value.model_dump(mode="json", by_alias=True, exclude_unset=True) == raw
    for field in ["bridge_checkpoint", "prior_artifact_sha256", "last_source"]:
        changed = copy.deepcopy(raw)
        del changed[field]
        with pytest.raises(ValidationError):
            StartedPlayPrefixGameRead.model_validate_json(json.dumps(changed))
    changed = {**raw, "write_qualified": True}
    with pytest.raises(ValidationError):
        StartedPlayPrefixGameRead.model_validate_json(json.dumps(changed))


def test_owned_db_witness_script_is_syntax_checked_without_pg():
    """owned実行前のscript破損を検出するだけで、DB成功を代記しない。"""
    from db.test_terminal_pitch_storage import _script

    for result in ("batting-result.walk", "batting-result.hit-by-pitch"):
        compile(_script(result), "terminal-owned-candidate.py", "exec")
