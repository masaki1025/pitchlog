"""合成契約で網羅ベクタ runner の基盤を検証する。"""

from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
RUNNER_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/runners/vectors.py"

sys.path.insert(0, str(BACKEND_SRC))
VECTORS = importlib.import_module("pitchlog.domaincheck.runners.vectors")
PATH_MATCH = importlib.import_module("pitchlog.domaincheck.path_match")


class SyntheticGeneratedNormalizer:
    """合成 DSL から生成済みとみなす正規化 adapter。"""

    generated_id = "syntheticNormalizer"
    source_hash = f"sha256:{'1' * 64}"

    def __init__(self, *, passthrough: bool = False) -> None:
        """素通り変異の有無を指定して初期化する。"""
        self.passthrough = passthrough
        self.calls: list[object] = []
        self.outputs: list[object] = []

    def normalize(self, raw: object) -> object:
        """Legacy 文字列を整数 NumericValue へ正規化する。"""
        self.calls.append(raw)
        if self.passthrough:
            self.outputs.append(raw)
            return raw
        assert isinstance(raw, list)
        rows: list[dict[str, object]] = []
        for row in raw:
            assert isinstance(row, dict)
            legacy_value = row["legacyValue"]
            assert isinstance(legacy_value, str)
            rows.append(
                {
                    "value": {
                        "kind": "integer",
                        "value": int(legacy_value),
                    }
                }
            )
        self.outputs.append(rows)
        return rows


class SyntheticCalculation:
    """正規化済み入力だけを受ける合成計算 adapter。"""

    def __init__(self, supported: set[str]) -> None:
        """対応する case ID 集合を指定して初期化する。"""
        self.supported = supported
        self.inputs: list[tuple[str, object]] = []

    def execute(self, case_id: str, normalized: object) -> object:
        """対応 case なら受け取った正規化済み値を計算結果として返す。"""
        if case_id not in self.supported:
            raise VECTORS.UnsupportedVectorCase(case_id)
        self.inputs.append((case_id, normalized))
        return normalized


def _numeric_rows_schema() -> dict[str, object]:
    """整数 NumericValue 行の合成 schema を返す。"""
    return {
        "type": "array",
        "minItems": 1,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["value"],
            "properties": {
                "value": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "value"],
                    "properties": {
                        "kind": {"const": "integer"},
                        "value": {"type": "integer"},
                    },
                }
            },
        },
    }


