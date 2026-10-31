"""新v3の規範34期待を実artifactと固定typed callerの両経路へ通す。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from jsonschema import Draft202012Validator

import pitchlog
from pitchlog.domainrt.host import NodeDomainHost
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    LineupPrefixRequest,
    evaluate_lineup_prefix_continuation,
)

_ROOT = Path(__file__).resolve().parents[3]
_BASE = _ROOT / "contracts/state-transition"


def test_normative_34_actual_direct_and_product_factory_full_values(
    record_property: Callable[[str, object], None],
) -> None:
    """期待を実行から生成せず、実factoryの開閉を34回独立に検査する。"""
    assert Path(pitchlog.__file__).resolve().is_relative_to(_ROOT / "backend/src")
    source = _BASE / "lineup_play_prefix_cases_v1.json"
    normative = json.loads(source.read_text())
    wrapped = json.loads((_BASE / "lineup_play_prefix_d11_vectors_v1.json").read_text())
    artifact = _ROOT / "frontend/public/domain/pitchlog-domain.js"
    declaration = _ROOT / "frontend/public/domain/pitchlog-domain.json"
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert wrapped["calculation"] == "lineup-play-prefix-v3"
    assert wrapped["sourcePath"] == (
        "contracts/state-transition/lineup_play_prefix_cases_v1.json"
    )
    assert wrapped["sourceSha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert wrapped["executionArtifactSha256"] == digest
    assert len(wrapped["cases"]) == len(normative["cases"]) == 34
    schema = json.loads((_ROOT / "backend/domain/manifest.schema.json").read_text())
    validator = Draft202012Validator(
        {"$ref": "#/$defs/ExpectedValue", "$defs": schema["$defs"]}
    )
    last = None
    with NodeDomainHost(artifact, declaration) as direct_host:
        assert direct_host.artifact_sha256 == digest
        for case, row in zip(normative["cases"], wrapped["cases"], strict=True):
            assert set(row) == {"caseId", "request", "expected"}
            assert row["caseId"] == case["caseId"]
            assert row["request"] == case["request"]
            validator.validate(row["expected"])
            assert row["expected"] == {
                "comparison": "exact",
                "expected": case["expected"],
                "provenance": "NFR-018 (b)② 差分の検出可能性",
            }
            request = LineupPrefixRequest.model_validate_json(
                json.dumps(row["request"])
            )
            assert (
                request.model_dump(mode="json", by_alias=True, exclude_unset=True)
                == row["request"]
            )
            direct = json.loads(
                direct_host.call(
                    "deriveLineupPlayPrefixWithContinuation",
                    request.model_dump_json(by_alias=True, exclude_unset=True),
                )
            )
            assert direct == row["expected"]["expected"], row["caseId"]
            # 製品側factory/loaded hash/一回callは差し替えず実入口を通す。
            typed = evaluate_lineup_prefix_continuation(request)
            entrypoint = typed.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            )
            assert entrypoint == row["expected"]["expected"], row["caseId"]
            last = (row["caseId"], row["expected"]["expected"], entrypoint, direct)
    assert last is not None
    case_id, expected, entrypoint, direct = last
    measured = {
        "calculation": "lineup-play-prefix-v3",
        "propertyId": "lineupPrefixHostParity",
        "propertyKind": "equivalence",
        "generatedCases": 34,
        "status": "passed",
        "trace": {
            "vector": "lineupPrefixVectors",
            "case": case_id,
            "entrypointId": "lineupPrefixServer",
            "directTargetId": "lineupPrefixDirect",
            "expected": expected,
            "entrypointOutput": entrypoint,
            "directTargetOutput": direct,
            "artifactHashes": {"single": "sha256:" + digest},
            "issuedSqlOrAst": None,
            "stageIO": [],
        },
    }
    for name, value in measured.items():
        record_property(name, json.dumps(value) if isinstance(value, dict) else value)
