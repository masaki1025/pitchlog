"""実唯一artifactの終了/再開/二追記連結。保存資格は明示doubleでDB証拠ではない。"""

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest
from test_nonplay_normal_payload import fixture_values

from pitchlog.domainrt.host import NodeDomainHost
from pitchlog.sync.idempotency import source_fingerprint

ROOT = Path(__file__).resolve().parents[2]


def ident(n):
    """試験だけの技術予約値。実E1/権利資格には使用しない。"""
    return str(UUID(int=n))


def seal(q):
    """保存adapterの写像を明示doubleで行う。認可/PG成功を意味しない。"""
    cp = q["source"]["checkpoint"]
    cp["ref"]["digest"] = source_fingerprint(cp["content"])
    q["prefixRef"] = copy.deepcopy(cp["ref"])
    q["t1"]["before"] = copy.deepcopy(cp["content"]["restored"]["current"])
    q["sourcePosition"] = {
        "d1": str(int(cp["content"]["d3"]) + 1),
        "d2": str(int(cp["content"]["d3"]) + 1024),
        "appliedWatermark": cp["content"]["d3"],
    }
    q["playIdentity"] = {
        "eventId": ident(900 + int(cp["content"]["d3"])),
        "d5": ident(1900 + int(cp["content"]["d3"])),
        "playId": ident(2900 + int(cp["content"]["d3"])),
    }
    q["nextCheckpoint"] = {
        "id": ident(3900 + int(cp["content"]["d3"])),
        "revision": str(int(cp["ref"]["revision"]) + 1),
        "digest": "f" * 64,
    }


def append(host, q):
    """実hostで得た全出力をstackへ写し、テスト計算を作らない。"""
    out = json.loads(
        host.call(("deriveLineupPlayPrefixWithContinuation"), json.dumps(q))
    )
    assert out["ok"], out
    v = out["value"]
    c = q["source"]["checkpoint"]["content"]
    before = copy.deepcopy(c["restored"])
    after = copy.deepcopy(before)
    after.update(
        current=copy.deepcopy(v["t1"]["after"]),
        participants=copy.deepcopy(v["participants"]),
        runners=copy.deepcopy(v["runners"]),
        responsibility=copy.deepcopy(v["nextResponsibility"]),
        lastPlayEvaluation=copy.deepcopy(v["t2"]),
    )
    event = {
        "eventId": q["playIdentity"]["eventId"],
        "gameId": c["scope"]["gameId"],
        "generation": c["scope"]["generation"],
        "d1": q["sourcePosition"]["d1"],
        "d5": q["playIdentity"]["d5"],
        "fingerprint": "wire-v1:" + "a" * 64,
        "eventKind": "play_input",
    }
    play = {
        "source": event,
        "playId": q["playIdentity"]["playId"],
        "d2": q["sourcePosition"]["d2"],
        "physicalPlayNumber": c["nextPhysicalPlayNumber"],
    }
    q["source"]["activeStack"].insert(
        0,
        {
            "play": play,
            "historyEntry": copy.deepcopy(v["newHistoryEntry"]),
            "beforeContext": before,
            "afterContext": after,
        },
    )
    c.update(
        restored=after,
        d3=event["d1"],
        d1Head={"kind": "accepted-event", "source": event},
        projectionHead={"kind": "d1-event", "source": event},
        activeHead=play,
        activeDepth=str(int(c["activeDepth"]) + 1),
        historyVersion=str(int(c["historyVersion"]) + 1),
        nextPhysicalPlayNumber=str(int(c["nextPhysicalPlayNumber"]) + 1),
    )
    q["source"]["checkpoint"]["ref"]["revision"] = str(
        int(q["source"]["checkpoint"]["ref"]["revision"]) + 1
    )
    seal(q)
    return out


