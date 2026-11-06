"""FR-007/010の規範期待を、唯一実artifactと閉typed入口に通す。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from pitchlog.domainrt.game_lifecycle import (
    LifecycleRequest,
    _validator,
    decode_lifecycle_response,
    evaluate_game_lifecycle,
)
from pitchlog.domainrt.host import NodeDomainHost

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "contracts/state-transition/game_lifecycle_cases_v1.json"
VECTORS = ROOT / "contracts/state-transition/game_lifecycle_d11_vectors_v1.json"


def test_normative_lifecycle_cases_use_actual_host_and_closed_codec(record_property):
    """期待をhost出力から作らず、各規範値を実単一IIFEへ照合する。"""
    document = json.loads(CASES.read_text())
    assert set(document) == {"cases"}
    cases = document["cases"]
    assert type(cases) is list and len(cases) == 4
    assert len({row["caseId"] for row in cases}) == 4
    wrapped = json.loads(VECTORS.read_text())
    assert wrapped["calculation"] == "native-game-lifecycle-v1"
    assert (
        wrapped["sourcePath"]
        == "contracts/state-transition/game_lifecycle_cases_v1.json"
    )
    assert wrapped["sourceSha256"] == hashlib.sha256(CASES.read_bytes()).hexdigest()
    assert len(wrapped["cases"]) == len(cases)
    for row, vector in zip(cases, wrapped["cases"], strict=True):
        assert isinstance(row, dict)
        assert vector == {
            "caseId": row["caseId"],
            "request": row["request"],
            "expected": {
                "comparison": "exact",
                "expected": row["expected"],
                "provenance": "FR-007 追記再開",
            },
        }
    artifact = ROOT / "frontend/public/domain/pitchlog-domain.js"
    declaration = ROOT / "frontend/public/domain/pitchlog-domain.json"
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert wrapped["executionArtifactSha256"] == digest
    domain = ROOT / "backend/domain"
    manifest = json.loads((domain / "game-lifecycle-manifest.json").read_text())
    schema = json.loads((domain / "manifest.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    assert manifest["calculations"][0]["directTargets"][0]["hash"] == (
        "sha256:" + digest
    )
    catalog = json.loads((domain / "game-lifecycle-property-catalog.json").read_text())
    catalog_schema = json.loads(
        (domain / "game-lifecycle-property-catalog.schema.json").read_text()
    )
    Draft202012Validator(catalog_schema).validate(catalog)
    with NodeDomainHost(artifact, declaration) as host:
        assert host.artifact_sha256 == digest
        for row in cases:
            assert set(row) == {"caseId", "request", "expected"}
            request = LifecycleRequest(json.dumps(row["request"]))
            direct = decode_lifecycle_response(
                host.call("applyGameLifecycle", request.json)
            ).to_wire()
            typed = evaluate_game_lifecycle(host, request).to_wire()
            assert direct == typed == row["expected"], row["caseId"]
    for row in cases:
        _validator("Response").validate(row["expected"])
    record_property("calculation", "native-game-lifecycle-v1")
    record_property("normativeCases", len(cases))
    record_property("artifactSha256", digest)
