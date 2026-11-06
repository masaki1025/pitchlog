"""A-2のBF責任と実投球者を、生成T5の出力で別々に対向する。"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from pitchlog.stats.facts import evaluate_native_projection

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "docs/features/mvp-stats-primitives/primitive-cases.candidate.json"
CURRENT = "00000000-0000-0000-0000-000000000004"
PREVIOUS = "00000000-0000-0000-0000-000000000005"
BATTER = "00000000-0000-0000-0000-000000000003"
EVENT = UUID("00000000-0000-0000-0000-0000000007d1")


def _flags(case_id: str) -> dict:
    cases = json.loads(SOURCE.read_text())["cases"]
    return next(row for row in cases if row["case_id"] == case_id)["input"][
        "events"
    ][0]["stat_flags"]


def _payload(
    flags: dict,
    *,
    changed: bool,
    owner: str | None,
    balls: str = "3",
    strikes: str = "1",
) -> dict:
    people = {
        "pitcherId": CURRENT,
        "batterId": BATTER,
        "catcherId": "00000000-0000-0000-0000-000000000001",
        "battingOrder": "1",
    }
    proof = {
        "kind": "changed-mid-plate-appearance" if changed else "no-change",
        "paStartSource": {
            "kind": "started-game",
            "id": "00000000-0000-0000-0000-000000000002",
        },
        "previousPitcherId": PREVIOUS if changed else None,
        "strikesAtChange": strikes if changed else None,
        "ballsAtChange": balls if changed else None,
    }
    runners = []
    if owner is not None:
        runners.append({"runnerId": BATTER, "responsiblePitcherId": owner})
    return {
        "formatVersion": "play-prefix-play-v3",
        "participants": people,
        "calculation": {
            "formatVersion": "play-prefix-calculation-v3",
            "request": {
                "t1": {
                    "pitchEventKind": "pitch-event",
                    "before": {
                        "stateFields": {"state.inning": "1", "state.half": "top"}
                    },
                },
                "source": {"responsibility": proof},
            },
            "response": {
                "ok": True,
                "value": {
                    "t1": {
                        "statFlags": flags,
                        "plateAppearanceEnded": True,
                        "outEffect": {"count": "0"},
                    },
                    "beforeParticipants": people,
                    "responsibility": proof,
                    "runners": runners,
                },
            },
        },
    }


def _metric(result: dict, name: str) -> dict:
    return result["metrics"][name]


@pytest.mark.parametrize(
    "case_id,changed,owner,balls,strikes,expected",
    [
        ("walk", True, PREVIOUS, "3", "1", PREVIOUS),  # A-2: 3-1
        ("walk", True, CURRENT, "1", "2", CURRENT),  # A-2: 他7count
        ("intentional-walk", True, PREVIOUS, "3", "1", PREVIOUS),
        ("strikeout-out", True, None, "0", "2", CURRENT),
        ("walk", False, CURRENT, "0", "0", CURRENT),
    ],
)
def test_bf_credit_follows_saved_responsibility_and_pitch_count_stays_current(
    case_id: str,
    changed: bool,
    owner: str | None,
    balls: str,
    strikes: str,
    expected: str,
) -> None:
    """BFの1件帰属をA-2の手定期待で検査し、球数の実投手を動かさない。"""
    result = evaluate_native_projection(
        _payload(
            _flags(case_id),
            changed=changed,
            owner=owner,
            balls=balls,
            strikes=strikes,
        ),
        source_event_id=EVENT,
    )
    bf = _metric(result, "batters_faced")
    assert bf["state"] == "available"
    assert bf["value"] == "1"
    assert bf["credits"] == [{"player_id": expected, "quantity": "1"}]
    pitch = _metric(result, "pitch_count")
    if case_id == "intentional-walk":
        assert pitch["credits"] == []
        assert pitch["value"] == "0"
    else:
        assert pitch["credits"] == [{"player_id": CURRENT, "quantity": "1"}]


def test_changed_walk_without_saved_batter_responsibility_is_not_zero() -> None:
    """欠けた走者責任を現在投手へ仮補完しない。"""
    result = evaluate_native_projection(
        _payload(_flags("walk"), changed=True, owner=None), source_event_id=EVENT
    )
    assert _metric(result, "batters_faced")["state"] == "source_unavailable"
    assert _metric(result, "batters_faced")["value"] is None
    assert _metric(result, "pitcher_bb")["state"] == "source_unavailable"
