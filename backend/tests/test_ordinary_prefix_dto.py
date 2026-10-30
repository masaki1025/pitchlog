"""固定FE封筒とBEの新prefix応答型を全値で照合する。実GET成功ではない。"""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pitchlog.api.schemas.started_games import StartedRecordedPrefixGameRead

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "frontend/src/api/fixtures/recordedPrefixGame.v1.json"
POSITIVES = json.loads(FIXTURE.read_text())["positive"]


def test_fixed_fixture_identity():
    """他担当の固定版を読み、期待値を製品sourceから生成しない。"""
    assert (
        hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        == "5c0bfa1a21839dace0c5f24a627981bad6387de6cc407d7135694a87b9c9b43e"
    )
    assert [case["id"] for case in POSITIVES] == [
        "prefix-0",
        "prefix-1",
        "prefix-2",
        "legacy-prefix-1",
    ]


@pytest.mark.parametrize("case", POSITIVES, ids=lambda case: case["id"])
def test_all_complete_static_envelopes_match(case):
    """開始0/通常1/保存2/旧1の全key/全null/今回差分を完全比較する。"""
    value = StartedRecordedPrefixGameRead.model_validate_json(json.dumps(case["value"]))
    assert (
        json.loads(value.model_dump_json(by_alias=True, exclude_unset=True))
        == case["value"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "n0-fake-anchor",
        "n2-no-anchor",
        "foreign-game-row",
        "missing-play-field",
        "unknown-key",
        "page101",
        "zero-next",
        "zero-anchor",
        "date-missing",
        "n0-after-change",
        "bad-policy",
    ],
)
def test_invalid_prefix_envelopes_are_rejected(mutation):
    """架空の保存済み根拠・欠落・余剰・不正相関を閉じる。"""
    source = (
        POSITIVES[0]
        if mutation in {"n0-fake-anchor", "n0-after-change"}
        else POSITIVES[2]
    )
    raw = copy.deepcopy(source["value"])
    if mutation == "n0-fake-anchor":
        raw["checkpoint_anchor"] = copy.deepcopy(
            POSITIVES[2]["value"]["checkpoint_anchor"]
        )
    elif mutation == "n2-no-anchor":
        raw["checkpoint_anchor"] = None
    elif mutation == "foreign-game-row":
        raw["page"]["items"][0]["play_row"]["game_id"] = (
            "99999999-0000-4000-8000-000000000001"
        )
    elif mutation == "missing-play-field":
        del raw["page"]["items"][0]["play_row"]["comment"]
    elif mutation == "unknown-key":
        raw["unknown"] = True
    elif mutation == "page101":
        raw["page"]["items"] = [
            copy.deepcopy(raw["page"]["items"][0]) for _ in range(101)
        ]
    elif mutation == "zero-next":
        raw["next_position"]["d1"] = "0"
    elif mutation == "zero-anchor":
        raw["checkpoint_anchor"]["revision"] = "0"
    elif mutation == "date-missing":
        del raw["last_saved_at"]
    elif mutation == "n0-after-change":
        raw["after"]["stateFields"]["state.count.balls"] = "1"
    else:
        raw["append_policy"]["max_d2"] = "9223372036854775807"
    with pytest.raises(ValidationError):
        StartedRecordedPrefixGameRead.model_validate_json(json.dumps(raw))
