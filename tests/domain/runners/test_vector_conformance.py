"""共通の適合ベクタを pytest から既存 runner へ直接渡す。"""

from __future__ import annotations

import ast
import importlib
import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
FIXTURE_DIR = Path(__file__).parent / "fixtures/vector-conformance"

sys.path.insert(0, str(BACKEND_SRC))
VECTORS = importlib.import_module("pitchlog.domaincheck.runners.vectors")
PATH_MATCH = importlib.import_module("pitchlog.domaincheck.path_match")
CLI = importlib.import_module("pitchlog.domaincheck.cli")

SCENARIO_IDS = {
    "valid-two-cases",
    "passthrough-normalizer",
    "unsupported-case",
    "unknown-case-field",
    "duplicate-case-id",
    "case-schema-mismatch",
    "output-mismatch",
    "invalid-normalizer-hash",
    "empty-cases",
}
EXISTING_TEST_SCENARIOS = {
    "test_valid_vector_consumes_every_case_and_reaches_calculation": "valid-two-cases",
    "test_passthrough_normalization_fails_before_calculation": "passthrough-normalizer",
    "test_unsupported_case_fails_individually": "unsupported-case",
    "test_unknown_case_field_fails_individually": "unknown-case-field",
    "test_duplicate_case_id_fails_individually": "duplicate-case-id",
    "test_case_schema_mismatch_fails_individually": "case-schema-mismatch",
}
# 既存機構への委譲をソースで確認する静的検査であり、実行シナリオを持たない。
EXCLUDED_EXISTING_TESTS = {
    "test_runner_uses_existing_schema_checker_and_lossless_comparator",
}


def _load_scenarios() -> list[dict[str, Any]]:
    """Schema に適合した共通 fixture のシナリオを返す。"""
    fixture = json.loads(
        (FIXTURE_DIR / "vector_conformance_v1.json").read_text(encoding="utf-8")
    )
    schema = json.loads(
        (FIXTURE_DIR / "vector_conformance_schema_v1.json").read_text(
            encoding="utf-8"
        )
    )
    CLI.validate_asset(fixture, schema)
    return cast(list[dict[str, Any]], fixture["scenarios"])


class TableNormalizer:
    """宣言された呼び出し順に正規化結果を返す。"""

    def __init__(self, config: dict[str, Any]) -> None:
        """生成物の属性と表を保持する。"""
        self.generated_id: str = config["generatedId"]
        self.source_hash: str = config["sourceHash"]
        self.mode: str = config["mode"]
        self.table: list[dict[str, object]] = config["table"]
        self.calls: list[object] = []

    def normalize(self, raw: object) -> object:
        """素通り、または呼び出し番号に対応する表の値を返す。"""
        index = len(self.calls)
        self.calls.append(raw)
        if self.mode == "passthrough":
            return raw
        entry = self.table[index]
        assert raw == entry["raw"]
        return entry["normalized"]


class TableCalculation:
    """対応 ID と出力表だけに従う計算 adapter。"""

    def __init__(self, config: dict[str, Any]) -> None:
        """対応 ID と任意の出力表を保持する。"""
        self.supported_case_ids: set[str] = set(config["supportedCaseIds"])
        self.outputs: dict[str, object] = config.get("outputs", {})
        self.executed_case_ids: list[str] = []

    def execute(self, case_id: str, normalized: object) -> object:
        """未対応を送出し、対応 ID は出力表または入力値を返す。"""
        if case_id not in self.supported_case_ids:
            raise VECTORS.UnsupportedVectorCase(case_id)
        self.executed_case_ids.append(case_id)
        return self.outputs.get(case_id, normalized)


def _comparison(config: dict[str, Any]) -> Any:
    """宣言された比較面を既存の契約オブジェクトへ変換する。"""
    fields = tuple(
        PATH_MATCH.FieldContract(
            field=field["field"],
            role=field["role"],
            value_type=field["valueType"],
            nullable=field["nullable"],
            scale=field["scale"],
        )
        for field in config["fields"]
    )
    return PATH_MATCH.ComparisonContract(
        surface=config["surface"],
        fields=fields,
        normalizations=frozenset(config["normalizations"]),
    )


def _contract(config: dict[str, Any]) -> Any:
    """runner ID を pytest として既存の契約オブジェクトを作る。"""
    return VECTORS.VectorContract(
        calculation=config["calculation"],
        vector=config["vector"],
        runner="pytest",
        entrypoint_id=config["entrypointId"],
        direct_target_id=config["directTargetId"],
        case_schema=config["caseSchema"],
        normalization_comparison=_comparison(config["normalizationComparison"]),
        output_comparison=_comparison(config["outputComparison"]),
    )


def test_fixture_has_nine_unique_scenarios() -> None:
    """設計書の九件が重複せず存在することを確認する。"""
    scenarios = _load_scenarios()
    scenario_ids = [scenario["id"] for scenario in scenarios]

    assert len(scenarios) == 9
    assert len(scenario_ids) == len(set(scenario_ids))
    assert set(scenario_ids) == SCENARIO_IDS


def test_existing_runner_tests_have_scenarios() -> None:
    """既存の六つの実行テストとシナリオの対応を確認する。"""
    source = ast.parse(
        (Path(__file__).parent / "test_vectors.py").read_text(encoding="utf-8")
    )
    existing_tests = {
        node.name
        for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }
    scenario_ids = {scenario["id"] for scenario in _load_scenarios()}

    assert len(EXISTING_TEST_SCENARIOS) == 6
    assert set(EXISTING_TEST_SCENARIOS) & EXCLUDED_EXISTING_TESTS == set()
    assert existing_tests == set(EXISTING_TEST_SCENARIOS) | EXCLUDED_EXISTING_TESTS
    assert set(EXISTING_TEST_SCENARIOS.values()) <= scenario_ids


@pytest.mark.parametrize(
    "scenario", _load_scenarios(), ids=lambda scenario: scenario["id"]
)
def test_vector_conformance(scenario: dict[str, Any]) -> None:
    """宣言どおりの結果と adapter 呼び出し痕跡を検査する。"""
    normalizer = TableNormalizer(scenario["normalizer"])
    calculation = TableCalculation(scenario["calculation"])
    expected = scenario["expected"]

    if expected["outcome"] == "complete":
        report = VECTORS.run_vectors(
            scenario["cases"], _contract(scenario["contract"]), normalizer, calculation
        )
        assert report.complete
        assert list(report.declared_case_ids) == expected["declaredCaseIds"]
        assert list(report.consumed_case_ids) == expected["consumedCaseIds"]
    else:
        with pytest.raises(VECTORS.VectorRunError) as error:
            VECTORS.run_vectors(
                scenario["cases"],
                _contract(scenario["contract"]),
                normalizer,
                calculation,
            )
        assert str(error.value).startswith(expected["messagePrefix"])

    assert len(normalizer.calls) == scenario["trace"]["normalizeCalls"]
    assert calculation.executed_case_ids == scenario["trace"]["executedCaseIds"]
