"""初球participantsの単一実装（一意性の拒否）を、呼出側の写像ごと固定する。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from pitchlog.domainrt.initial_game_roster import InitialRosterProjection
from pitchlog.repositories import recorded_snapshot
from pitchlog.sync.first_ball_execution import (
    FirstBallExecutionError,
)
from pitchlog.sync.first_ball_execution import (
    _participants as execution_participants,
)
from pitchlog.sync.first_ball_payload import select_first_ball_participants

ROOT = Path(__file__).resolve().parents[2]
ROSTERS = json.loads(
    (ROOT / "contracts/state-transition/initial_game_roster_cases_v1.json").read_text()
)["cases"]


def _entry(player_id: str, *, batting: str | None, position: str | None) -> Any:
    """選択規則が読む3点だけを持つ射影entry。"""
    return SimpleNamespace(
        player=SimpleNamespace(player_id=player_id),
        batting_slot=(
            SimpleNamespace(kind="slot", slot=batting)
            if batting is not None
            else SimpleNamespace(kind="none")
        ),
        roles=(
            (SimpleNamespace(kind="fielding", position=position),)
            if position is not None
            else ()
        ),
    )


def _roster(away: list[Any], home: list[Any]) -> Any:
    """away/homeのparticipantsだけを持つ射影。"""
    return SimpleNamespace(
        teams=(
            SimpleNamespace(participants=tuple(away)),
            SimpleNamespace(participants=tuple(home)),
        )
    )


def _happy() -> Any:
    """先頭打者1・投手1・捕手2が一意な最小構成。"""
    batter, pitcher, catcher = (str(uuid4()) for _ in range(3))
    away = [_entry(batter, batting="1", position=None)]
    home = [
        _entry(pitcher, batting=None, position="1"),
        _entry(catcher, batting=None, position="2"),
    ]
    return _roster(away, home), (batter, pitcher, catcher)


def test_unique_roles_are_selected_without_calculation() -> None:
    """一意な3役だけを選び、打順は"1"固定で返す。"""
    roster, (batter, pitcher, catcher) = _happy()
    value = select_first_ball_participants(roster)
    assert (
        value.batter_id,
        value.pitcher_id,
        value.catcher_id,
        value.batting_order,
    ) == (batter, pitcher, catcher, "1")


@pytest.mark.parametrize("role", ["batter", "pitcher", "catcher"])
@pytest.mark.parametrize("fault", ["missing", "duplicate"])
def test_non_unique_roles_are_rejected(role: str, fault: str) -> None:
    """0件・2件のいずれでも ValueError とし、推測で1件を選ばない。"""
    roster, _ = _happy()
    away, home = roster.teams
    target = away if role == "batter" else home
    position = None if role == "batter" else ("1" if role == "pitcher" else "2")
    if fault == "missing":
        if role == "batter":
            target.participants[0].batting_slot = SimpleNamespace(kind="none")
        else:
            target.participants[0].roles = ()
    else:
        clone = _entry(str(uuid4()), batting="1", position=position)
        target.participants = (*target.participants, clone)
    with pytest.raises(ValueError):
        select_first_ball_participants(roster)


def test_recorded_reader_maps_non_unique_roles_to_not_available() -> None:
    """記録後readerでは、参加者不成立を閉じた非公開（409）へ写す。"""
    roster, _ = _happy()
    roster.teams[0].participants[0].batting_slot = SimpleNamespace(kind="none")
    with pytest.raises(recorded_snapshot.RecordedSnapshotUnavailable):
        recorded_snapshot._participants(roster)


def test_execution_maps_non_unique_roles_to_its_own_rejection() -> None:
    """同期writer側も、同じ単一実装の拒否を自前の閉じた例外へ写す。"""
    case = next(
        item
        for item in ROSTERS
        if item["expected"]["ok"] is True and item["request"]["dh"] is True
    )
    value = InitialRosterProjection.model_validate_json(
        json.dumps(case["expected"]["value"])
    )
    raw = value.model_dump_json(by_alias=True)
    assert execution_participants(raw).batting_order == "1"
    damaged = value.model_dump(mode="json", by_alias=True)
    away = damaged["teams"][0]["participants"]
    first = next(entry for entry in away if entry["batting_slot"].get("slot") == "1")
    first["batting_slot"] = {"kind": "none"}
    with pytest.raises(FirstBallExecutionError):
        execution_participants(json.dumps(damaged))
