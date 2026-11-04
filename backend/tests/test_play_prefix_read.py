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


def test_lineup_zero_dto_is_separate_and_cannot_issue_recorded_or_writer_values():
    """v3初期の両cursor/名簿を保ち、未保存head/秘密/余剰を拒否する。"""
    import copy
    import json

    from pydantic import ValidationError
    from test_ordinary_prefix_dto import POSITIVES
    from test_play_prefix import _lineup_initial_from_fixture

    from pitchlog.api.schemas.started_games import (
        StartedGameRead,
        StartedLineupPrefixGameRead,
    )
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.domainrt.lineup_play_prefix_continuation import SourcePosition
    from pitchlog.repositories.play_prefix import _initial_lineup_document
    from pitchlog.sync.d4_reference import encode_d4_reference

    initial, _ = _lineup_initial_from_fixture()
    d4 = encode_d4_reference(initial.tenant_id, initial.game_id, initial.generation)
    with open_domain_host() as host:
        doc, _ = _initial_lineup_document(
            initial,
            str(UUID(int=9001)),
            d4,
            1,
            host.artifact_sha256,
            SourcePosition(d1="1", d2="1", appliedWatermark="0"),
        )
    original = POSITIVES[0]["value"]
    raw = {k: copy.deepcopy(original[k]) for k in StartedGameRead.model_fields}
    raw.update(
        read_kind="lineup-prefix",
        id=str(initial.game_id),
        current_d4=d4,
        after=doc.after.model_dump(mode="json", by_alias=True),
        state=initial.before.model_dump(mode="json", by_alias=True),
        prefix_ref=doc.prefix_ref.model_dump(mode="json", by_alias=True),
        rules=doc.rules.model_dump(mode="json", by_alias=True),
        t2=None,
        last_entry=None,
        last_source=None,
        prior_artifact_sha256=doc.artifact_sha256,
        pa_start_source=doc.pa_start_source.model_dump(mode="json", by_alias=True),
        lineup=doc.lineup.model_dump(mode="json", by_alias=True),
        roster_digest=doc.roster_digest,
        runners=[],
        participants=doc.participants.model_dump(mode="json", by_alias=True),
        next_position={"d1": "1", "d2": "1"},
        checkpoint_anchor=None,
        storage_anchor=None,
        recovery_generation="1",
        page={"items": [], "next_cursor": None},
        append_policy={
            "version": "ordinary-append-v1",
            "first_d2": "1",
            "d2_gap": "1000",
            "max_d2": "9007199254740991",
        },
        last_saved_at="2026-10-31T00:00:00Z",
    )
    value = StartedLineupPrefixGameRead.model_validate_json(json.dumps(raw))
    assert json.loads(value.model_dump_json(by_alias=True, exclude_unset=True)) == raw
    for key, bad in [
        ("credential", "secret"),
        ("prefix_ref", None),
        ("participants", None),
        ("next_position", {"d1": "0", "d2": "1"}),
        (
            "checkpoint_anchor",
            {"id": str(UUID(int=9)), "revision": "1", "history_version": "1"},
        ),
        ("storage_anchor", {"id": str(UUID(int=9)), "history_epoch": "1"}),
        (
            "last_source",
            {
                "eventId": str(UUID(int=9)),
                "d5": str(UUID(int=10)),
                "playId": str(UUID(int=11)),
            },
        ),
    ]:
        changed = copy.deepcopy(raw)
        changed[key] = bad
        with pytest.raises((ValidationError, ValueError)):
            StartedLineupPrefixGameRead.model_validate_json(json.dumps(changed))
