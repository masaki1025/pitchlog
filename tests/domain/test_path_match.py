"""経路一致の 6 次元証跡と lossless 比較器を検証する。"""

from __future__ import annotations

import ast
import copy
import importlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
SCHEMA_PATH = ROOT / "backend/domain/path-match.schema.json"
COMPARATOR_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/path_match.py"
REVIEW_TRIGGERS = ROOT / "backend/domain/review-triggers.json"

sys.path.insert(0, str(BACKEND_SRC))
PATH_MATCH = importlib.import_module("pitchlog.domaincheck.path_match")
COLLECT_LAYERS = importlib.import_module(
    "pitchlog.domaincheck.collect_layers"
)
CHECKER = importlib.import_module("pitchlog.domaincheck.cli")


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object を UTF-8 で読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _key(
    *,
    calculation: str = "syntheticCalculation",
    case: str = "syntheticCase",
    entrypoint: str = "syntheticEntrypoint",
) -> Any:
    """合成した 6 次元要求キーを返す。"""
    return PATH_MATCH.PathKey(
        calculation=calculation,
        vector="syntheticVector",
        case=case,
        runner="pytest",
        entrypoint_id=entrypoint,
        direct_target_id="syntheticDirectTarget",
    )


def _structured_contract() -> Any:
    """状況判定を模した構造化値だけの比較面を返す。"""
    return PATH_MATCH.ComparisonContract(
        surface="structured-only",
        fields=(
            PATH_MATCH.FieldContract(
                field="state",
                role="structured",
                value_type="json",
                nullable=False,
                scale=None,
            ),
            PATH_MATCH.FieldContract(
                field="score",
                role="structured",
                value_type="exact-number",
                nullable=False,
                scale=0,
            ),
        ),
        normalizations=frozenset(
            {"total-order", "exact-numeric-representation"}
        ),
    )


def _integer(value: int) -> dict[str, object]:
    """NumericValue の整数形を返す。"""
    return {"kind": "integer", "value": value}


def _decimal(value: str) -> dict[str, object]:
    """NumericValue の exact decimal 形を返す。"""
    return {"kind": "exact-decimal", "value": value}


def _scaled(value: int, scale: int) -> dict[str, object]:
    """情報保存型統一に用いる scaled integer 形を返す。"""
    return {"kind": "scaled-integer", "value": value, "scale": scale}


def _structured_rows() -> list[dict[str, object]]:
    """構造化値のみの正しい一行を返す。"""
    return [{"state": {"inning": 1, "half": "top"}, "score": _integer(0)}]


def _positive_report() -> Any:
    """正当な 5 判定を持つ最小 report を返す。"""
    key = _key()
    output = _structured_rows()
    return PATH_MATCH.compare_path_set(
        [key],
        [
            PATH_MATCH.PathSubmission(
                key=key,
                expected=output,
                entrypoint_output=copy.deepcopy(output),
                direct_target_output=copy.deepcopy(output),
            )
        ],
        {key.calculation: _structured_contract()},
    )


def _trigger_four_contract() -> Any:
    """トリガー 4 の全比較軸を同時に測る比較面を返す。"""
    fields = [
        PATH_MATCH.FieldContract(
            "rowId", "structured", "json", False, None
        ),
        PATH_MATCH.FieldContract(
            "decimal", "structured", "exact-number", True, 2
        ),
        PATH_MATCH.FieldContract(
            "nullable", "structured", "json", True, None
        ),
    ]
    fields.extend(
        PATH_MATCH.FieldContract(name, "display", "display-string", False, None)
        for name in (
            "characterDisplay",
            "leadingZeroDisplay",
            "negativeDisplay",
            "remainderDisplay",
        )
    )
    return PATH_MATCH.ComparisonContract(
        surface="structured-and-display",
        fields=tuple(fields),
        normalizations=frozenset(
            {"total-order", "exact-numeric-representation"}
        ),
    )


def _trigger_row(
    row_id: str,
    decimal: object,
    nullable: object,
) -> dict[str, object]:
    """表示の厳密一致軸をすべて持つ一行を返す。"""
    return {
        "rowId": row_id,
        "decimal": decimal,
        "nullable": nullable,
        "characterDisplay": "−１",
        "leadingZeroDisplay": "0.333",
        "negativeDisplay": "-2",
        "remainderDisplay": "5回2/3",
    }


