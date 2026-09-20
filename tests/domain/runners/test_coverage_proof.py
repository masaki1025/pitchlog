"""正本と schema から導く要求 case 集合と網羅性の証明を検査する。"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from itertools import product
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
ASSET_PATH = ROOT / "backend/domain/required-cases.json"
VOCABULARY_PATH = ROOT / "backend/domain/vocabulary.schema.json"
ADR_PATH = ROOT / "docs/adr/ADR-003-domain-calc-method.md"

sys.path.insert(0, str(BACKEND_SRC))
REQUIRED = importlib.import_module(
    "pitchlog.domaincheck.runners.required_cases"
)
VECTORS = importlib.import_module("pitchlog.domaincheck.runners.vectors")
PATH_MATCH = importlib.import_module("pitchlog.domaincheck.path_match")

ROUNDING_SIGN_PAIRS = tuple(
    product(
        ("before", "exact", "after"),
        ("positive", "negative"),
    )
)


@pytest.fixture(scope="module")
def asset() -> dict[str, Any]:
    """固定済みの要求 case 資産を返す。"""
    return json.loads(ASSET_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def vocabulary() -> dict[str, Any]:
    """表示 primitive の正である語彙 schema を返す。"""
    return json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def adr_text() -> str:
    """入力範囲の正である ADR 全文を返す。"""
    return ADR_PATH.read_text(encoding="utf-8")


def _cover_map(case: dict[str, Any]) -> dict[str, str]:
    """一 case の軸 ID と分割 ID の対応を返す。"""
    return {
        cover["axisId"]: cover["partitionId"]
        for cover in case["covers"]
    }


def _cross_case(
    candidate: dict[str, Any],
    pair: tuple[str, str],
) -> bool:
    """Case が指定された丸め境界と符号の組を覆うか返す。"""
    covers = _cover_map(candidate)
    return (
        covers.get("rounding-boundary"),
        covers.get("sign"),
    ) == pair


class _GeneratedNormalizer:
    """JSON 文字列から合成入力を復元する生成済み正規化 adapter。"""

    generated_id = "syntheticCoverageNormalizer"
    source_hash = f"sha256:{'2' * 64}"

    def normalize(self, raw: object) -> object:
        """生の JSON 文字列を構造化した payload 行へ正規化する。"""
        assert isinstance(raw, list) and len(raw) == 1
        row = raw[0]
        assert isinstance(row, dict)
        encoded = row["encoded"]
        assert isinstance(encoded, str)
        return [{"payload": json.loads(encoded)}]


class _SyntheticCalculation:
    """対応 case の正規化済み値を返す合成計算 adapter。"""

    def __init__(self, supported: set[str]) -> None:
        """対応する case ID 集合を指定する。"""
        self.supported = supported

    def execute(self, case_id: str, normalized: object) -> object:
        """対応 case を実行し、正規化済み値を計算結果として返す。"""
        if case_id not in self.supported:
            raise VECTORS.UnsupportedVectorCase(case_id)
        return normalized


def _case_schema() -> dict[str, object]:
    """網羅性証明用の合成 vector case schema を返す。"""
    output = {
        "type": "array",
        "minItems": 1,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["payload"],
            "properties": {"payload": {"type": "object"}},
        },
    }
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
                    "required": ["encoded"],
                    "properties": {"encoded": {"type": "string"}},
                },
            },
            "normalized": copy.deepcopy(output),
            "expected": copy.deepcopy(output),
        },
    }


def _vector_contract() -> Any:
    """既存 lossless 比較器を使う合成 vector 契約を返す。"""
    comparison = PATH_MATCH.ComparisonContract(
        surface="structured-only",
        fields=(
            PATH_MATCH.FieldContract(
                "payload",
                "structured",
                "json",
                False,
                None,
            ),
        ),
        normalizations=frozenset(),
    )
    return VECTORS.VectorContract(
        calculation="syntheticCoverageCalculation",
        vector="syntheticCoverageVector",
        runner="pytest",
        entrypoint_id="syntheticCoverageEntrypoint",
        direct_target_id="syntheticCoverageTarget",
        case_schema=_case_schema(),
        normalization_comparison=comparison,
        output_comparison=comparison,
    )


def _vector_cases(required_cases: list[dict[str, Any]]) -> list[dict[str, object]]:
    """要求 case の具体入力をステップ 34 runner 用に変換する。"""
    cases: list[dict[str, object]] = []
    for required_case in required_cases:
        encoded = json.dumps(
            required_case["input"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        output = [{"payload": copy.deepcopy(required_case["input"])}]
        cases.append(
            {
                "caseId": required_case["id"],
                "raw": [{"encoded": encoded}],
                "normalized": output,
                "expected": copy.deepcopy(output),
            }
        )
    return cases


def _run_cases(required_cases: list[dict[str, Any]]) -> Any:
    """要求 case をステップ 34 runner で実際に消費する。"""
    case_ids = {case["id"] for case in required_cases}
    return VECTORS.run_vectors(
        _vector_cases(required_cases),
        _vector_contract(),
        _GeneratedNormalizer(),
        _SyntheticCalculation(case_ids),
    )


def test_asset_matches_independent_authority_and_schema_derivation(
    asset: dict[str, Any],
    adr_text: str,
    vocabulary: dict[str, Any],
) -> None:
    """固定資産が正本 ID と語彙 schema からの独立導出に一致する。"""
    derived = REQUIRED.derive_required_case_asset(adr_text, vocabulary)

    REQUIRED.validate_required_case_asset(asset, adr_text, vocabulary)
    assert derived == asset
    assert asset["authority"]["id"] == "ADR-003 D-11 入力範囲表"
    assert asset["vocabularySchema"]["source"] == (
        "backend/domain/vocabulary.schema.json"
    )
    assert ASSET_PATH.read_text(encoding="utf-8") == (
        json.dumps(asset, ensure_ascii=False, indent=2) + "\n"
    )


def test_all_eight_axes_have_required_cases(asset: dict[str, Any]) -> None:
    """正本から導いた 8 軸すべてに一つ以上の case がある。"""
    axes = {axis["id"] for axis in asset["axes"]}
    covered = {
        cover["axisId"]
        for case in asset["requiredCases"]
        for cover in case["covers"]
    }

    assert len(axes) == 8
    assert covered == axes


def test_rounding_boundary_and_sign_form_exact_six_member_product(
    asset: dict[str, Any],
) -> None:
    """丸め境界 3 分割と正負の直積が過不足なく 6 通りある。"""
    observed = [
        pair
        for pair in ROUNDING_SIGN_PAIRS
        if any(_cross_case(case, pair) for case in asset["requiredCases"])
    ]
    actual_cross_cases = [
        case
        for case in asset["requiredCases"]
        if "rounding-boundary" in _cover_map(case)
        and "sign" in _cover_map(case)
    ]

    assert len(ROUNDING_SIGN_PAIRS) == 6
    assert tuple(observed) == ROUNDING_SIGN_PAIRS
    assert len(actual_cross_cases) == len(ROUNDING_SIGN_PAIRS)


def test_negative_exact_rounding_boundary_is_present(
    asset: dict[str, Any],
) -> None:
    """負値のちょうど中間値 `-1.5` を必須 case に含める。"""
    candidate = next(
        case
        for case in asset["requiredCases"]
        if _cross_case(case, ("exact", "negative"))
    )

    assert candidate["input"]["value"] == {
        "kind": "exact-decimal",
        "value": "-1.5",
    }


@pytest.mark.parametrize(("rounding", "sign"), ROUNDING_SIGN_PAIRS)
def test_removing_each_cross_product_member_fails_individually(
    asset: dict[str, Any],
    rounding: str,
    sign: str,
) -> None:
    """直積の 6 通りを一つずつ削る変異をそれぞれ拒否する。"""
    mutated = copy.deepcopy(asset)
    pair = (rounding, sign)
    mutated["requiredCases"] = [
        case
        for case in mutated["requiredCases"]
        if not _cross_case(case, pair)
    ]

    with pytest.raises(REQUIRED.CoverageError, match="軸分割|直積"):
        REQUIRED.validate_required_case_set(mutated)


def test_one_missing_or_unexpected_evidence_case_fails_set_difference(
    asset: dict[str, Any],
) -> None:
    """要求と証跡の双方向差が一件でもあれば網羅性を証明しない。"""
    required = sorted(REQUIRED.required_case_ids(asset))
    missing_one = required[1:]
    missing_proof = REQUIRED.prove_case_coverage(asset, missing_one)

    assert len(missing_proof.missing) == 1
    assert not missing_proof.complete
    with pytest.raises(REQUIRED.CoverageError, match="missing"):
        REQUIRED.require_complete_coverage(asset, missing_one)

    unexpected_one = [*required, "display.unknown.extra"]
    unexpected_proof = REQUIRED.prove_case_coverage(asset, unexpected_one)
    assert len(unexpected_proof.unexpected) == 1
    assert not unexpected_proof.complete
    with pytest.raises(REQUIRED.CoverageError, match="unexpected"):
        REQUIRED.require_complete_coverage(asset, unexpected_one)


def test_derivation_changes_with_schema_axis_and_rejects_unknown_authority_axis(
    asset: dict[str, Any],
    adr_text: str,
    vocabulary: dict[str, Any],
) -> None:
    """Schema 境界と正本の軸変更が独立導出へ反映される。"""
    changed_schema = copy.deepcopy(vocabulary)
    changed_schema["$defs"]["FixedDecimal"]["properties"]["scale"]["maximum"] = 4
    derived = REQUIRED.derive_required_case_asset(adr_text, changed_schema)

    original_ids = REQUIRED.required_case_ids(asset)
    changed_ids = REQUIRED.required_case_ids(derived)
    assert "display.scale.fixed-decimal.maximum.3" in original_ids
    assert "display.scale.fixed-decimal.maximum.4" in changed_ids
    assert changed_ids != original_ids

    changed_adr = adr_text.replace(
        "nullable / オーバーフロー",
        "nullable / 未知軸 / オーバーフロー",
    )
    with pytest.raises(REQUIRED.CoverageError, match="未知または曖昧"):
        REQUIRED.derive_required_case_asset(changed_adr, vocabulary)


def test_consuming_every_declared_subset_case_does_not_prove_coverage(
    asset: dict[str, Any],
) -> None:
    """宣言した少数 case の全消費だけでは要求集合の網羅と認めない。"""
    subset = asset["requiredCases"][:2]
    vector_report = _run_cases(subset)

    assert vector_report.complete
    assert vector_report.consumed_case_ids == vector_report.declared_case_ids
    proof = REQUIRED.prove_case_coverage(
        asset,
        vector_report.consumed_case_ids,
    )
    assert proof.missing
    assert not proof.complete
    with pytest.raises(REQUIRED.CoverageError, match="missing"):
        REQUIRED.require_complete_coverage(
            asset,
            vector_report.consumed_case_ids,
        )


def test_all_required_cases_run_and_prove_complete_coverage(
    asset: dict[str, Any],
) -> None:
    """要求集合の全 case が runner を完走し網羅性の証明を得る。"""
    vector_report = _run_cases(asset["requiredCases"])
    proof = REQUIRED.require_complete_coverage(
        asset,
        vector_report.consumed_case_ids,
    )

    assert vector_report.complete
    assert proof.complete
    assert proof.required == proof.observed
    assert not proof.missing
    assert not proof.unexpected
