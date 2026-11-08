"""真正P3検証後の閲覧有界頁選択だけを検査する。"""

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from pitchlog.repositories import ordinary_prefix_read as reader
from pitchlog.repositories.past_correction_current_paged import VerifiedP3PagedCurrent
from pitchlog.repositories.play_prefix import LineupPrefixDocument
from pitchlog.sync.first_ball_payload import FirstBallObservations
from pitchlog.sync.terminal_pitch_payload import LineupPitchPlayPayload


def _verified(after: int, count: int, limit: int, *, stable: tuple):
    """SQL資格を偽装せず、頁選択関数へ渡す検証済み型の形を作る。"""
    tenant, game, capsule, checkpoint_id = stable
    prefix = SimpleNamespace(
        tenant_id=str(tenant),
        game_id=str(game),
        model_dump=lambda **_: {"id": "head", "length": str(count)},
    )
    doc = SimpleNamespace(
        prefix_ref=prefix,
        confirmed_watermark=str(count),
        recovery_generation="1",
        after="after",
        rules="rules",
        t2="t2",
        artifact_sha256="a" * 64,
        pa_start_source="source",
        lineup="lineup",
        roster_digest="b" * 64,
        runners=[],
        participants="participants",
        id=str(checkpoint_id),
        revision="1",
        history_version="1",
        storage_anchor="anchor",
    )
    response = SimpleNamespace(
        value=SimpleNamespace(new_history_entry="last", play_identity="last")
    )
    payload = SimpleNamespace(
        observations=FirstBallObservations.model_validate(
            {
                "pitchTypeKey": "pitch-type.straight",
                "course": {"unit": "1/263", "x": "131", "y": "132"},
                "pitchSpeed": {"kmh": None, "outsideRangeConfirmed": False},
                "stance": None,
                "battingSide": None,
            }
        ),
        calculation=SimpleNamespace(response=response),
    )
    selected: tuple[dict[str, Any], ...] = tuple(
        {
            "play_row": {"d1": d1},
            "history_entry": {"d1": d1},
            "play_runners": [],
        }
        for d1 in range(after + 1, after + limit + 1)
    )
    verified = VerifiedP3PagedCurrent(
        # 頁投影だけの合成形。実CP/SQL資格の成立を示すものではない。
        checkpoint=cast(LineupPrefixDocument, doc),
        original_checkpoint=cast(LineupPrefixDocument, doc),
        capsule_id=capsule,
        change_event_id=uuid4(),
        d5=uuid4(),
        target_d1=1,
        stats_version_id=uuid4(),
        watermark=count,
        source_count=count,
        selected_after_d1=after,
        selected_items=selected,
        selected_payloads=(cast(LineupPitchPlayPayload, payload),) * limit,
        target_item=selected[0],
        last_item=selected[-1],
        last_payload=cast(LineupPitchPlayPayload, payload),
    )
    return verified


def test_p3_viewer_latest_25_then_older_one(monkeypatch) -> None:
    """26件でも全部を表示用RAMへ戻さず、scope付きcursorで旧頁を取得する。"""
    monkeypatch.setattr(reader, "_public_play", lambda row, _: row)
    stable = (uuid4(), uuid4(), uuid4(), uuid4())
    first = reader._read_p3_lineup_projection(
        _verified(1, 26, 25, stable=stable),
        "meta",
        {},
        {"saved_at": "saved"},
        limit=25,
        cursor=None,
        viewer=True,
    )
    numbers = [item["play_row"]["d1"] for item in first.projection["page"]["items"]]
    assert numbers == list(range(26, 1, -1))
    cursor = first.projection["page"]["next_cursor"]
    assert type(cursor) is str
    second = reader._read_p3_lineup_projection(
        _verified(0, 26, 1, stable=stable),
        "meta",
        {},
        {"saved_at": "saved"},
        limit=25,
        cursor=cursor,
        viewer=True,
    )
    numbers = [item["play_row"]["d1"] for item in second.projection["page"]["items"]]
    assert numbers == [1]
    assert second.projection["page"]["next_cursor"] is None
    with pytest.raises(reader.OrdinaryPrefixError):
        reader._read_p3_lineup_projection(
            _verified(0, 26, 1, stable=(uuid4(), *stable[1:])),
            "meta",
            {},
            {"saved_at": "saved"},
            limit=25,
            cursor=cursor,
            viewer=True,
        )