def _measure_trigger_four() -> Any:
    """Decimal・NULL・行順・表示文字列を実際に突き合わせる。"""
    key = _key(calculation="triggerFourCalculation")
    expected = [
        _trigger_row("second", _decimal("1.20"), {"kind": "present"}),
        _trigger_row("first", None, None),
    ]
    entrypoint = [
        _trigger_row("first", None, None),
        _trigger_row("second", _scaled(120, 2), {"kind": "present"}),
    ]
    direct_target = [
        _trigger_row("second", _scaled(120, 2), {"kind": "present"}),
        _trigger_row("first", None, None),
    ]
    return PATH_MATCH.compare_path_set(
        [key],
        [
            PATH_MATCH.PathSubmission(
                key,
                expected,
                entrypoint,
                direct_target,
            )
        ],
        {key.calculation: _trigger_four_contract()},
    )


def test_schema_freezes_six_dimensions_five_judgments_and_two_normalizations(
) -> None:
    """不変の骨格と許可する正規化の母集合を固定する。"""
    schema = _read_json(SCHEMA_PATH)
    expectations = schema["x-expectations"]
    dimensions = expectations["sixDimensions"]["expected"]
    judgments = expectations["fiveJudgments"]["expected"]
    normalizations = expectations["allowedNormalizations"]["expected"]

    assert len(dimensions) == 6
    assert set(dimensions) == {
        "calculation",
        "vector",
        "case",
        "runner",
        "entrypointId",
        "directTargetId",
    }
    assert len(judgments) == 5
    assert set(judgments) == {
        "entrypointExecuted",
        "directTargetExecuted",
        "entrypointEqualsExpected",
        "directTargetEqualsExpected",
        "pathsEqual",
    }
    assert len(normalizations) == 2
    assert set(normalizations) == {
        "total-order",
        "exact-numeric-representation",
    }


def test_schema_accepts_a_valid_path_match_report() -> None:
    """正しい 6 次元証跡が閉じた schema に受理される。"""
    schema = _read_json(SCHEMA_PATH)

    CHECKER.validate_asset(_positive_report().to_document(), schema)


@pytest.mark.parametrize("mutation", ["unknown", "missing"])
def test_schema_rejects_unknown_and_missing_evidence_keys(
    mutation: str,
) -> None:
    """証跡 object の未知キーと欠落キーを個別に拒否する。"""
    schema = _read_json(SCHEMA_PATH)
    document = _positive_report().to_document()
    evidence = document["evidence"][0]
    if mutation == "unknown":
        evidence["ignoredField"] = True
    else:
        del evidence["runner"]

    with pytest.raises(CHECKER.CheckerViolation):
        CHECKER.validate_asset(document, schema)


@pytest.mark.parametrize(
    "judgment",
    [
        "entrypoint_executed",
        "direct_target_executed",
        "entrypoint_equals_expected",
        "direct_target_equals_expected",
        "paths_equal",
    ],
)
def test_each_of_five_judgments_is_required_for_success(judgment: str) -> None:
    """5 判定の各 1 件だけが偽でも report を不成立にする。"""
    report = _positive_report()
    evidence = report.evidence[0]
    broken_judgments = replace(evidence.judgments, **{judgment: False})
    broken_evidence = replace(evidence, judgments=broken_judgments)
    broken_report = replace(report, evidence=(broken_evidence,))

    assert not broken_report.complete


def test_one_missing_requirement_fails_by_set_difference() -> None:
    """要求集合にだけある 1 要素を集合差として検出する。"""
    present = _key(case="presentCase")
    missing = _key(case="missingCase")
    output = _structured_rows()

    report = PATH_MATCH.compare_path_set(
        [present, missing],
        [PATH_MATCH.PathSubmission(present, output, output, output)],
        {present.calculation: _structured_contract()},
    )

    assert report.missing == (missing,)
    assert report.unexpected == ()
    assert not report.complete


