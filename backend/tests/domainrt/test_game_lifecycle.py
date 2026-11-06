"""終了/自動検知後再開を唯一実artifactで照合し、再開後の偽falseを作らない。"""

import copy
import json
from pathlib import Path

import pytest

from pitchlog.domainrt.game_lifecycle import (
    LifecycleProtocolError,
    LifecycleRequest,
    LifecycleRequestError,
    decode_lifecycle_response,
)
from pitchlog.domainrt.host import NodeDomainHost

ROOT = Path(__file__).resolve().parents[3]
EVENT = "10000000-0000-0000-0000-000000000001"
RECEIPT = "20000000-0000-0000-0000-000000000001"
NEXT_EVENT = "10000000-0000-0000-0000-000000000002"
NEXT_RECEIPT = "20000000-0000-0000-0000-000000000002"


def request():
    """独立の九回裏サヨナラ検知後の手入力。製品出力から期待を採らない。"""
    return {
        "formatVersion": "native-game-lifecycle-v1",
        "action": "end",
        "current": {
            "stateFields": {
                "state.inning": "9",
                "state.half": "bottom",
                "state.outs": "1",
                "state.count.strikes": "2",
                "state.count.balls": "1",
                "state.runners": "second-third",
                "state.battingOrder": "5",
                "state.tiebreakActive": False,
                "state.gameEnded": True,
                "state.score": {"home": "3", "away": "2"},
            },
            "scoreboard": {
                "inningScores": {"home": "1", "away": "0"},
                "hits": "9",
                "errors": "1",
                "strikeouts": "3",
                "walks": "2",
            },
            "battingOrderBySide": {"home": "5", "away": "7"},
        },
        "lifecycle": {"status": "in_progress", "lastVersion": "0", "active": None},
        "target": None,
        "event": {"eventId": EVENT, "receiptId": RECEIPT},
    }


@pytest.fixture(scope="module")
def host():
    """配置済み実単一IIFEをhost自身のhash検査へ通す。"""
    with NodeDomainHost(
        ROOT / "frontend/public/domain/pitchlog-domain.js",
        ROOT / "frontend/public/domain/pitchlog-domain.json",
    ) as value:
        yield value


def call(host, value):
    """全応答をcodecで読み、固定結果を注入しない。"""
    req = LifecycleRequest(json.dumps(value))
    return decode_lifecycle_response(
        host.call("applyGameLifecycle", req.json)
    ).to_wire()


def test_end_reopen_and_reend_preserve_all_math(host):
    """D01=Bの既計算結果を変えず、終了ロック解除だけを核で行う。"""
    r = request()
    original = copy.deepcopy(r)
    expected_end = {
        "ok": True,
        "value": {
            "current": original["current"],
            "lifecycle": {
                "status": "finished",
                "lastVersion": "1",
                "active": {
                    "version": "1",
                    "eventId": EVENT,
                    "receiptId": RECEIPT,
                },
            },
            "stateEffect": {
                "gameEnded": {"kind": "unchanged", "before": True, "after": True}
            },
        },
    }
    ended = call(host, r)
    assert ended == expected_end and r == original
    reopened_request = {
        **copy.deepcopy(r),
        "action": "reopen",
        "lifecycle": ended["value"]["lifecycle"],
        "target": ended["value"]["lifecycle"]["active"],
        "event": {"eventId": NEXT_EVENT, "receiptId": NEXT_RECEIPT},
    }
    current_after = copy.deepcopy(original["current"])
    current_after["stateFields"]["state.gameEnded"] = False
    reopened = call(host, reopened_request)
    assert reopened == {
        "ok": True,
        "value": {
            "current": current_after,
            "lifecycle": {"status": "in_progress", "lastVersion": "1", "active": None},
            "stateEffect": {
                "gameEnded": {"kind": "set", "before": True, "after": False}
            },
        },
    }
    r.update(current=current_after, lifecycle=reopened["value"]["lifecycle"])
    reended = call(host, r)
    assert reended == {
        "ok": True,
        "value": {
            "current": current_after,
            "lifecycle": {
                "status": "finished",
                "lastVersion": "2",
                "active": {
                    "version": "2",
                    "eventId": EVENT,
                    "receiptId": RECEIPT,
                },
            },
            "stateEffect": {
                "gameEnded": {"kind": "unchanged", "before": False, "after": False}
            },
        },
    }


