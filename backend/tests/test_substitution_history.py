"""既play原本を更新せず、交代だけで文脈差分を説明する。"""

import copy
import json
from pathlib import Path

import pytest

from pitchlog.sync.substitution_history import (
    SubstitutionHistoryError,
    verify_substitution_gaps,
)

CASES = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "contracts/state-transition/nonplay_prefix_bridge_cases_v1.json"
    ).read_text()
)
ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def source():
    """正式採用caseの単一play後を基底にする。"""
    return copy.deepcopy(CASES["steps"][1]["source"])


def substitute_after_play():
    """新eventを既playの後へ置き、既frame全値は維持する。"""
    value = source()
    content = value["checkpoint"]["content"]
    original_frame = copy.deepcopy(value["activeStack"][0])
    after = copy.deepcopy(content["restored"])
    after["lineup"]["home"]["pitcherId"] = ID
    after["substitutionState"] = {"marker": "new-state"}
    content["restored"] = after
    content["substitutionFrames"] = [
        {
            "source": {
                **content["d1Head"]["source"],
                "eventId": ID,
                "d1": "2",
                "eventKind": "substitution",
            },
            "afterPlayId": original_frame["play"]["playId"],
            "beforeContext": copy.deepcopy(original_frame["afterContext"]),
            "afterContext": copy.deepcopy(after),
        }
    ]
    assert value["activeStack"][0] == original_frame
    return value


def test_legacy_chain_and_substitution_gap():
    """旧連続playと、交代が入る非連続playの両方を受け取る。"""
    verify_substitution_gaps(source())
    verify_substitution_gaps(substitute_after_play())


def test_missing_frame_and_wrong_anchor_rejected():
    """CPだけ更新して原本を置かない操作を拒否する。"""
    value = substitute_after_play()
    value["checkpoint"]["content"]["substitutionFrames"] = []
    with pytest.raises(SubstitutionHistoryError):
        verify_substitution_gaps(value)
    value = substitute_after_play()
    value["checkpoint"]["content"]["substitutionFrames"][0]["afterPlayId"] = ID
    with pytest.raises(SubstitutionHistoryError):
        verify_substitution_gaps(value)


def test_original_play_is_not_rewritten_to_hide_gap():
    """交代frame前文脈を旧play由来から改変したら拒否する。"""
    value = substitute_after_play()
    frame = value["checkpoint"]["content"]["substitutionFrames"][0]
    frame["beforeContext"]["lineup"]["home"]["pitcherId"] = ID
    with pytest.raises(SubstitutionHistoryError):
        verify_substitution_gaps(value)


def test_substitution_and_lifecycle_control_share_one_play_gap():
    """交代後の終了再開を同じplay間のD1順で連結する。"""
    value = substitute_after_play()
    content = value["checkpoint"]["content"]
    frame = content["substitutionFrames"][0]
    before = copy.deepcopy(frame["afterContext"])
    after = copy.deepcopy(before)
    after["current"]["stateFields"]["state.gameEnded"] = True
    control = {
        "source": {
            **frame["source"],
            "eventId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "d1": "3",
            "d5": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            "eventKind": "game_end_declaration",
        },
        "anchorEventId": value["activeStack"][0]["play"]["source"]["eventId"],
        "beforeContext": before,
        "afterContext": after,
    }
    content["restored"] = after
    verify_substitution_gaps(value, [control])

    control["source"]["d1"] = frame["source"]["d1"]
    with pytest.raises(SubstitutionHistoryError):
        verify_substitution_gaps(value, [control])