def test_one_unexpected_evidence_fails_by_set_difference() -> None:
    """証跡集合にだけある 1 要素を集合差として検出する。"""
    required = _key(case="requiredCase")
    unexpected = _key(case="unexpectedCase")
    output = _structured_rows()

    report = PATH_MATCH.compare_path_set(
        [required],
        [
            PATH_MATCH.PathSubmission(required, output, output, output),
            PATH_MATCH.PathSubmission(unexpected, output, output, output),
        ],
        {required.calculation: _structured_contract()},
    )

    assert report.missing == ()
    assert report.unexpected == (unexpected,)
    assert not report.complete


def test_second_entrypoint_cannot_be_hidden_by_first_entrypoint() -> None:
    """二入口の片方だけを実行した提出を要求直積の差で検出する。"""
    first = _key(entrypoint="firstEntrypoint")
    second = _key(entrypoint="secondEntrypoint")
    output = _structured_rows()

    report = PATH_MATCH.compare_path_set(
        [first, second],
        [PATH_MATCH.PathSubmission(first, output, output, output)],
        {first.calculation: _structured_contract()},
    )

    assert report.missing == (second,)
    assert not report.complete


def test_comparator_does_not_round_raw_output_to_contract_scale() -> None:
    """過剰精度を丸めれば一致する値でも scale 違反として拒否する。"""
    key = _key(calculation="roundingCalculation")
    contract = PATH_MATCH.ComparisonContract(
        "structured-only",
        (
            PATH_MATCH.FieldContract(
                "value", "structured", "exact-number", False, 2
            ),
        ),
        frozenset({"exact-numeric-representation"}),
    )
    expected = [{"value": _decimal("1.23")}]
    over_precise = [{"value": _decimal("1.234")}]

    report = PATH_MATCH.compare_path_set(
        [key],
        [PATH_MATCH.PathSubmission(key, expected, over_precise, expected)],
        {key.calculation: contract},
    )

    assert not report.complete
    assert any(
        difference.reason == "scale-mismatch"
        for difference in report.evidence[0].differences
    )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [("unknown", "unknown-field"), ("missing", "missing-field")],
)
def test_unknown_and_missing_output_fields_fail(
    mutation: str,
    reason: str,
) -> None:
    """比較行の未知フィールド・欠落フィールドを個別に拒否する。"""
    key = _key(calculation="fieldSetCalculation")
    expected = _structured_rows()
    changed = copy.deepcopy(expected)
    if mutation == "unknown":
        changed[0]["ignored"] = True
    else:
        del changed[0]["state"]

    report = PATH_MATCH.compare_path_set(
        [key],
        [PATH_MATCH.PathSubmission(key, expected, changed, expected)],
        {key.calculation: _structured_contract()},
    )

    assert not report.complete
    assert any(
        difference.reason == reason
        for difference in report.evidence[0].differences
    )


def test_null_is_not_made_equal_to_a_default_value() -> None:
    """Nullable の null と既定値 0 を同値化しない。"""
    key = _key(calculation="nullCalculation")
    contract = PATH_MATCH.ComparisonContract(
        "structured-only",
        (
            PATH_MATCH.FieldContract(
                "nullableValue", "structured", "json", True, None
            ),
        ),
        frozenset(),
    )
    expected = [{"nullableValue": None}]
    defaulted = [{"nullableValue": 0}]

    report = PATH_MATCH.compare_path_set(
        [key],
        [PATH_MATCH.PathSubmission(key, expected, defaulted, expected)],
        {key.calculation: contract},
    )

    assert not report.complete
    assert any(
        difference.reason == "value-mismatch"
        for difference in report.evidence[0].differences
    )


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("characterDisplay", "-１"),
        ("leadingZeroDisplay", ".333"),
        ("negativeDisplay", "−2"),
        ("remainderDisplay", "5 2/3回"),
    ],
)
def test_display_string_variations_are_not_normalized(
    field: str,
    changed: str,
) -> None:
    """文字種・先頭 0・負号・剰余表記の各差を完全一致で検出する。"""
    key = _key(calculation="displayCalculation")
    expected = [_trigger_row("only", _decimal("1.20"), None)]
    actual = copy.deepcopy(expected)
    actual[0][field] = changed

    report = PATH_MATCH.compare_path_set(
        [key],
        [PATH_MATCH.PathSubmission(key, expected, actual, expected)],
        {key.calculation: _trigger_four_contract()},
    )

    assert not report.complete
    assert any(
        difference.field == field
        and difference.reason == "display-mismatch"
        for difference in report.evidence[0].differences
    )