def control(host, q, action, life, n):
    """真正核応答を閉control候補へ写す。consumed/headはDB試験を別途要する。"""
    c = q["source"]["checkpoint"]["content"]
    before = copy.deepcopy(c["restored"])
    request = {
        "formatVersion": "native-game-lifecycle-v1",
        "action": action,
        "current": copy.deepcopy(before["current"]),
        "lifecycle": life,
        "target": life["active"] if action == "reopen" else None,
        "event": {"eventId": ident(n), "receiptId": ident(n + 100)},
    }
    response = json.loads(host.call("applyGameLifecycle", json.dumps(request)))
    assert response["ok"]
    after = copy.deepcopy(before)
    after["current"] = copy.deepcopy(response["value"]["current"])
    source = {
        "eventId": ident(n),
        "gameId": c["scope"]["gameId"],
        "generation": c["scope"]["generation"],
        "d1": str(int(c["d3"]) + 1),
        "d5": ident(n + 200),
        "fingerprint": "wire-v1:" + "b" * 64,
        "eventKind": "game_end_declaration" if action == "end" else "game_reopen",
    }
    anchor = q["source"]["activeStack"][0]["play"]["source"]["eventId"]
    bridge = {
        "source": source,
        "action": action,
        "anchorEventId": anchor,
        "beforeContext": before,
        "afterContext": after,
        "kernel": {"request": request, "response": response},
        "frameId": ident(n + 300),
        "checkpointBefore": copy.deepcopy(q["source"]["checkpoint"]["ref"]),
    }
    c.update(
        restored=after,
        d3=source["d1"],
        d1Head={"kind": "accepted-event", "source": source},
        projectionHead={"kind": "d1-event", "source": source},
        historyVersion=str(int(c["historyVersion"]) + 1),
        controlBridges=[*c.get("controlBridges", []), bridge],
    )
    q["source"]["checkpoint"]["ref"]["revision"] = str(
        int(q["source"]["checkpoint"]["ref"]["revision"]) + 1
    )
    seal(q)
    return response["value"]["lifecycle"]


@pytest.mark.parametrize("automatic", [False, True])
def test_real_kernel_end_reopen_two_added_play_reend(automatic):
    """FR007のT2真/outcome/Xは保持し、再終了で再開寿命が失効する。"""
    q = fixture_values()[0]["calculation"]["request"]
    c = q["source"]["checkpoint"]["content"]
    r = c["restored"]
    if automatic:
        r["current"]["stateFields"].update(
            {
                "state.inning": "9",
                "state.half": "bottom",
                "state.score": {"home": "3", "away": "2"},
            }
        )
        r["current"]["scoreboard"]["inningScores"] = {"home": "3", "away": "2"}
        r["participants"] = {
            "batterId": r["lineup"]["home"]["battingOrder"]["1"],
            "pitcherId": r["lineup"]["away"]["pitcherId"],
            "catcherId": r["lineup"]["away"]["catcherId"],
            "battingOrder": "1",
        }
    with NodeDomainHost(
        ROOT / "frontend/public/domain/pitchlog-domain.js",
        ROOT / "frontend/public/domain/pitchlog-domain.json",
    ) as host:
        c["executionArtifactSha256"] = host.artifact_sha256
        seal(q)
        initial = append(host, q)
        t2 = copy.deepcopy(initial["value"]["t2"])
        assert t2["decision"]["endConditionDetected"] is automatic
        life = control(
            host,
            q,
            "end",
            {"status": "in_progress", "lastVersion": "0", "active": None},
            5000,
        )
        assert life["lastVersion"] == "1"
        assert (
            json.loads(
                host.call("deriveLineupPlayPrefixWithContinuation", json.dumps(q))
            )["ok"]
            is False
        )
        life = control(host, q, "reopen", life, 6000)
        assert c["restored"]["lastPlayEvaluation"] == t2
        bad = copy.deepcopy(q)
        bad["source"]["checkpoint"]["content"]["controlBridges"][-1]["kernel"][
            "response"
        ]["value"]["current"]["stateFields"]["state.count.balls"] = "3"
        seal(bad)
        assert (
            json.loads(
                host.call("deriveLineupPlayPrefixWithContinuation", json.dumps(bad))
            )["ok"]
            is False
        )
        for expected_balls in ("2", "3"):
            out = append(host, q)
            assert (
                out["value"]["t1"]["after"]["stateFields"]["state.count.balls"]
                == expected_balls
            )
            assert out["value"]["t2"]["decision"]["endConditionDetected"] is automatic
            assert out["value"]["t2"]["decision"]["outcome"] == (
                "walk-off" if automatic else "no-end"
            )
            assert out["value"]["t2"]["decision"]["xMark"] == "recorded-score"
        life = control(host, q, "end", life, 7000)
        assert life["lastVersion"] == "2"
        assert (
            json.loads(
                host.call("deriveLineupPlayPrefixWithContinuation", json.dumps(q))
            )["ok"]
            is False
        )
