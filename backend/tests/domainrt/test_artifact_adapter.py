"""常駐 Node を合成ベクタ runner へ接続して検証する。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from pitchlog.domaincheck.path_match import ComparisonContract, FieldContract
from pitchlog.domaincheck.runners.artifact_adapter import NodeArtifactAdapter
from pitchlog.domaincheck.runners.vectors import VectorContract, run_vectors
from pitchlog.domainrt import DomainRuntimeError, NodeDomainHost

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests/domain/runners/fixtures/artifact-adapter"
)


def _comparison(document: dict[str, Any]) -> ComparisonContract:
    """共通 fixture の比較面を既存の契約型へ変換する。"""
    return ComparisonContract(
        surface=document["surface"],
        fields=tuple(
            FieldContract(
                field=item["field"],
                role=item["role"],
                value_type=item["valueType"],
                nullable=item["nullable"],
                scale=item["scale"],
            )
            for item in document["fields"]
        ),
        normalizations=frozenset(document["normalizations"]),
    )


def _contract(document: dict[str, Any]) -> VectorContract:
    """合成ベクタの宣言を pytest runner の契約へ変換する。"""
    return VectorContract(
        calculation=document["calculation"],
        vector=document["vector"],
        runner="pytest",
        entrypoint_id=document["entrypointId"],
        direct_target_id=document["directTargetId"],
        case_schema=document["caseSchema"],
        normalization_comparison=_comparison(document["normalizationComparison"]),
        output_comparison=_comparison(document["outputComparison"]),
    )


def _vector() -> dict[str, Any]:
    """両経路が使う合成ベクタを返す。"""
    return json.loads((FIXTURE / "vector.json").read_text(encoding="utf-8"))


def _host() -> NodeDomainHost:
    """両経路で同一の合成 artifact を検証して起動する。"""
    return NodeDomainHost(
        FIXTURE / "pitchlog-domain.js", FIXTURE / "pitchlog-domain.json"
    )


def test_node_artifact_adapter_consumes_every_case() -> None:
    """常駐 Node 経由の正規化と計算で合成ベクタを完走する。"""
    vector = _vector()
    digest = hashlib.sha256((FIXTURE / "pitchlog-domain.js").read_bytes()).hexdigest()
    with _host() as host:
        adapter = NodeArtifactAdapter(host, vector["generatedId"], f"sha256:{digest}")
        report = run_vectors(
            vector["cases"], _contract(vector["contract"]), adapter, adapter
        )
    assert report.complete
    assert report.consumed_case_ids == tuple(item["caseId"] for item in vector["cases"])
    assert len(adapter.calls) == len(vector["cases"]) * 2
    for index, item in enumerate(vector["cases"]):
        assert json.loads(adapter.calls[index * 2].response_json) == item["normalized"]
        assert (
            json.loads(adapter.calls[index * 2 + 1].response_json) == item["expected"]
        )


def test_node_artifact_adapter_rejects_json_number() -> None:
    """数値型が紛れた要求は常駐 Node の境界で失敗する。"""
    with _host() as host:
        adapter = NodeArtifactAdapter(host, "syntheticNormalizer", f"sha256:{'1' * 64}")
        with pytest.raises(DomainRuntimeError) as error:
            adapter.normalize([{"legacyValue": 1}])
    assert error.value.code == "INVALID_BOUNDARY"
    assert adapter.calls == []