def test_situation_judgment_fixture_is_structured_only() -> None:
    """状況判定 fixture の比較面に表示値を持たせない。"""
    report = _positive_report()
    document = report.to_document()
    evidence = document["evidence"][0]

    assert report.complete
    assert evidence["comparisonSurface"] == "structured-only"
    assert {
        field["role"] for field in evidence["comparedFields"]
    } == {"structured"}


def test_ingame_preprocessing_fixture_includes_display_values() -> None:
    """断中前処理 fixture が構造化値と完成表示値の双方を比較する。"""
    report = _measure_trigger_four()
    document = report.to_document()
    evidence = document["evidence"][0]
    roles = {field["role"] for field in evidence["comparedFields"]}

    assert report.complete
    assert evidence["comparisonSurface"] == "structured-and-display"
    assert roles == {"structured", "display"}


def test_allowed_lossless_normalizations_pass_all_trigger_four_axes() -> None:
    """Decimal・NULL・行順・表示文字列を許可された二方式だけで照合する。"""
    measured = _measure_trigger_four()

    assert measured.complete
    assert measured.evidence[0].differences == ()
    assert measured.evidence[0].judgments.complete


def test_valid_evidence_actually_passes_all_five_judgments() -> None:
    """正当な raw 出力が実際に 5 判定をすべて通過する。"""
    report = _positive_report()
    judgments = report.evidence[0].judgments

    assert report.complete
    assert judgments.entrypoint_executed
    assert judgments.direct_target_executed
    assert judgments.entrypoint_equals_expected
    assert judgments.direct_target_equals_expected
    assert judgments.paths_equal


def test_comparator_reuses_step_thirty_one_evidence_without_recollecting() -> None:
    """収集処理を複製せずステップ 31 の証跡型から提出を作る。"""
    key = _key()
    output = _structured_rows()
    collected = COLLECT_LAYERS.LayerEvidence(
        calculation=key.calculation,
        property_id="syntheticProperty",
        property_kind="equivalence",
        generated_cases=1,
        status="passed",
        vector=key.vector,
        case=key.case,
        entrypoint_id=key.entrypoint_id,
        direct_target_id=key.direct_target_id,
        judgments=COLLECT_LAYERS.FiveJudgments(True, True, True, True, True),
        artifact_hashes_valid=True,
        stage_chain_valid=True,
        provenance=COLLECT_LAYERS.RunnerProvenance(
            COLLECT_LAYERS.Runner.PYTEST,
            "junit-xml",
            f"sha256:{'0' * 64}",
            "synthetic::test",
        ),
    )
    submission = PATH_MATCH.submission_from_collected(
        collected,
        expected=output,
        entrypoint_output=output,
        direct_target_output=output,
    )

    report = PATH_MATCH.compare_path_set(
        [key],
        [submission],
        {key.calculation: _structured_contract()},
    )
    tree = ast.parse(COMPARATOR_SOURCE.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert report.complete
    assert "xml.etree.ElementTree" not in imported
    assert "pitchlog.domaincheck.collect_layers" in (
        COMPARATOR_SOURCE.read_text(encoding="utf-8")
    )


def test_trigger_four_record_is_bound_to_measured_lossless_result() -> None:
    """トリガー 4 の記録を全比較軸の実測結果へ束縛する。"""
    measured = _measure_trigger_four()
    asset = _read_json(REVIEW_TRIGGERS)
    trigger = next(item for item in asset["triggers"] if item["id"] == 4)

    assert measured.complete
    assert trigger["evaluation"] == {"fired": not measured.complete}
    assert trigger["evidenceLocation"] == "tests/domain/test_path_match.py"


def test_schema_asset_is_indented_and_has_trailing_newline() -> None:
    """コア資産を逐行確認できる整形で固定する。"""
    content = SCHEMA_PATH.read_text(encoding="utf-8")

    assert content.endswith("\n")
    assert "\n  \"$schema\"" in content
