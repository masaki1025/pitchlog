"""実artifactの交代結果からCP候補を作る。DB資格は別検査。"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.host import open_domain_host
from pitchlog.domainrt.lineup_play_prefix_continuation import NonplaySource
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.substitution_projection import (
    SubstitutionProjectionError,
    build_substitution_source,
)

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = json.loads(
    (ROOT / "frontend/src/api/fixtures/nativeUndoProduct.v1.json").read_text()
)["samples"]
METADATA = json.loads(
    (ROOT / "frontend/src/api/fixtures/lineupPrefixGame.v3.json").read_text()
)["value"]
FINGERPRINT = "wire-v1:" + "a" * 64
NEW_PLAYER = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


def candidate():
    """正式hostの2操作を使い、偽DB成功を作らず純候補を取得する。"""
    before = deepcopy(
        next(item for item in SAMPLES if item["index"] == 2)["payload"]["calculation"][
            "request"
        ]["source"]
    )
    restored = before["checkpoint"]["content"]["restored"]
    side = (
        "away" if restored["current"]["stateFields"]["state.half"] == "top" else "home"
    )
    with open_domain_host() as host:
        initial = json.loads(
            host.call(
                "deriveInitialSubstitutionStateV1",
                _canonical_json(
                    {
                        "version": "substitution-initial-state-v1",
                        "roster": METADATA["roster"],
                        "attackingSide": side,
                        "runners": restored["runners"],
                    }
                ),
            )
        )
        assert initial["ok"] is True
        state = initial["value"]
        fielding = state["home" if side == "away" else "away"]
        operation = {
            "kind": "pitcher",
            "side": "home" if side == "away" else "away",
            "outgoingId": fielding["fielding"]["1"],
            "incomingId": NEW_PLAYER,
            "count": {
                "strikes": restored["current"]["stateFields"]["state.count.strikes"],
                "balls": restored["current"]["stateFields"]["state.count.balls"],
            },
            "dh": "retain",
        }
        transition = json.loads(
            host.call(
                "transitionSubstitutionV1",
                _canonical_json(
                    {
                        "version": "substitution-transition-v1",
                        "state": state,
                        "operation": operation,
                        "eligibleIncomingIds": [NEW_PLAYER],
                        "restoreContext": restored,
                    }
                ),
            )
        )
        assert transition["ok"] is True
        payload = {
            "formatVersion": "substitution-event-v1",
            "expectedCheckpoint": before["checkpoint"]["ref"],
            "eventId": "ffffffff-ffff-4fff-8fff-ffffffffffff",
            "operation": operation,
            "incomingSnapshots": [{"playerId": NEW_PLAYER, "uniformNumber": "18"}],
        }
        content = before["checkpoint"]["content"]
        event = SyncEvent(
            "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            content["scope"]["gameId"],
            int(content["d3"]) + 1,
            content["scope"]["generation"],
            "substitution",
            v6=4,
            v7=payload,
        )
        return before, event, transition["value"], host.artifact_sha256


def test_saved_cp_candidate_preserves_play_and_updates_substitution_context():
    """元playのstack/物理番号は動かさず、交代frameとCPだけを前進する。"""
    before, event, transition, _current_artifact = candidate()
    # ここは純形の検査。保存時は実host SHAと旧pinの有限互換資格を別途要求する。
    pinned_artifact = before["checkpoint"]["content"]["executionArtifactSha256"]
    after = build_substitution_source(
        before,
        event,
        fingerprint=FINGERPRINT,
        artifact_sha256=pinned_artifact,
        transition=transition,
    )
    assert after["activeStack"] == before["activeStack"]
    assert (
        after["checkpoint"]["content"]["activeHead"]
        == before["checkpoint"]["content"]["activeHead"]
    )
    assert (
        after["checkpoint"]["content"]["restored"]["participants"]["pitcherId"]
        == NEW_PLAYER
    )
    assert len(after["checkpoint"]["content"]["substitutionFrames"]) == 1
    assert NonplaySource.model_validate_json(
        _canonical_json(after)
    ).checkpoint.ref.revision == str(int(before["checkpoint"]["ref"]["revision"]) + 1)


def test_stale_checkpoint_and_artifact_are_rejected():
    """Wire CPとhost pinの不一致を受理候補に補修しない。"""
    before, event, transition, current_artifact = candidate()
    with pytest.raises(SubstitutionProjectionError):
        build_substitution_source(
            before,
            event,
            fingerprint=FINGERPRINT,
            artifact_sha256=current_artifact,
            transition=transition,
        )
