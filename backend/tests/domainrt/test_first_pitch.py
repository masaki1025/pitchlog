"""最初の一球を製品と同じNodeホストのartifactで検査する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pitchlog.domainrt.host import NodeDomainHost

_ROOT = Path(__file__).resolve().parents[3]
_ARTIFACT = _ROOT / "frontend/public/domain/pitchlog-domain.js"
_DECLARATION = _ROOT / "frontend/public/domain/pitchlog-domain.json"


def _decimalize(value: Any) -> Any:
    """契約整数の表現だけをABIへ写し、効果を計算しない。"""
    if type(value) is int:
        return str(value)
    if isinstance(value, list):
        return [_decimalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _decimalize(item) for key, item in value.items()}
    return value


def _case() -> dict[str, Any]:
    """承認済みの一球caseを正式契約からそのまま読む。"""
    contract = json.loads(
        (
            _ROOT / "contracts/state-transition/state_transition_contract_v1.json"
        ).read_text()
    )
    return next(
        case
        for case in contract["cases"]
        if case["caseId"] == "ST-MATRIX-0529a0eb116d64a9"
    )


def _request(case: dict[str, Any]) -> dict[str, Any]:
    """入力座標と実beforeをJSON境界へ一対一に写す。"""
    return {
        "eventKind": case["inputCoordinate"]["eventKind"],
        "resultId": case["inputCoordinate"]["resultId"],
        "pitchEventKind": case["inputCoordinate"]["event.perPitch.pitchEventKind"],
        "before": _decimalize(case["historyInput"]["before"]),
    }


def test_real_node_host_matches_complete_first_pitch_contract() -> None:
    """六効果/全23flag/after/履歴を同artifactで完全一致比較する。"""
    case = _case()
    expected = {
        key: case["expected"][key]
        for key in (
            "countEffect",
            "plateAppearanceEnded",
            "batterDestination",
            "runnerDefaultAdvance",
            "outEffect",
            "statFlags",
            "historyContext",
        )
    }
    expected["after"] = case["historyInput"]["after"]
    with NodeDomainHost(_ARTIFACT, _DECLARATION) as host:
        actual = json.loads(host.call("deriveState", json.dumps(_request(case))))
    assert actual == {"ok": True, "value": _decimalize(expected)}
    assert len(actual["value"]["statFlags"]) == 23


def test_real_node_host_rejects_unimplemented_operation() -> None:
    """未実装操作を固定成功や状態不変成功へ代替しない。"""
    request = _request(_case())
    request["resultId"] = "batting-result.home-run"
    with NodeDomainHost(_ARTIFACT, _DECLARATION) as host:
        actual = json.loads(host.call("deriveState", json.dumps(request)))
    assert actual == {"ok": False, "error": {"code": "UNSUPPORTED_T1_SCOPE"}}
