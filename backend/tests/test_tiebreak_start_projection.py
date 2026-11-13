"""タイブレーク開始の保存候補を、実artifactと閉じたCP相関で検査する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.host import open_domain_host
from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.tiebreak_start_projection import (
    TiebreakStartProjectionError,
    build_tiebreak_start_source,
)

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _ROOT / "frontend/src/api/fixtures/nativeUndoProduct.current.v1.json"
_RULE = {
    "startInning": "10",
    "runnerPlacement": "no_out_first_second",
    "leadoffRule": "continue_lineup",
}


def _source():
    """既存fixtureを開始CPへ縮め、10回・無走者の規則適合状態にする。"""
    sample = json.loads(_FIXTURE.read_text(encoding="utf-8"))["samples"][0]
    before = copy.deepcopy(sample["payload"]["calculation"]["request"]["source"])
    cp = before["checkpoint"]
    content = cp["content"]
    restored = content["restored"]
    before["activeStack"] = []
    content.update(
        activeHead=None,
        activeDepth="0",
        d3="0",
        d1Head=None,
        historyVersion="0",
    )
    content["projectionHead"] = {
        "kind": "started-game",
        "eventId": content["origin"]["eventId"],
    }
    fields = restored["current"]["stateFields"]
    fields.update(
        {
            "state.inning": "10",
            "state.battingOrder": "4",
            "state.count.balls": "0",
        }
    )
    restored["participants"]["battingOrder"] = "4"
    restored["rules"]["tiebreak"] = copy.deepcopy(_RULE)
    side = "away" if fields["state.half"] == "top" else "home"
    order = restored["lineup"][side]["battingOrder"]
    active = [order[str(slot)] for slot in range(1, 10)]
    batter = order["4"]
    restored["participants"]["batterId"] = batter
    runners = [player for player in active if player != batter]
    return before, active, batter, restored["participants"]["pitcherId"], runners


def _payload(cp, first, second, *, leadoff="4", inning="10"):
    """保存eventの閉じたV7を作る。"""
    return {
        "formatVersion": "tiebreak-start-event-v1",
        "expectedCheckpoint": {
            "id": cp["ref"]["id"],
            "revision": str(cp["ref"]["revision"]),
            "digest": cp["ref"]["digest"],
        },
        "eventId": "00000000-0000-4000-8000-000000000502",
        "runnerPlacement": "first-second",
        "leadoffBatter": leadoff,
        "inning": inning,
        "firstRunnerId": first,
        "secondRunnerId": second,
    }


def _event(content, payload):
    """同一CP直後のD1 eventを作る。"""
    return SyncEvent(
        d5="00000000-0000-4000-8000-000000000501",
        game_id=content["scope"]["gameId"],
        d1=int(content["d3"]) + 1,
        d4=content["scope"]["generation"],
        v5="tiebreak_start",
        v7=payload,
    )


def _artifact(host, restored, first, second, active):
    """唯一artifactへ実選手IDだけを渡す。"""
    request = {
        "version": "tiebreak-start-v1",
        "restoreContext": restored,
        "rule": _RULE,
        "selection": {"firstRunnerId": first, "secondRunnerId": second},
        "activePlayerIds": active,
    }
    return json.loads(host.call("transitionTiebreakStartV1", _canonical_json(request)))


def test_build_tiebreak_start_source_preserves_responsibility_and_appends_frame():
    """配置走者の責任投手を半回開始投手へ固定し、CPを一回だけ進める。"""
    before, active, _batter, pitcher, runners = _source()
    cp = before["checkpoint"]
    content = cp["content"]
    with open_domain_host() as host:
        content["executionArtifactSha256"] = host.artifact_sha256
        cp["ref"]["digest"] = source_fingerprint(content)
        payload = _payload(cp, runners[0], runners[1])
        result = _artifact(host, content["restored"], runners[0], runners[1], active)
        assert result["ok"] is True
        after = build_tiebreak_start_source(
            before,
            _event(content, payload),
            fingerprint="wire-v1:" + "a" * 64,
            artifact_sha256=host.artifact_sha256,
            transition=result["value"],
        )
    after_content = after["checkpoint"]["content"]
    assert len(after_content["tiebreakFrames"]) == 1
    assert after_content["restored"]["current"]["stateFields"]["state.runners"] == (
        "first-second"
    )
    assert after_content["restored"]["runners"][0]["responsiblePitcherId"] == pitcher
    assert after_content["restored"]["runners"][1]["responsiblePitcherId"] == pitcher
    assert after_content["historyVersion"] == "1"
    assert after["checkpoint"]["ref"]["digest"] == source_fingerprint(after_content)


@pytest.mark.parametrize(
    "field,value",
    [("leadoffBatter", "5"), ("inning", "11"), ("runnerPlacement", "second-third")],
)
def test_projection_rejects_payload_that_differs_from_saved_state(field, value):
    """保存状態と異なる先頭打者・回・配置をCP候補にしない。"""
    before, active, _batter, _pitcher, runners = _source()
    cp = before["checkpoint"]
    content = cp["content"]
    with open_domain_host() as host:
        content["executionArtifactSha256"] = host.artifact_sha256
        cp["ref"]["digest"] = source_fingerprint(content)
        payload = _payload(cp, runners[0], runners[1])
        payload[field] = value
        result = _artifact(host, content["restored"], runners[0], runners[1], active)
        with pytest.raises(TiebreakStartProjectionError):
            build_tiebreak_start_source(
                before,
                _event(content, payload),
                fingerprint="wire-v1:" + "a" * 64,
                artifact_sha256=host.artifact_sha256,
                transition=result["value"],
            )


def test_artifact_rejects_ineligible_or_duplicate_runner():
    """出場外・先頭打者・重複の走者を配置しない。"""
    before, active, batter, _pitcher, runners = _source()
    cp = before["checkpoint"]
    content = cp["content"]
    with open_domain_host() as host:
        content["executionArtifactSha256"] = host.artifact_sha256
        cp["ref"]["digest"] = source_fingerprint(content)
        duplicate = _artifact(host, content["restored"], runners[0], runners[0], active)
        outside = _artifact(host, content["restored"], batter, runners[0], active)
    assert duplicate["ok"] is False
    assert outside["ok"] is False
