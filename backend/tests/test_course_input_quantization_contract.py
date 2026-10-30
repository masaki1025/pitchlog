"""量子化の候補契約を規範由来の厳密有理数と照合する。

製品artifactは呼び出さない。作者側の整合検査であり、非作者検証・
P-6 blind・製品実装検査の成立を意味しない。
"""

from __future__ import annotations

import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (
    ROOT / "contracts/display-geometry/course_input_quantization_contract_v1.json"
)
DECIMAL = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$")


def _contract() -> dict[str, Any]:
    """検査対象の候補契約を読む。"""
    return json.loads(CONTRACT.read_text())


def _expected(data: dict[str, str]) -> dict[str, Any]:
    """規範のhalf-upをFractionのfloorとして独立計算する。"""
    if data["view"] not in {"catcher", "pitcher"}:
        return {"ok": False, "error": {"code": "INVALID_VIEW"}}
    parsed = []
    for key in ("x", "y"):
        text = data[key]
        if len(text) > 400 or DECIMAL.fullmatch(text) is None:
            return {"ok": False, "error": {"code": "INVALID_DECIMAL"}}
        parts = re.split("[eE]", text)
        if len(parts) == 2 and abs(int(parts[1])) > 400:
            return {"ok": False, "error": {"code": "INVALID_DECIMAL"}}
        parsed.append(Fraction(text))
    size = int(data["size"])
    if any(value < 0 or value > size for value in parsed):
        return {"ok": False, "error": {"code": "OUT_OF_RANGE"}}
    rounded = [value + Fraction(1, 2) for value in parsed]
    x, y = [value.numerator // value.denominator for value in rounded]
    if data["view"] == "pitcher":
        x = size - x
    return {"ok": True, "value": {"unit": f"1/{size}", "x": str(x), "y": str(size - y)}}


def test_separate_calculation_and_pending_independent_verification() -> None:
    """別計算・非作者確認未実施と既存42件不変の前提を固定する。"""
    contract = _contract()
    assert contract["calculation"] == "course-input-quantization"
    assert contract["status"] == "candidate"
    assert contract["provenance"]["independentVerifierId"] == "not-performed"
    assert contract["provenance"]["independentVerificationStatus"] == "pending"
    assert contract["abi"]["comparison"] == "complete-envelope"
    existing = json.loads(
        (
            ROOT / "contracts/display-geometry/coordinate_transform_contract_v1.json"
        ).read_text()
    )
    assert existing["calculation"] == "coordinate-transform"
    assert len(existing["cases"]) == 42


def test_vectors_match_independent_rational_derivation_completely() -> None:
    """固定1093件を部分一致せず完全封筒で照合する。"""
    cases = _contract()["cases"]
    assert len(cases) == 1093
    assert len({case["caseId"] for case in cases}) == len(cases)
    for case in cases:
        assert set(case["input"]) == {"x", "y", "view", "size"}
        assert case["expected"] == _expected(case["input"]), case["caseId"]


def test_grid_covers_both_axes_views_and_batter_sides() -> None:
    """両軸264点・両視点・両打席1056組を欠落なく固定する。"""
    size = json.loads((ROOT / "contracts/display_geometry_263_v1.json").read_text())[
        "size"
    ]
    cases = [
        case for case in _contract()["cases"] if case["caseId"].startswith("grid-")
    ]
    assert len(cases) == 1056
    actual = {
        (
            int(c["input"]["x"]),
            int(c["input"]["y"]),
            c["input"]["view"],
            c["descriptor"]["batterSide"],
        )
        for c in cases
    }
    assert actual == {
        (k, k, view, side)
        for k in range(size + 1)
        for view in ("catcher", "pitcher")
        for side in ("right", "left")
    }


def test_descriptors_reference_counterexamples() -> None:
    """検査軸と変異の参照先を固定し、空宣言を許さない。"""
    contract = _contract()
    by_id = {case["caseId"]: case for case in contract["cases"]}
    for key in ("propertyDescriptors", "mutationDescriptors"):
        assert len(contract[key]) == 5
        assert len({item["id"] for item in contract[key]}) == 5
        for item in contract[key]:
            assert item["caseIds"]
            assert set(item["caseIds"]) <= by_id.keys()
    # 製品変異試験はゲート後。ここでは各変異が差を生む期待値を固定する。
    assert by_id["half-exact-catcher"]["expected"]["value"]["x"] == "132"
    assert by_id["y-half"]["expected"]["value"]["y"] == "131"
    assert by_id["half-exact-pitcher"]["expected"]["value"]["x"] == "131"
    assert by_id["grid-000-catcher-right"]["expected"]["value"]["y"] == "263"
    for case_id in ("negative-tiny", "too-large-tiny"):
        assert by_id[case_id]["expected"] == {
            "ok": False,
            "error": {"code": "OUT_OF_RANGE"},
        }
    assert by_id["changed-size"]["expected"]["value"] == {
        "unit": "1/9",
        "x": "4",
        "y": "6",
    }
