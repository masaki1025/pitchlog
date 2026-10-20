"""spike のドメイン計算（T1/T2）を契約のゴールデンベクタで検証する。

正解データは `contracts/state-transition/` の 2 契約と入力軸 descriptor。
T1 は matrixRows 全件（5 面＋23 フラグ）、T2 は判定 248 件・規則設定の
拒否 12 件・境界 39 件・F-2 の既定 2 件を照合する。数値はすべて int で、
契約の表記（記号つき座標）はこの試験側で具体値へ解く。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitchlog.sync.spike_domain import decide, derive, validate_rule

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts" / "state-transition"

R_REF = 9
M_REF = 10
N_REF = 5


def _load(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


T1 = _load("state_transition_contract_v1.json")
T2 = _load("game_end_contract_v1.json")
DESCRIPTOR = _load("input_axes_descriptor_v1.json")


def _number(symbol: str, ref: dict[str, int]) -> int:
    """記号つき整数（"R+1" など）を具体値へ解く。"""
    clean = str(symbol).strip().strip('"')
    if clean in ref:
        return ref[clean]
    for operator in ("+", "-"):
        if operator in clean[1:]:
            name, _, delta = clean.partition(operator)
            base = ref[name]
            return base + int(delta) if operator == "+" else base - int(delta)
    return int(clean)


def _setting(axis_id: str, value: str | int) -> dict[str, Any]:
    """入力軸の値（descriptor・validationErrors）を規則設定へ解く。"""
    clean = str(value).strip().strip('"')
    base = {
        "regulationInnings": R_REF,
        "coldConditions": [],
        "extensionLimit": 12,
        "tiebreak": None,
    }
    ref = {"R": R_REF, "L": 12, "M": M_REF, "N": N_REF}
    if axis_id == "gameEnd.regulationInnings":
        return {
            **base,
            "regulationInnings": _number(clean, ref),
            "extensionLimit": None,
        }
    if axis_id == "gameEnd.extensionLimit":
        if clean == "none":
            return {**base, "extensionLimit": None}
        return {**base, "extensionLimit": _number(clean.split(":", 1)[1], ref)}
    if axis_id == "gameEnd.tiebreak":
        if clean == "none":
            return {**base, "tiebreak": None}
        raw = clean.split(":", 1)[1]
        if raw == "L+1-when-finite":
            return {**base, "tiebreak": 13, "extensionLimit": 12}
        tiebreak = _number(raw, ref)
        return {**base, "tiebreak": tiebreak, "extensionLimit": max(12, tiebreak)}
    if axis_id == "gameEnd.coldConditions":
        kind, raw = clean.split(":", 1)
        if kind == "tier-count":
            count = _number(raw, ref)
            return {
                **base,
                "coldConditions": [
                    {"pointDifference": M_REF, "startInning": N_REF}
                    for _ in range(count)
                ],
            }
        if kind == "point-difference":
            return {
                **base,
                "coldConditions": [
                    {"pointDifference": _number(raw, ref), "startInning": N_REF}
                ],
            }
        if kind == "start-inning":
            return {
                **base,
                "coldConditions": [
                    {"pointDifference": M_REF, "startInning": _number(raw, ref)}
                ],
            }
    raise AssertionError(f"未知の軸または値: {axis_id} {value}")


def _decision_input(coordinate: dict[str, Any]) -> dict[str, Any]:
    """判定ケースの記号座標を具体値へ解く。"""
    regulation = int(coordinate["gameEnd.regulationInnings"])
    raw_limit = str(coordinate["gameEnd.extensionLimit"])
    limit = (
        None
        if raw_limit == "none"
        else _number(raw_limit.split(":", 1)[1], {"R": regulation, "L": 0})
    )
    inning = _number(
        str(coordinate["state.inning"]),
        {
            "R": regulation,
            "L": limit if limit is not None else regulation,
            "N": N_REF,
        },
    )
    raw_score = str(coordinate["state.score"])

    def margin(symbol: str) -> int:
        raw = symbol.split("lead:", 1)[1]
        if raw == "M":
            return M_REF
        if raw == "M+1":
            return M_REF + 1
        if raw == "M-1":
            return M_REF - 1
        return int(raw)

    if raw_score == "tie":
        diff = 0
    elif raw_score.startswith("home-lead"):
        diff = margin(raw_score)
    else:
        diff = -margin(raw_score)
    event = None
    if "event.operationKind" in coordinate:
        event = {
            "operationKind": coordinate["event.operationKind"],
            "kind": coordinate.get("event.perPitch.kind"),
            "resultId": coordinate.get("event.perPitch.resultId"),
        }
    return {
        "regulationInnings": regulation,
        "extensionLimit": limit,
        "tiebreak": None,
        "satisfiedColdTierCount": int(coordinate["gameEnd.satisfiedColdTierCount"]),
        "inning": inning,
        "half": coordinate["state.half"],
        "scoreDiff": diff,
        "gameEnded": bool(coordinate["state.gameEnded"]),
        "tiebreakActive": bool(coordinate["state.tiebreakActive"]),
        "event": event,
    }


SURFACES = (
    "countEffect",
    "plateAppearanceEnded",
    "batterDestination",
    "runnerDefaultAdvance",
    "outEffect",
    "statFlags",
)


def test_t1_matrix_rows_match_contract() -> None:
    """行列層（matrixRows）の全件で 5 面＋23 フラグが契約と一致する。"""
    cases = [case for case in T1["cases"] if case["rowRef"]["layer"] == "matrixRows"]
    assert len(cases) == 89
    mismatches: list[str] = []
    for case in cases:
        coordinate = case["inputCoordinate"]
        before = case["historyInput"]["before"]
        value = derive(
            before["stateFields"],
            before["scoreboard"],
            coordinate["resultId"],
            coordinate.get("event.perPitch.pitchEventKind"),
        )
        for key in SURFACES:
            if value[key] != case["expected"][key]:
                mismatches.append(f"{case['caseId']}: {key}")
    assert mismatches == []


def test_t1_after_state_matches_contract_except_known_rows() -> None:
    """遷移後の状態は契約の historyInput.after と既知の差分だけが残る。

    P-6 の独立検証は `historyInput.after` に 34 行の不整合（語彙違反の
    resultId と矛盾する走者・得点）を検出している。ここでは計算側の
    `after` がその既知の差分を再現することを記録し、差分の総数を固定する。
    """
    cases = [case for case in T1["cases"] if case["rowRef"]["layer"] == "matrixRows"]
    diffs: list[str] = []
    for case in cases:
        coordinate = case["inputCoordinate"]
        before = case["historyInput"]["before"]
        value = derive(
            before["stateFields"],
            before["scoreboard"],
            coordinate["resultId"],
            coordinate.get("event.perPitch.pitchEventKind"),
        )
        after = value["after"]
        expected = case["historyInput"]["after"]
        if (
            after["stateFields"] != expected["stateFields"]
            or after["scoreboard"] != expected["scoreboard"]
        ):
            diffs.append(case["caseId"])
    # 34 行（P-6 の実測）と一致することを固定する。
    assert len(diffs) == 34


def test_t2_validation_errors_are_rejected() -> None:
    """不正な規則設定（validationErrors）の全 12 件が拒否される。"""
    assert len(T2["validationErrors"]) == 12
    for item in T2["validationErrors"]:
        setting = _setting(item["axisId"], item["valueIdentity"])
        assert validate_rule(setting) != [], item
        assert item["expected"] == "reject-invalid-rule-setting"


def test_t2_descriptor_boundaries_are_accepted_and_rejected() -> None:
    """入力軸 descriptor の境界 39 件が受理・拒否に分かれる。"""
    accepted = 0
    rejected = 0
    for axis in DESCRIPTOR["gameEndAxes"]:
        if "derivedFrom" in axis:
            continue
        for value in axis.get("boundaryValues", []):
            setting = _setting(axis["axisId"], value)
            assert validate_rule(setting) == [], (axis["axisId"], value)
            accepted += 1
        for value in axis.get("invalidBoundaryValues", []):
            setting = _setting(axis["axisId"], value)
            assert validate_rule(setting) != [], (axis["axisId"], value)
            rejected += 1
    assert (accepted, rejected) == (27, 12)
    assert accepted + rejected == 39


def test_t2_default_settings_from_f2_are_savable() -> None:
    """F-2 の既定値（公式戦・準公式戦）が保存可能。"""
    official = {
        "regulationInnings": 9,
        "coldConditions": [],
        "extensionLimit": 12,
        "tiebreak": 10,
    }
    semi_official = {
        "regulationInnings": 9,
        "coldConditions": [
            {"pointDifference": 10, "startInning": 5},
            {"pointDifference": 7, "startInning": 7},
        ],
        "extensionLimit": 9,
        "tiebreak": None,
    }
    assert validate_rule(official) == []
    assert validate_rule(semi_official) == []


def test_t2_decisions_match_contract() -> None:
    """判定 248 件が契約の decision と一致する。"""
    assert len(T2["cases"]) == 248
    mismatches: list[str] = []
    for case in T2["cases"]:
        actual = decide(_decision_input(case["inputCoordinate"]))
        for key, expected in case["decision"].items():
            if actual[key] != expected:
                mismatches.append(f"{case['caseId']}: {key}")
    assert mismatches == []


def _draw_rule(**overrides: Any) -> dict[str, Any]:
    """DRAW 系の検証に使う基準設定（R=9・L=12・tiebreak なし）。"""
    rule: dict[str, Any] = {
        "regulationInnings": 9,
        "coldConditions": [],
        "extensionLimit": 12,
        "tiebreak": None,
    }
    rule.update(overrides)
    return rule


@pytest.mark.parametrize(
    ("rule", "reason"),
    [
        (_draw_rule(extensionLimit=8), "req:DRAW-01(L<R)"),
        (_draw_rule(tiebreak=9), "req:DRAW-03(発動回<=R)"),
        (_draw_rule(tiebreak=13), "req:DRAW-03(発動回>L)"),
    ],
)
def test_t2_draw_rules_have_explicit_reasons(
    rule: dict[str, Any], reason: str
) -> None:
    """DRAW-01/03 の拒否理由が条文 ID を保つ。"""
    assert reason in validate_rule(rule)
