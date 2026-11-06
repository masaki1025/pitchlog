"""交代後の次球を保存payloadから再読して文脈を閉じる。"""

from copy import deepcopy

import pytest
from test_substitution_projection import candidate

from pitchlog.repositories.nonplay_prefix import (
    NonplaySourceUnavailable,
    _advance_substitution_after_pitch,
    _stored_contexts,
)


def _saved_pitch():
    """交代の実artifact遷移を元に、次球の保存payloadだけを構成する。"""
    _source, _event, transition, artifact = candidate()
    restored = deepcopy(transition["afterContext"])
    after_state = deepcopy(restored["current"])
    before_balls = int(after_state["stateFields"]["state.count.balls"])
    after_state["stateFields"]["state.count.balls"] = str(before_balls + 1)
    value = {
        "t1": {"after": after_state, "plateAppearanceEnded": False},
        "rosterDigest": restored["rosterDigest"],
        "lineup": restored["lineup"],
        "participants": restored["participants"],
        "runners": restored["runners"],
        "nextResponsibility": restored["responsibility"],
        "t2": restored["lastPlayEvaluation"],
    }
    payload = {
        "formatVersion": "play-prefix-play-v3",
        "calculation": {
            "formatVersion": "nonplay-prefix-calculation-v1",
            "artifactSha256": artifact,
            "request": {
                "source": {
                    "formatVersion": "nonplay-prefix-source-v1",
                    "checkpoint": {"content": {"restored": restored}},
                }
            },
            "response": {"value": value},
        },
    }
    return restored, value, payload, artifact


def test_saved_pitch_context_keeps_substitution_and_matches_unique_artifact():
    """Play frameの前後双方が交代配置を保持し、再読取評価が一致する。"""
    restored, value, payload, artifact = _saved_pitch()
    before, after = _stored_contexts(payload)
    assert before == restored
    assert after["substitutionState"] == _advance_substitution_after_pitch(
        restored, value, artifact
    )
    assert after["substitutionState"]["exitedPlayerIds"] == restored[
        "substitutionState"
    ]["exitedPlayerIds"]
    assert after["current"] == value["t1"]["after"]


def test_saved_pitch_rejects_different_artifact_pin():
    """別artifactへ静かに移行した再読取を拒否する。"""
    restored, value, _payload, _artifact = _saved_pitch()
    with pytest.raises(NonplaySourceUnavailable):
        _advance_substitution_after_pitch(restored, value, "0" * 64)