def test_early_end_does_not_invent_t2_end_detection(host):
    """FR010の早期宣言はstate.gameEndedをtrueへ仮補完しない。"""
    r = request()
    r["current"]["stateFields"].update({"state.inning": "1", "state.gameEnded": False})
    out = call(host, r)
    assert out["value"]["current"] == r["current"]
    assert out["value"]["lifecycle"]["status"] == "finished"
    assert out["value"]["stateEffect"]["gameEnded"] == {
        "kind": "unchanged",
        "before": False,
        "after": False,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "target",
        "wrong-version",
        "wrong-event",
        "wrong-receipt",
        "wrong-status",
        "same-event",
        "same-receipt",
    ],
)
def test_reopen_requires_exact_current_finalization(host, mutation):
    """閉じた型と同値条件を検査する。"""
    r = request()
    active = {"version": "1", "eventId": EVENT, "receiptId": RECEIPT}
    r.update(
        action="reopen",
        lifecycle={"status": "finished", "lastVersion": "1", "active": active},
        target=copy.deepcopy(active),
        event={"eventId": NEXT_EVENT, "receiptId": NEXT_RECEIPT},
    )
    if mutation == "target":
        r["target"] = None
    if mutation == "wrong-version":
        r["target"]["version"] = "2"
    if mutation == "wrong-event":
        r["target"]["eventId"] = NEXT_EVENT
    if mutation == "wrong-receipt":
        r["target"]["receiptId"] = NEXT_RECEIPT
    if mutation == "wrong-status":
        r["lifecycle"]["status"] = "in_progress"
    if mutation == "same-event":
        r["event"]["eventId"] = EVENT
    if mutation == "same-receipt":
        r["event"]["receiptId"] = RECEIPT
    assert call(host, r) == {
        ("ok"): False,
        ("error"): {("code"): ("LIFECYCLE_STATE_MISMATCH")},
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "bool-version",
        "leading-zero",
        "lf",
        "current-extra",
        "current-missing",
        "number-count",
        "unknown-action",
    ],
)
def test_request_closed_codec_and_artifact_reject(host, mutation):
    """閉じた型と同値条件を検査する。"""
    r = request()
    if mutation == "extra":
        r["unknown"] = None
    if mutation == "bool-version":
        r["lifecycle"]["lastVersion"] = False
    if mutation == "leading-zero":
        r["lifecycle"]["lastVersion"] = "01"
    if mutation == "lf":
        r["lifecycle"]["lastVersion"] = "1\n"
    if mutation == "current-extra":
        r["current"]["unknown"] = None
    if mutation == "current-missing":
        del r["current"]["stateFields"]["state.gameEnded"]
    if mutation == "number-count":
        r["current"]["stateFields"]["state.count.balls"] = 1
    if mutation == "unknown-action":
        r["action"] = "substitution"
    with pytest.raises(LifecycleRequestError):
        LifecycleRequest(json.dumps(r))
    if mutation not in {"bool-version", "number-count"}:
        assert (
            json.loads(host.call(("applyGameLifecycle"), json.dumps(r)))[("ok")]
            is False
        )


@pytest.mark.parametrize(
    "raw",
    [
        '{"ok":true}',
        '{"ok":true,"value":null}',
        '{"ok":false,"error":{"code":"SOMETHING"}}',
    ],
)
def test_response_cannot_supply_fake_success(raw):
    """閉じた型と同値条件を検査する。"""
    with pytest.raises(LifecycleProtocolError):
        decode_lifecycle_response(raw)
