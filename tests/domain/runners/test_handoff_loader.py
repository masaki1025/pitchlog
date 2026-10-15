"""付録 E の読み込みと写像を共通変異で検証する。"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_vector_bridge import _direct_report, _Host

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).parent / "fixtures/handoff-loader/mutations.json"
sys.path.insert(0, str(ROOT / "backend/src"))
HANDOFF = importlib.import_module("pitchlog.domaincheck.runners.handoff")
BRIDGE = importlib.import_module("pitchlog.domaincheck.runners.vector_bridge")
VECTORS = importlib.import_module("pitchlog.domaincheck.runners.vectors")


def _json(path: str) -> Any:
    """リポジトリにある契約を試験で読む。"""
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _mutated_bytes(scenario: dict[str, Any]) -> bytes:
    """共通 fixture の一箇所だけを変更したバイト列を返す。"""
    if scenario["operation"] == "directCases":
        source = _json(
            "contracts/state-transition/state_transition_contract_v1.json"
        )["cases"]
        return json.dumps(source, ensure_ascii=False).encode()
    raw = (ROOT / scenario["target"]).read_bytes()
    if scenario["operation"] in {"unsafeInteger", "duplicateField", "negativeZero"}:
        assert b'"schemaVersion": 1' in raw
        replacement = {
            "unsafeInteger": b'"schemaVersion": 9007199254740993',
            "duplicateField": b'"schemaVersion": 1, "schemaVersion": 1',
            "negativeZero": b'"schemaVersion": -0',
        }[scenario["operation"]]
        return raw.replace(b'"schemaVersion": 1', replacement, 1)
    document = json.loads(raw)
    tokens = scenario["pointer"].split("/")[1:]
    item = document
    for token in tokens[:-1]:
        item = item[int(token)] if isinstance(item, list) else item[token]
    final = tokens[-1]
    if isinstance(item, list):
        item[int(final)] = scenario["value"]
    else:
        item[final] = scenario["value"]
    return json.dumps(document, ensure_ascii=False).encode()


def test_loads_all_cases_from_both_contracts() -> None:
    """実契約の件数を動的に数え、宣言された写像だけを適用する。"""
    loaded = HANDOFF.load_handoff(ROOT)
    for calculation_id, filename, source_field in (
        (
            "state-transition",
            "contracts/state-transition/state_transition_contract_v1.json",
            "expected",
        ),
        (
            "game-end",
            "contracts/state-transition/game_end_contract_v1.json",
            "decision",
        ),
    ):
        source_cases = _json(filename)["cases"]
        result = loaded.by_calculation[calculation_id]
        assert len(result.cases) == len(source_cases)
        assert [case["caseId"] for case in result.cases] == [
            case["caseId"] for case in source_cases
        ]
        for source, mapped in zip(source_cases, result.cases, strict=True):
            assert set(mapped) == {"caseId", "raw", "normalized", "expected"}
            assert mapped["expected"] == source[source_field]
            assert mapped["raw"] == source["raw"]
            assert mapped["normalized"] == source["normalized"]


@pytest.mark.parametrize(
    "scenario",
    json.loads(FIXTURE.read_text(encoding="utf-8")),
    ids=lambda scenario: scenario["id"],
)
def test_rejects_shared_mutations(scenario: dict[str, Any]) -> None:
    """直読、版差異、未知 field、精度欠落を規則 ID で拒否する。"""
    changed = _mutated_bytes(scenario)

    def reader(path: str) -> bytes:
        """一つの契約ファイルだけを差し替えて読む。"""
        return changed if path == scenario["target"] else (ROOT / path).read_bytes()

    with pytest.raises(HANDOFF.HandoffLoadError) as error:
        HANDOFF.load_handoff(ROOT, reader)
    assert error.value.code == scenario["code"]


def _step30_scenario(mode: str, mutation: str) -> dict[str, Any]:
    """同じ契約 case から比較経路だけを変える合成ベクタを作る。"""
    contract_asset = json.loads(
        (ROOT / "contracts/state-transition/state_transition_contract_v1.json").read_text(
            encoding="utf-8"
        )
    )
    schema = json.loads(
        (ROOT / "contracts/state-transition/state_transition_contract_schema_v1.json").read_text(
            encoding="utf-8"
        )
    )
    undo_cases = [
        item for item in contract_asset["cases"]
        if item["rowRef"]["layer"] == "undoRows"
    ]
    full_case = next(
        item for item in undo_cases
        if item["expected"]["guaranteeMode"] == "full-equality"
        and item["rowRef"]["coordinate"]["targetKind"] == "confirmed-play"
        and item["inputCoordinate"]["history.topDifference.changedFaces"]
        == "state-and-scoreboard"
        and item["inputCoordinate"]["history.scenarioLength"] == 1
    )
    source = (
        next(
            item for item in undo_cases
            if item["expected"]["guaranteeMode"] == "liveness-only"
            and item["rowRef"]["coordinate"]["targetKind"] == "confirmed-play"
            and item["inputCoordinate"]["history.scenarioLength"] == "D+1"
        )
        if mode == "liveness-only"
        else full_case
    )
    case = copy.deepcopy(source)
    normalized = [{"value": {"kind": "integer", "value": 1}}]
    case["raw"] = normalized
    case["normalized"] = normalized
    expected = case["expected"]
    remaining_length = len(case["historyInput"]["stack"]) - 1
    if mode == "liveness-only":
        output: dict[str, Any] = {
            "operationResult": "applied",
            "historyContext": ["比較対象外"] * remaining_length,
            "stateEffect": {"別の状態欄": "比較対象外"},
        }
        if mutation == "two-lost":
            output["historyContext"] = ["比較対象外"] * (remaining_length - 1)
        elif mutation == "rejected":
            output["operationResult"] = "nothing-to-undo"
    else:
        output = copy.deepcopy(expected)
        if mutation == "state-mismatch":
            output["stateEffect"]["stateFields"]["state.half"] = {
                "kind": "set", "value": "top",
            }
        elif mutation == "scoreboard-mismatch":
            output["stateEffect"]["scoreboard"]["hits"] = {
                "kind": "set", "value": "999",
            }
        elif mutation == "stat-flags-mismatch":
            output["stateEffect"]["statFlags"]["投球数"] = {
                "kind": "set", "value": "999",
            }
    comparison_fields = [
        {
            "field": field,
            "role": "structured",
            "valueType": "json",
            "nullable": False,
            "scale": None,
        }
        for field in full_case["expected"]
    ]
    return {
        "cases": [case],
        "contract": {
            "calculation": "syntheticLiveness",
            "vector": "syntheticUndoVector",
            "entrypointId": "syntheticUndoEntrypoint",
            "directTargetId": "syntheticUndoTarget",
            "caseSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["caseId", "raw", "normalized", "expected"],
                "additionalProperties": True,
            },
            "normalizationComparison": {
                "surface": "structured-only",
                "fields": [{
                    "field": "value", "role": "structured", "valueType": "exact-number",
                    "nullable": False, "scale": 0,
                }],
                "normalizations": ["exact-numeric-representation"],
            },
            "outputComparison": {
                "surface": "structured-only", "fields": comparison_fields,
                "normalizations": [],
            },
            "livenessComparison": schema["x-pitchlog-undo-liveness-comparison"],
        },
        "normalizer": {
            "generatedId": "syntheticUndoNormalizer",
            "sourceHash": "sha256:" + "1" * 64,
            "mode": "table",
            "table": [{"raw": normalized, "normalized": normalized}],
        },
        "calculation": {
            "supportedCaseIds": [case["caseId"]],
            "outputs": {case["caseId"]: output},
        },
    }


@pytest.mark.parametrize(
    ("mode", "mutation", "accepted"),
    [
        ("liveness-only", "none", True),
        ("liveness-only", "two-lost", False),
        ("liveness-only", "rejected", False),
        ("full-equality", "none", True),
        ("full-equality", "state-mismatch", False),
        ("full-equality", "scoreboard-mismatch", False),
        ("full-equality", "stat-flags-mismatch", False),
    ],
)
def test_step30_direct_and_bridge_comparisons_agree(
    mode: str, mutation: str, accepted: bool,
) -> None:
    """保証モードごとの成功・失敗が直接経路とTS用ブリッジで一致する。"""
    scenario = _step30_scenario(mode, mutation)
    host = _Host(scenario)
    assert BRIDGE.serve(host.stdin, host.stdout) == 0
    terminal = host.stdout.messages[-1]
    if accepted:
        direct = _direct_report(scenario)
        assert json.dumps(terminal, sort_keys=True) == json.dumps(direct, sort_keys=True)
        assert terminal["complete"] is True
    else:
        with pytest.raises(VECTORS.VectorRunError, match="計算結果が不一致"):
            _direct_report(scenario)
        assert terminal == {
            "type": "vector-run-error",
            "message": f"計算結果が不一致: {scenario['cases'][0]['caseId']}",
        }