def _case_schema() -> dict[str, object]:
    """合成 vector の一 case を閉じる schema を返す。"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["caseId", "raw", "normalized", "expected"],
        "properties": {
            "caseId": {
                "type": "string",
                "pattern": "^[A-Za-z][A-Za-z0-9._-]*$",
            },
            "raw": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["legacyValue"],
                    "properties": {
                        "legacyValue": {
                            "type": "string",
                            "pattern": "^[0-9]+$",
                        }
                    },
                },
            },
            "normalized": _numeric_rows_schema(),
            "expected": _numeric_rows_schema(),
        },
    }


def _comparison_contract() -> Any:
    """整数 NumericValue の lossless 比較面を返す。"""
    return PATH_MATCH.ComparisonContract(
        surface="structured-only",
        fields=(
            PATH_MATCH.FieldContract(
                "value", "structured", "exact-number", False, 0
            ),
        ),
        normalizations=frozenset({"exact-numeric-representation"}),
    )


def _contract() -> Any:
    """合成 vector runner の契約を返す。"""
    comparison = _comparison_contract()
    return VECTORS.VectorContract(
        calculation="syntheticVectorCalculation",
        vector="syntheticVector",
        runner="pytest",
        entrypoint_id="syntheticEntrypoint",
        direct_target_id="syntheticNormalizerTarget",
        case_schema=_case_schema(),
        normalization_comparison=comparison,
        output_comparison=comparison,
    )


def _case(case_id: str, raw_value: str) -> dict[str, object]:
    """正規化前後と計算期待値を持つ合成 case を返す。"""
    normalized = [
        {"value": {"kind": "integer", "value": int(raw_value)}}
    ]
    return {
        "caseId": case_id,
        "raw": [{"legacyValue": raw_value}],
        "normalized": normalized,
        "expected": copy.deepcopy(normalized),
    }


def _valid_cases() -> list[dict[str, object]]:
    """順序付きの正しい合成 case 群を返す。"""
    return [_case("caseOne", "001"), _case("caseTwo", "002")]


def test_passthrough_normalization_fails_before_calculation() -> None:
    """生値をそのまま計算入力へ渡す素通り変異を拒否する。"""
    normalizer = SyntheticGeneratedNormalizer(passthrough=True)
    calculation = SyntheticCalculation({"caseOne", "caseTwo"})

    with pytest.raises(VECTORS.VectorRunError, match="生成済み正規化の出力が不一致"):
        VECTORS.run_vectors(
            _valid_cases(),
            _contract(),
            normalizer,
            calculation,
        )

    assert len(normalizer.calls) == 1
    assert calculation.inputs == []


def test_unsupported_case_fails_individually() -> None:
    """Vector が宣言した case に計算 adapter が未対応なら拒否する。"""
    normalizer = SyntheticGeneratedNormalizer()
    calculation = SyntheticCalculation({"caseOne"})

    with pytest.raises(VECTORS.VectorRunError, match="未対応 case: caseTwo"):
        VECTORS.run_vectors(
            _valid_cases(),
            _contract(),
            normalizer,
            calculation,
        )

    assert [case_id for case_id, _ in calculation.inputs] == ["caseOne"]


def test_unknown_case_field_fails_individually() -> None:
    """Case schema に無い未知 field を拒否する。"""
    cases = _valid_cases()
    cases[0]["ignored"] = True

    with pytest.raises(VECTORS.VectorRunError, match="case schema 不一致"):
        VECTORS.run_vectors(
            cases,
            _contract(),
            SyntheticGeneratedNormalizer(),
            SyntheticCalculation({"caseOne", "caseTwo"}),
        )


def test_duplicate_case_id_fails_individually() -> None:
    """異なる内容が同じ case ID を再利用する vector を拒否する。"""
    cases = [_case("duplicateCase", "001"), _case("duplicateCase", "002")]

    with pytest.raises(VECTORS.VectorRunError, match="case ID が重複"):
        VECTORS.run_vectors(
            cases,
            _contract(),
            SyntheticGeneratedNormalizer(),
            SyntheticCalculation({"duplicateCase"}),
        )


def test_case_schema_mismatch_fails_individually() -> None:
    """Raw 値の型が合成契約 schema と違う case を拒否する。"""
    cases = _valid_cases()
    raw = cases[0]["raw"]
    assert isinstance(raw, list)
    raw[0]["legacyValue"] = 1

    with pytest.raises(VECTORS.VectorRunError, match="case schema 不一致"):
        VECTORS.run_vectors(
            cases,
            _contract(),
            SyntheticGeneratedNormalizer(),
            SyntheticCalculation({"caseOne", "caseTwo"}),
        )


def test_valid_vector_consumes_every_case_and_reaches_calculation() -> None:
    """正しい vector が正規化を経て全 case を実際に完走する。"""
    cases = _valid_cases()
    normalizer = SyntheticGeneratedNormalizer()
    calculation = SyntheticCalculation({"caseOne", "caseTwo"})

    report = VECTORS.run_vectors(
        cases,
        _contract(),
        normalizer,
        calculation,
    )

    assert report.complete
    assert report.declared_case_ids == ("caseOne", "caseTwo")
    assert report.consumed_case_ids == report.declared_case_ids
    assert len(report.executions) == len(cases) == 2
    assert all(item.normalization_matched for item in report.executions)
    assert all(item.output_matched for item in report.executions)
    assert all(
        calculation.inputs[index][1] is normalizer.outputs[index]
        for index in range(len(cases))
    )


def test_runner_uses_existing_schema_checker_and_lossless_comparator() -> None:
    """Schema と lossless 比較を既存機構へ委譲していることを静的確認する。"""
    source = RUNNER_SOURCE.read_text(encoding="utf-8")

    assert "from pitchlog.domaincheck.cli import" in source
    assert "validate_asset" in source
    assert "from pitchlog.domaincheck.path_match import" in source
    assert "compare_path_set" in source
    assert "required-cases" not in source
