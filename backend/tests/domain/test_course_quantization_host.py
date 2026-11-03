"""保存された単一 JS を実ホストで実行し、独立契約と全封筒比較する。"""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from pitchlog.domaincheck.cli import validate_asset
from pitchlog.domainrt.course_quantization import CourseQuantizationAdapter
from pitchlog.domainrt.host import open_domain_host

ROOT = Path(__file__).resolve().parents[3]
CALCULATION = "course-input-quantization"


def _contract() -> dict:
    """正解を製品実装から導出せず、独立契約を読む。"""
    return json.loads(
        (
            ROOT
            / "contracts/display-geometry/course_input_quantization_contract_v1.json"
        ).read_text()
    )


def _expected_value(case: dict) -> dict:
    """契約の全封筒を変えず、登録済ExpectedValueへ検査用に射影する。"""
    schema = json.loads((ROOT / "backend/domain/manifest.schema.json").read_text())
    manifest = json.loads((ROOT / "backend/domain/manifest.json").read_text())
    registered = manifest["calculations"][0]["vectors"][0]["expectedValueSchema"]
    projected = {
        "expected": case["expected"],
        "comparison": "exact",
        "provenance": "付録A-1 座標の丸め",
    }
    validate_asset(
        projected,
        {"$schema": schema["$schema"], "$ref": registered, "$defs": schema["$defs"]},
    )
    return projected


def _record(
    record_property: Callable[[str, object], None],
    property_id: str,
    kind: str,
    count: int,
    case: dict,
    entrypoint_output: dict,
    direct_output: dict,
) -> None:
    """既収集器へ、実測した両呼出し・全期待値・実hashを渡す。"""
    digest = (
        "sha256:"
        + hashlib.sha256(
            (ROOT / "frontend/public/domain/pitchlog-domain.js").read_bytes()
        ).hexdigest()
    )
    for name, value in {
        "calculation": CALCULATION,
        "propertyId": property_id,
        "propertyKind": kind,
        "generatedCases": count,
        "status": "passed",
        "trace": {
            "vector": "courseQuantizationVectors",
            "case": case["caseId"],
            "entrypointId": "courseQuantizationServer",
            "directTargetId": "courseQuantizationDirect",
            "expected": case["expected"],
            "entrypointOutput": entrypoint_output,
            "directTargetOutput": direct_output,
            "artifactHashes": {"single": digest},
            "issuedSqlOrAst": None,
            "stageIO": [],
        },
    }.items():
        record_property(name, json.dumps(value) if isinstance(value, dict) else value)


def test_course_contract_all_cases_through_real_host(
    record_property: Callable[[str, object], None],
) -> None:
    """全宣言caseを一度ずつ実行し、欠落/余剰を含め全封筒を照合する。"""
    cases = _contract()["cases"]
    assert cases and len({case["caseId"] for case in cases}) == len(cases)
    with open_domain_host() as host:
        adapter = CourseQuantizationAdapter(host)
        last = None
        direct = None
        for case in cases:
            last = adapter.execute(case["caseId"], case["input"])
            expected_value = _expected_value(case)
            assert last == expected_value["expected"], case["caseId"]
            if last["ok"]:
                size = int(case["input"]["size"])
                body = last["value"]
                assert isinstance(body, dict)
                assert 0 <= int(body["x"]) <= size
                assert 0 <= int(body["y"]) <= size
        direct = json.loads(host.call("quantizeCourse", json.dumps(cases[-1]["input"])))
        assert last is not None
        assert direct == last
    _record(
        record_property, "courseRange", "invariant", len(cases), cases[-1], last, direct
    )


def test_course_real_host_adapter_and_direct_are_equal(
    record_property: Callable[[str, object], None],
) -> None:
    """実アダプタと実artifact直接呼出しの双方を独立期待値に合わせる。"""
    case = next(
        case
        for case in _contract()["cases"]
        if case["caseId"] == "grid-000-catcher-right"
    )
    with open_domain_host() as host:
        entrypoint = CourseQuantizationAdapter(host).execute(
            case["caseId"], case["input"]
        )
        direct = json.loads(host.call("quantizeCourse", json.dumps(case["input"])))
    assert entrypoint == direct == _expected_value(case)["expected"]
    _record(
        record_property, "courseHostParity", "equivalence", 1, case, entrypoint, direct
    )


@pytest.mark.parametrize(
    "payload", [{}, {"x": "1", "y": "2", "view": "unknown", "size": "263"}]
)
def test_course_host_preserves_closed_rejection(payload: dict) -> None:
    """未対応要求を成功値へ補完せず、同じartifactの拒否を返す。"""
    with open_domain_host() as host:
        result = CourseQuantizationAdapter(host).execute("negative", payload)
    assert result["ok"] is False
