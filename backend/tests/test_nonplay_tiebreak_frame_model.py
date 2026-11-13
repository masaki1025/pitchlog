"""非play CP閉型がタイブレーク開始frameを保存できることを固定する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pitchlog.domainrt.lineup_play_prefix_continuation import NonplayCheckpoint

_ROOT = Path(__file__).resolve().parents[2]
_CASES = _ROOT / "contracts/state-transition/nonplay_prefix_bridge_cases_v1.json"


def _checkpoint() -> dict[str, object]:
    """既存bridge caseの空CPを複製し、保存済みタイブレークframeだけを足す。"""
    document = json.loads(_CASES.read_text())
    checkpoint = copy.deepcopy(document["steps"][0]["source"]["checkpoint"])
    content = checkpoint["content"]
    restored = content["restored"]
    events = {
        "play_input": "00000000-0000-4000-8000-0000000005e1",
        "substitution": "00000000-0000-4000-8000-0000000005e2",
        "tiebreak_start": "00000000-0000-4000-8000-0000000005e3",
    }
    content["tiebreakFrames"] = [
        {
            "source": {
                "eventId": events["tiebreak_start"],
                "gameId": content["scope"]["gameId"],
                "generation": content["scope"]["generation"],
                "d1": "55",
                "d5": "00000000-0000-4000-8000-0000000000d5",
                "fingerprint": "wire-v1:" + "a" * 64,
                "eventKind": "tiebreak_start",
            },
            "afterPlayId": events["play_input"],
            "beforeContext": restored,
            "afterContext": restored,
        }
    ]
    # 既存の交代frameも同じ閉型で共存できることを同時に確認する。
    content["substitutionFrames"] = [
        {
            "source": {
                "eventId": events["substitution"],
                "gameId": content["scope"]["gameId"],
                "generation": content["scope"]["generation"],
                "d1": "54",
                "d5": "00000000-0000-4000-8000-0000000000d6",
                "fingerprint": "wire-v1:" + "b" * 64,
                "eventKind": "substitution",
            },
            "afterPlayId": events["play_input"],
            "beforeContext": restored,
            "afterContext": restored,
        }
    ]
    return checkpoint


def test_nonplay_checkpoint_accepts_tiebreak_and_substitution_frames():
    """tiebreak_start sourceとtiebreakFramesを余剰扱いせず保存型へ含める。"""
    checkpoint = _checkpoint()
    raw = json.dumps(checkpoint, ensure_ascii=False)
    parsed = NonplayCheckpoint.model_validate_json(raw)
    assert parsed.content.tiebreak_frames is not None
    assert len(parsed.content.tiebreak_frames) == 1
    assert parsed.content.tiebreak_frames[0].source.event_kind == "tiebreak_start"
    assert parsed.content.substitution_frames is not None
    assert (
        parsed.model_dump(mode="json", by_alias=True, exclude_unset=True) == checkpoint
    )


def test_nonplay_checkpoint_rejects_unknown_event_kind_in_frame():
    """未知eventKindをタイブレークframeの互換値へ丸めない。"""
    checkpoint = _checkpoint()
    checkpoint["content"]["tiebreakFrames"][0]["source"]["eventKind"] = "unknown"
    with pytest.raises(ValidationError):
        NonplayCheckpoint.model_validate_json(json.dumps(checkpoint))
